from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import require_user
from app.db.session import SessionLocal

router = APIRouter()


class NotebookCreate(BaseModel):
    name: str


@router.get("/notebooks")
def list_notebooks(request: Request):
    """Return only the logged-in user's notebooks ordered by creation date."""
    user = require_user(request)
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT id, name, created_at FROM notebooks "
                "WHERE user_id = :user_id ORDER BY created_at ASC"
            ),
            {"user_id": user["id"]},
        ).fetchall()
        return [
            {"id": r.id, "name": r.name, "created_at": r.created_at.isoformat()}
            for r in rows
        ]
    finally:
        db.close()


@router.post("/notebooks")
def create_notebook(body: NotebookCreate, request: Request):
    """Create a new notebook owned by the logged-in user and return it."""
    user = require_user(request)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Notebook name cannot be empty.")
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                "INSERT INTO notebooks (name, user_id) VALUES (:name, :user_id) "
                "RETURNING id, name, created_at"
            ),
            {"name": name, "user_id": user["id"]},
        )
        row = result.fetchone()
        db.commit()
        return {"id": row.id, "name": row.name, "created_at": row.created_at.isoformat()}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
