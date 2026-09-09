import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.retrieve import embed_query, preprocess_query, search_chunks
from app.services.chat import build_prompt, call_groq, call_groq_stream
from app.services.cache import check_cache, store_cache
from app.services.relevance import NO_RELEVANT_INFO_RESPONSE, is_relevant

router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    document_ids: list[int] | None = None   # empty/None = search all
    notebook_id: int | None = None


# ── Helpers ────────────────────────────────────────────────────────────────

def _has_chunks(notebook_id: int | None, document_ids: list[int] | None) -> bool:
    """Return True if there are any searchable chunks matching the given filters."""
    db = SessionLocal()
    try:
        filters: list[str] = []
        params: dict = {}
        if notebook_id is not None:
            filters.append("d.notebook_id = :notebook_id")
            params["notebook_id"] = notebook_id
        if document_ids:
            params["doc_ids"] = "{" + ",".join(str(i) for i in document_ids) + "}"
            filters.append("d.id = ANY(CAST(:doc_ids AS INT[]))")
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        sql = f"SELECT COUNT(*) FROM chunks c JOIN documents d ON d.id = c.document_id {where}"
        count = db.execute(text(sql), params).scalar()
        return count > 0
    finally:
        db.close()


def _save_exchange(notebook_id: int | None, question: str, answer: str, sources: list[dict]) -> None:
    """Persist the user question + assistant answer pair to the messages table."""
    if notebook_id is None:
        return
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO messages (notebook_id, role, content, sources_json) "
                "VALUES (:nb, 'user', :content, '[]')"
            ),
            {"nb": notebook_id, "content": question},
        )
        db.execute(
            text(
                "INSERT INTO messages (notebook_id, role, content, sources_json) "
                "VALUES (:nb, 'assistant', :content, :sources)"
            ),
            {"nb": notebook_id, "content": answer, "sources": json.dumps(sources)},
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# ── GET messages ───────────────────────────────────────────────────────────

@router.get("/messages")
def list_messages(notebook_id: int | None = None):
    """
    Return persisted chat messages, optionally filtered by notebook_id.
    Ordered by creation time ascending so the UI can render them in order.
    """
    db = SessionLocal()
    try:
        if notebook_id is not None:
            rows = db.execute(
                text(
                    "SELECT id, role, content, sources_json, created_at "
                    "FROM messages WHERE notebook_id = :nb ORDER BY created_at ASC"
                ),
                {"nb": notebook_id},
            ).fetchall()
        else:
            rows = db.execute(
                text(
                    "SELECT id, role, content, sources_json, created_at "
                    "FROM messages ORDER BY created_at ASC"
                )
            ).fetchall()

        return [
            {
                "id": row.id,
                "role": row.role,
                "content": row.content,
                "sources": json.loads(row.sources_json or "[]"),
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    finally:
        db.close()


# ── POST /chat (non-streaming, kept for backward compat) ───────────────────

@router.post("/chat")
def chat(request: ChatRequest):
    """
    RAG chat endpoint (non-streaming):
    preprocess -> embed_query -> check_cache
      -> (search_chunks [top 5] -> relevance gate -> build_prompt -> call_groq -> store_cache)
    """
    raw_question = (request.question or "").strip()
    if not raw_question:
        raise HTTPException(status_code=400, detail="question must not be empty.")

    if not _has_chunks(request.notebook_id, request.document_ids):
        return {"answer": "Upload a document first.", "sources": [], "cached": False}

    query_embedding = embed_query(preprocess_query(raw_question))

    # Check cache first
    cached_hit = check_cache(
        query_embedding,
        document_ids=request.document_ids or None,
        notebook_id=request.notebook_id
    )
    if cached_hit:
        return {
            "answer": cached_hit["answer"],
            "sources": cached_hit["sources"],
            "cached": True
        }

    try:
        chunks = search_chunks(
            query_embedding,
            limit=5,
            document_ids=request.document_ids or None,
            notebook_id=request.notebook_id,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="Retrieval failed. Please try again.")

    if not is_relevant(chunks):
        store_cache(
            raw_question,
            query_embedding,
            NO_RELEVANT_INFO_RESPONSE,
            [],
            document_ids=request.document_ids or None,
            notebook_id=request.notebook_id
        )
        return {"answer": NO_RELEVANT_INFO_RESPONSE, "sources": [], "cached": False}

    prompt = build_prompt(raw_question, chunks)

    try:
        answer = call_groq(prompt)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    seen: set[tuple] = set()
    sources: list[dict] = []
    for chunk in chunks:
        key = (chunk["filename"], chunk["page_number"])
        if key not in seen:
            seen.add(key)
            sources.append({"filename": chunk["filename"], "page": chunk["page_number"]})

    # Save to semantic cache
    store_cache(
        raw_question,
        query_embedding,
        answer,
        sources,
        document_ids=request.document_ids or None,
        notebook_id=request.notebook_id
    )

    return {"answer": answer, "sources": sources, "cached": False}


# ── POST /chat/stream (SSE streaming) ─────────────────────────────────────

@router.post("/chat/stream")
def chat_stream(request: ChatRequest):
    """
    RAG chat endpoint (streaming SSE):
    preprocess -> embed_query -> check_cache
      -> (search_chunks [top 5] -> relevance gate -> build_prompt -> call_groq_stream -> store_cache)
    Persists the exchange to the messages table after streaming completes.
    """
    raw_question = (request.question or "").strip()
    if not raw_question:
        raise HTTPException(status_code=400, detail="question must not be empty.")

    if not _has_chunks(request.notebook_id, request.document_ids):
        def empty_stream():
            yield "data: Upload a document first.\n\n"
            yield "event: sources\ndata: []\n\n"
        return StreamingResponse(empty_stream(), media_type="text/event-stream")

    query_embedding = embed_query(preprocess_query(raw_question))
    notebook_id = request.notebook_id
    document_ids = request.document_ids or None

    # Check cache first
    cached_hit = check_cache(
        query_embedding,
        document_ids=document_ids,
        notebook_id=notebook_id
    )

    import urllib.parse

    if cached_hit:
        def stream_cached():
            # Let the client know it was served from the cache
            yield "event: cached\ndata: true\n\n"
            
            # Stream the cached response character-by-character to simulate standard typing flow
            # (or chunk it for speed, let's stream in small 10-char chunks)
            ans = cached_hit["answer"]
            chunk_size = 15
            for i in range(0, len(ans), chunk_size):
                chunk = ans[i:i + chunk_size]
                encoded_chunk = urllib.parse.quote(chunk)
                yield f"data: {encoded_chunk}\n\n"

            yield f"event: sources\ndata: {json.dumps(cached_hit['sources'])}\n\n"
            # Message history persistence (cache hits don't create duplicate db records if preferred,
            # but standard behavior should persist user interactions, so we save the exchange)
            _save_exchange(notebook_id, raw_question, ans, cached_hit["sources"])

        return StreamingResponse(stream_cached(), media_type="text/event-stream")

    # Cache Miss - Standard Pipeline
    try:
        chunks = search_chunks(
            query_embedding,
            limit=5,
            document_ids=document_ids,
            notebook_id=notebook_id,
        )
    except Exception:
        def error_stream():
            yield "event: error\ndata: Retrieval failed. Please try again.\n\n"
            yield "event: sources\ndata: []\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    if not is_relevant(chunks):
        def irrelevant_stream():
            yield "event: cached\ndata: false\n\n"
            yield f"data: {urllib.parse.quote(NO_RELEVANT_INFO_RESPONSE)}\n\n"
            yield "event: sources\ndata: []\n\n"
            store_cache(
                raw_question,
                query_embedding,
                NO_RELEVANT_INFO_RESPONSE,
                [],
                document_ids=document_ids,
                notebook_id=notebook_id
            )
            _save_exchange(notebook_id, raw_question, NO_RELEVANT_INFO_RESPONSE, [])

        return StreamingResponse(irrelevant_stream(), media_type="text/event-stream")

    prompt = build_prompt(raw_question, chunks)

    # Deduplicate sources
    seen: set[tuple] = set()
    sources: list[dict] = []
    for chunk in chunks:
        key = (chunk["filename"], chunk["page_number"])
        if key not in seen:
            seen.add(key)
            sources.append({"filename": chunk["filename"], "page": chunk["page_number"]})

    def generate():
        full_content = ""
        try:
            # Let client know this is not a cached response
            yield "event: cached\ndata: false\n\n"

            for text_chunk in call_groq_stream(prompt):
                if text_chunk:
                    full_content += text_chunk
                    encoded_chunk = urllib.parse.quote(text_chunk)
                    yield f"data: {encoded_chunk}\n\n"

            yield f"event: sources\ndata: {json.dumps(sources)}\n\n"

            # Save query and generated answer to semantic cache
            store_cache(
                raw_question,
                query_embedding,
                full_content,
                sources,
                document_ids=document_ids,
                notebook_id=notebook_id
            )

            # Persist the exchange to the messages table
            _save_exchange(notebook_id, raw_question, full_content, sources)

        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
