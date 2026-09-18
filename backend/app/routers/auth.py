from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import (
    SESSION_COOKIE,
    SESSION_TTL,
    create_session,
    destroy_session,
    get_session_user,
    hash_password,
    validate_new_credentials,
    verify_password,
)
from app.db.session import SessionLocal

router = APIRouter(prefix="/auth")


class LoginBody(BaseModel):
    username: str
    password: str


class RegisterBody(BaseModel):
    username: str
    password: str


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=int(SESSION_TTL.total_seconds()),
    )


@router.post("/register", status_code=201)
def register(body: RegisterBody, response: Response):
    """Create an account and log straight in. Never returns a password."""
    username = validate_new_credentials(body.username, body.password)
    db = SessionLocal()
    try:
        existing = db.execute(
            text("SELECT id FROM users WHERE username = :username"),
            {"username": username},
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Username is already taken.")
        user_id = db.execute(
            text(
                "INSERT INTO users (username, password_hash) "
                "VALUES (:username, :password_hash) RETURNING id"
            ),
            {"username": username, "password_hash": hash_password(body.password)},
        ).scalar()
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")
    finally:
        db.close()
    _set_session_cookie(response, create_session(user_id))
    return {"id": user_id, "username": username}


@router.post("/login")
def login(body: LoginBody, response: Response):
    """Verify credentials, mint a session cookie. Never returns a password."""
    username = (body.username or "").strip()
    if not username or not body.password:
        raise HTTPException(status_code=400, detail="Username and password are required.")
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT id, username, password_hash FROM users WHERE username = :username"),
            {"username": username},
        ).fetchone()
    finally:
        db.close()
    if not row or not verify_password(body.password, row.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    _set_session_cookie(response, create_session(row.id))
    return {"id": row.id, "username": row.username}


@router.post("/logout")
def logout(request: Request, response: Response):
    """Revoke the session cookie (server-side + client-side)."""
    destroy_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    """Return the logged-in user, or 401 when unauthenticated."""
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user
