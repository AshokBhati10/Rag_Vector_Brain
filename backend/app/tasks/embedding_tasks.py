"""Stage 2 of async ingestion: chunk → 384-dim embed → pgvector store.

Reuses ``chunk_text`` / ``embed_chunks`` from ``app.services.ingest`` and the
exact chunk INSERT from the old synchronous upload endpoint, so citations
(filename + page_number per chunk) behave identically.
"""
from sqlalchemy import text

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.ingest import chunk_text, embed_chunks


def _mark_failed(doc_id: int, message: str) -> None:
    """Terminal failure state: never leave a document stuck in processing."""
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE documents SET status = 'failed', error_message = :msg "
                "WHERE id = :id"
            ),
            {"msg": message[:500], "id": doc_id},
        )
        db.commit()
    finally:
        db.close()


@celery_app.task(name="app.tasks.embedding_tasks.embed_and_store")
def embed_and_store(doc_id: int, pages: list, total_pages: int) -> dict:
    """Chunk pages, embed them, store chunks + mark the document completed."""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT id, status FROM documents WHERE id = :id"),
            {"id": doc_id},
        ).fetchone()
    finally:
        db.close()
    if row is None:
        return {"skipped": "document deleted before embedding"}
    if row.status != "parsing":
        return {"skipped": f"unexpected status {row.status!r}"}

    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE documents SET status = 'embedding' WHERE id = :id"),
            {"id": doc_id},
        )
        db.commit()
    finally:
        db.close()

    try:
        chunks = chunk_text(pages)
        if not any((c.get("content") or "").strip() for c in chunks):
            _mark_failed(
                doc_id,
                "No extractable text found in this PDF. "
                "Scanned/image-only PDFs are not supported.",
            )
            return {"failed": "no usable chunks"}
        embeddings = embed_chunks(chunks)
    except Exception as e:
        _mark_failed(doc_id, f"Chunking/embedding failed: {e}")
        return {"failed": str(e)[:200]}

    db = SessionLocal()
    try:
        # Re-check the document still exists (it may have been deleted while
        # the worker was busy) to avoid orphan chunks on a FK violation.
        still_there = db.execute(
            text("SELECT id FROM documents WHERE id = :id"), {"id": doc_id}
        ).fetchone()
        if still_there is None:
            db.rollback()
            return {"skipped": "document deleted during embedding"}
        for chunk, embedding in zip(chunks, embeddings):
            db.execute(
                text(
                    "INSERT INTO chunks (document_id, content, page_number, embedding) "
                    "VALUES (:doc_id, :content, :page_number, :embedding)"
                ),
                {
                    "doc_id": doc_id,
                    "content": chunk["content"],
                    "page_number": chunk["page_number"],
                    "embedding": str(embedding),
                },
            )
        db.execute(
            text(
                "UPDATE documents SET status = 'completed', total_pages = :pages, "
                "error_message = NULL WHERE id = :id"
            ),
            {"pages": total_pages, "id": doc_id},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        _mark_failed(doc_id, f"Chunk storage failed: {e}")
        return {"failed": str(e)[:200]}
    finally:
        db.close()
    return {"completed": doc_id, "chunks": len(chunks)}
