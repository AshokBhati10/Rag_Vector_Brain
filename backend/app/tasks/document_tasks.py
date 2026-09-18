"""Stage 1 of async ingestion: Docling PDF → structured pages.

Reuses ``app.services.ingest.parse_pdf`` unchanged — only the caller moved
from the FastAPI upload endpoint into a Celery worker.
"""
import os

from sqlalchemy import text

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.ingest import parse_pdf

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")


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


@celery_app.task(name="app.tasks.document_tasks.parse_document")
def parse_document(doc_id: int) -> dict:
    """Parse the saved PDF with Docling, then enqueue stage 2 (chunk+embed)."""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT id, file_path, status FROM documents WHERE id = :id"),
            {"id": doc_id},
        ).fetchone()
    finally:
        db.close()
    if row is None:
        return {"skipped": "document deleted before processing"}
    if row.status != "processing":
        return {"skipped": f"unexpected status {row.status!r}"}

    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE documents SET status = 'parsing' WHERE id = :id"),
            {"id": doc_id},
        )
        db.commit()
    finally:
        db.close()

    try:
        with open(os.path.join(UPLOAD_DIR, f"{doc_id}.pdf"), "rb") as f:
            file_bytes = f.read()
    except FileNotFoundError:
        _mark_failed(doc_id, "Source PDF is missing from storage.")
        return {"failed": "source file missing"}

    try:
        pages = parse_pdf(file_bytes)
    except Exception as e:
        _mark_failed(doc_id, f"PDF parsing failed: {e}")
        return {"failed": str(e)[:200]}

    if not any((p.get("text") or "").strip() for p in pages):
        _mark_failed(
            doc_id,
            "No extractable text found in this PDF. "
            "Scanned/image-only PDFs are not supported.",
        )
        return {"failed": "no extractable text"}

    # Hand off to stage 2 through RabbitMQ (pages are JSON-serializable).
    from app.tasks.embedding_tasks import embed_and_store

    embed_and_store.delay(doc_id, pages, len(pages))
    return {"queued": "embed", "pages": len(pages)}
