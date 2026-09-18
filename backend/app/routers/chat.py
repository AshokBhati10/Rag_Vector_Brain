import json
import re
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import (
    check_document_ids_or_404,
    get_owned_notebook_or_404,
    require_user,
)
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


def _authorize_chat(
    http_request: Request, notebook_id: int | None, document_ids: list[int] | None
) -> dict:
    """Enforce per-user isolation for the RAG endpoints.

    The notebook must belong to the logged-in user (400 when missing, 404
    otherwise) and every selected document must sit in the user's notebooks.
    An unscoped (None) notebook is rejected: without a notebook scope,
    retrieval could cross into other users' documents.
    """
    user = require_user(http_request)
    get_owned_notebook_or_404(notebook_id, user["id"])
    check_document_ids_or_404(user["id"], document_ids)
    return user


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


# ── Source tracking ────────────────────────────────────────────────────────

# Bracket classes cover ASCII [...] and CJK 【...】 markers — the model emits
# both styles nondeterministically. Matching is still exact: only cited pairs
# present in the retrieved set are kept, so nothing is ever inferred.
_CITATION_RE = re.compile(r"[\[【]([^\[\]【】]+?),\s*p\.\s*(\d+)\s*[\]】]")


def _chunk_sources(chunks: list[dict]) -> list[dict]:
    """Dedupe retrieved chunks into [{filename, page}] records."""
    seen: set[tuple] = set()
    sources: list[dict] = []
    for chunk in chunks:
        key = (chunk["filename"], chunk["page_number"])
        if key not in seen:
            seen.add(key)
            sources.append({"filename": chunk["filename"], "page": chunk["page_number"]})
    return sources


def _filter_sources_by_citations(answer: str, retrieved_sources: list[dict]) -> list[dict]:
    """Keep only retrieved sources the final answer actually cites.

    The model is instructed to cite real SOURCE metadata as
    ``[filename, p. N]``. A retrieved (filename, page) pair is returned only
    when the finished answer text cites exactly that pair. Anything uncited —
    including a model-written refusal with no citations — yields no sources.
    Matching is exact: never guess, infer, or fabricate entries.
    """
    cited: set[tuple] = set()
    for m in _CITATION_RE.finditer(answer or ""):
        try:
            cited.add((m.group(1).strip(), int(m.group(2))))
        except (ValueError, TypeError):
            continue
    return [s for s in retrieved_sources if (s["filename"], s["page"]) in cited]


# ── GET messages ───────────────────────────────────────────────────────────

@router.get("/messages")
def list_messages(http_request: Request, notebook_id: int | None = None):
    """
    Return the logged-in user's persisted chat messages, optionally filtered
    by one of their own notebooks (else 404). Ordered by creation time
    ascending so the UI can render them in order.
    """
    user = require_user(http_request)
    db = SessionLocal()
    try:
        if notebook_id is not None:
            get_owned_notebook_or_404(notebook_id, user["id"])
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
                    "SELECT m.id, m.role, m.content, m.sources_json, m.created_at "
                    "FROM messages m JOIN notebooks n ON n.id = m.notebook_id "
                    "WHERE n.user_id = :user_id ORDER BY m.created_at ASC"
                ),
                {"user_id": user["id"]},
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
def chat(request: ChatRequest, http_request: Request):
    """
    RAG chat endpoint (non-streaming):
    preprocess -> embed_query -> check_cache
      -> (search_chunks [top 5] -> relevance gate -> build_prompt -> call_groq -> store_cache)
    Scoped to the logged-in user's notebook (see _authorize_chat).
    """
    _authorize_chat(http_request, request.notebook_id, request.document_ids)
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
        # Re-derive actual sources from the cached answer text so even rows
        # cached before citation filtering return only cited sources.
        sources = _filter_sources_by_citations(
            cached_hit["answer"], cached_hit["sources"]
        )
        _save_exchange(
            request.notebook_id, raw_question,
            cached_hit["answer"], sources,
        )
        return {
            "answer": cached_hit["answer"],
            "sources": sources,
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
        _save_exchange(request.notebook_id, raw_question, NO_RELEVANT_INFO_RESPONSE, [])
        return {"answer": NO_RELEVANT_INFO_RESPONSE, "sources": [], "cached": False}

    prompt = build_prompt(raw_question, chunks)

    try:
        answer = call_groq(prompt)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Sources = retrieved chunks actually cited by the finished answer —
    # never the whole retrieval set or the selected-document list.
    sources = _filter_sources_by_citations(answer, _chunk_sources(chunks))

    # Save to semantic cache
    store_cache(
        raw_question,
        query_embedding,
        answer,
        sources,
        document_ids=request.document_ids or None,
        notebook_id=request.notebook_id
    )

    # Persist the exchange to the messages table (mirrors the streaming endpoint)
    _save_exchange(request.notebook_id, raw_question, answer, sources)

    return {"answer": answer, "sources": sources, "cached": False}


# ── POST /chat/stream (SSE streaming) ─────────────────────────────────────

@router.post("/chat/stream")
def chat_stream(request: ChatRequest, http_request: Request):
    """
    RAG chat endpoint (streaming SSE):
    preprocess -> embed_query -> check_cache
      -> (search_chunks [top 5] -> relevance gate -> build_prompt -> call_groq_stream -> store_cache)
    Persists the exchange to the messages table after streaming completes.
    Scoped to the logged-in user's notebook (see _authorize_chat).
    """
    _authorize_chat(http_request, request.notebook_id, request.document_ids)
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

            # Only the sources the cached answer actually cites (same rule as
            # fresh answers; also corrects rows cached before filtering).
            sources = _filter_sources_by_citations(ans, cached_hit["sources"])
            yield f"event: sources\ndata: {json.dumps(sources)}\n\n"
            # Message history persistence (cache hits don't create duplicate db records if preferred,
            # but standard behavior should persist user interactions, so we save the exchange)
            _save_exchange(notebook_id, raw_question, ans, sources)

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

    # Candidate sources from retrieval; the final list is derived from the
    # finished answer text inside generate() (only actually-cited pairs).
    retrieved_sources = _chunk_sources(chunks)

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

            sources = _filter_sources_by_citations(full_content, retrieved_sources)
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
