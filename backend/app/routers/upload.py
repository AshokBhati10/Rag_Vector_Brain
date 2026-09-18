import os

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import text

from app.auth import get_owned_notebook_or_404, require_user
from app.db.session import SessionLocal

router = APIRouter()

# Reasonable cap for an assignment demo (also enforced by Nginx — keep the
# backend limit below the proxy's client_max_body_size).
MAX_UPLOAD_BYTES = int(os.getenv("UPLOAD_MAX_MB", "20")) * 1024 * 1024
MAX_FILENAME_LEN = 200  # DB column is VARCHAR(255); stay safely under it

# Saved PDFs live here (persisted via the ./backend:/app volume mount).
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")


def _safe_filename(filename: str | None) -> str:
    """Normalize an upload filename: drop paths/NULs, enforce .pdf + length."""
    if not filename:
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    # Strip any directory components (some browsers send full paths) + NULs.
    name = filename.replace("\\", "/").split("/")[-1].replace("\x00", "").strip()
    if not name or not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    if len(name) > MAX_FILENAME_LEN:
        stem, ext = name[:-4], name[-4:]  # keep the .pdf extension visible
        name = stem[: MAX_FILENAME_LEN - len(ext)] + ext
    return name


@router.post("/upload")
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    notebook_id: int | None = Form(None),
):
    """Accept a PDF and queue it for background ingestion.

    Fast validation happens here (auth, notebook ownership, filename, size,
    magic bytes). The heavy work (Docling → chunk → embed → pgvector) runs in
    Celery workers via RabbitMQ, so this endpoint returns in milliseconds
    with ``status: "processing"``. Poll ``GET /documents`` for completion.
    """

    user = require_user(request)
    # The target notebook must belong to the user (400 when missing, 404 otherwise).
    get_owned_notebook_or_404(notebook_id, user["id"])

    filename = _safe_filename(file.filename)

    # Bounded read: never pull an unbounded body into memory.
    file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
        )
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    # Validate real content via PDF magic bytes, not just the filename/MIME type.
    if not file_bytes.lstrip(b"\x00 \t\r\n")[:5] == b"%PDF-":
        raise HTTPException(
            status_code=400,
            detail="File is not a valid PDF (missing %PDF- header).",
        )
    file_size_kb = len(file_bytes) // 1024

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    db = SessionLocal()
    try:
        # Register the document as processing first; the worker fills in
        # total_pages/chunks and flips it to completed (or failed).
        doc_id = db.execute(
            text(
                "INSERT INTO documents (filename, total_pages, file_size_kb, "
                "notebook_id, status) "
                "VALUES (:filename, 0, :file_size_kb, :notebook_id, "
                "'processing') RETURNING id"
            ),
            {
                "filename": filename,
                "file_size_kb": file_size_kb,
                "notebook_id": notebook_id,
            },
        ).scalar()
        file_path = os.path.join(UPLOAD_DIR, f"{doc_id}.pdf")
        db.execute(
            text("UPDATE documents SET file_path = :fp WHERE id = :id"),
            {"fp": file_path, "id": doc_id},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        db.close()

    try:
        with open(file_path, "wb") as f:
            f.write(file_bytes)
    except Exception as e:
        _mark_upload_failed(doc_id, f"Could not save upload: {e}")
        raise HTTPException(status_code=500, detail="Could not save upload.")

    # Enqueue stage 1 (Docling parse). Imported lazily so the API process
    # never loads the heavy Docling/torch modules at startup.
    try:
        from app.tasks.document_tasks import parse_document

        parse_document.delay(doc_id)
    except Exception as e:
        # Broker down etc: don't leave the row stuck in processing.
        _mark_upload_failed(doc_id, f"Could not queue processing job: {e}")
        raise HTTPException(
            status_code=503, detail="Processing queue unavailable. Try again."
        )

    return {
        "id": doc_id,
        "filename": filename,
        "total_pages": 0,
        "chunk_count": 0,
        "notebook_id": notebook_id,
        "status": "processing",
    }


def _mark_upload_failed(doc_id: int, message: str) -> None:
    """Best-effort terminal state when the upload itself cannot be queued."""
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
    except Exception:
        db.rollback()
    finally:
        db.close()
