import os

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from app.auth import get_owned_notebook_or_404, require_user
from app.db.session import SessionLocal

router = APIRouter()

_DOC_FIELDS = (
    "id, filename, total_pages, file_size_kb, notebook_id, "
    "COALESCE(status, 'completed') AS status, error_message"
)


def _doc_to_dict(row) -> dict:
    return {
        "id": row.id,
        "filename": row.filename,
        "total_pages": row.total_pages or 0,
        "file_size_kb": row.file_size_kb or 0,
        "notebook_id": row.notebook_id,
        "status": row.status or "completed",
        "error_message": row.error_message,
    }


@router.get("/documents")
def list_documents(request: Request, notebook_id: int | None = None):
    """
    List the logged-in user's documents. When notebook_id is provided it must
    belong to the user (else 404); otherwise documents across all of the
    user's own notebooks are returned.
    Each document carries its async-ingestion ``status`` (processing /
    completed / failed) plus an ``error_message`` when failed, so the
    frontend can show progress by polling this endpoint.
    """
    user = require_user(request)
    db = SessionLocal()
    try:
        if notebook_id is not None:
            get_owned_notebook_or_404(notebook_id, user["id"])
            rows = db.execute(
                text(
                    f"SELECT {_DOC_FIELDS} "
                    "FROM documents WHERE notebook_id = :nb ORDER BY uploaded_at ASC"
                ),
                {"nb": notebook_id},
            ).fetchall()
        else:
            rows = db.execute(
                text(
                    "SELECT d.id, d.filename, d.total_pages, d.file_size_kb, "
                    "d.notebook_id, COALESCE(d.status, 'completed') AS status, "
                    "d.error_message "
                    "FROM documents d JOIN notebooks n ON n.id = d.notebook_id "
                    "WHERE n.user_id = :user_id ORDER BY d.uploaded_at ASC"
                ),
                {"user_id": user["id"]},
            ).fetchall()

        return [_doc_to_dict(row) for row in rows]
    finally:
        db.close()


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, request: Request):
    """
    Delete a document by ID, only when it sits in the logged-in user's
    notebook (else 404). Chunks are removed automatically via CASCADE.
    """
    user = require_user(request)
    db = SessionLocal()
    try:
        owner = db.execute(
            text(
                "SELECT d.id, d.file_path FROM documents d "
                "JOIN notebooks n ON n.id = d.notebook_id "
                "WHERE d.id = :id AND n.user_id = :user_id"
            ),
            {"id": doc_id, "user_id": user["id"]},
        ).fetchone()
        if not owner:
            raise HTTPException(status_code=404, detail="Document not found.")
        result = db.execute(
            text("DELETE FROM documents WHERE id = :id RETURNING id"),
            {"id": doc_id},
        )
        deleted = result.fetchone()
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found.")
        db.commit()
        # Best-effort cleanup of the saved upload. A queued worker task that
        # fires afterwards finds no row and exits quietly (no orphan chunks).
        if owner.file_path:
            try:
                os.remove(owner.file_path)
            except OSError:
                pass
        return {"deleted": doc_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
