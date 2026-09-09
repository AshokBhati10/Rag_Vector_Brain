from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.db.session import SessionLocal

router = APIRouter()


@router.get("/documents")
def list_documents(notebook_id: int | None = None):
    """
    List all documents. When notebook_id is provided, restrict to that notebook.
    Returns id, filename, total_pages, file_size_kb for each document.
    """
    db = SessionLocal()
    try:
        if notebook_id is not None:
            rows = db.execute(
                text(
                    "SELECT id, filename, total_pages, file_size_kb, notebook_id "
                    "FROM documents WHERE notebook_id = :nb ORDER BY uploaded_at ASC"
                ),
                {"nb": notebook_id},
            ).fetchall()
        else:
            rows = db.execute(
                text(
                    "SELECT id, filename, total_pages, file_size_kb, notebook_id "
                    "FROM documents ORDER BY uploaded_at ASC"
                )
            ).fetchall()

        return [
            {
                "id": row.id,
                "filename": row.filename,
                "total_pages": row.total_pages or 0,
                "file_size_kb": row.file_size_kb or 0,
                "notebook_id": row.notebook_id,
            }
            for row in rows
        ]
    finally:
        db.close()


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int):
    """
    Delete a document by ID. Chunks are removed automatically via CASCADE.
    """
    db = SessionLocal()
    try:
        result = db.execute(
            text("DELETE FROM documents WHERE id = :id RETURNING id"),
            {"id": doc_id},
        )
        deleted = result.fetchone()
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found.")
        db.commit()
        return {"deleted": doc_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
