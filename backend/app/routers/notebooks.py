from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.db.session import SessionLocal

router = APIRouter()


class NotebookCreate(BaseModel):
    name: str


@router.get("/notebooks")
def list_notebooks():
    """Return all notebooks ordered by creation date."""
    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT id, name, created_at FROM notebooks ORDER BY created_at ASC")
        ).fetchall()
        return [
            {"id": r.id, "name": r.name, "created_at": r.created_at.isoformat()}
            for r in rows
        ]
    finally:
        db.close()


@router.post("/notebooks")
def create_notebook(body: NotebookCreate):
    """Create a new notebook and return it."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Notebook name cannot be empty.")
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                "INSERT INTO notebooks (name) VALUES (:name) "
                "RETURNING id, name, created_at"
            ),
            {"name": name},
        )
        row = result.fetchone()
        db.commit()
        return {"id": row.id, "name": row.name, "created_at": row.created_at.isoformat()}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
