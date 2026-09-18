"""Minimal session/cookie authentication (assignment/demo grade).

- Passwords: PBKDF2-HMAC-SHA256 via stdlib ``hashlib`` (no new dependencies).
- Sessions: opaque random tokens stored in the ``sessions`` table, carried in
  an HttpOnly SameSite=Lax cookie. No JWT, no refresh tokens, no OAuth.

All data access stays scoped through notebooks: a user owns notebooks
(``notebooks.user_id``), and documents / messages / chunks / cache rows all
belong to a notebook, so enforcing notebook ownership isolates everything.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import text

from app.db.session import SessionLocal

SESSION_COOKIE = "vb_session"
SESSION_TTL = timedelta(days=30)

_PBKDF2_ALGO = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    """Hash a password with a fresh random salt. Never store plain text."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{_PBKDF2_ALGO}${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time password check against a stored hash."""
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != _PBKDF2_ALGO:
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


_USERNAME_PATTERN = r"[A-Za-z0-9_.-]+"


def validate_new_credentials(username: str, password: str) -> str:
    """Validate a registration username/password. Returns the cleaned username.

    Rules (lightweight, assignment-grade): 3–32 chars, letters/digits plus
    ``_ . -``; password at least 4 chars. Raises 400 otherwise.
    """
    import re

    cleaned = (username or "").strip()
    if not (3 <= len(cleaned) <= 32) or not re.fullmatch(_USERNAME_PATTERN, cleaned):
        raise HTTPException(
            status_code=400,
            detail="Username must be 3–32 characters (letters, digits, _ . -).",
        )
    if not password or len(password) < 4:
        raise HTTPException(
            status_code=400, detail="Password must be at least 4 characters."
        )
    return cleaned


def create_session(user_id: int) -> str:
    """Mint an opaque session token for a user (cleans up expired rows)."""
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + SESSION_TTL
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM sessions WHERE expires_at < now()"))
        db.execute(
            text(
                "INSERT INTO sessions (token, user_id, expires_at) "
                "VALUES (:token, :user_id, :expires)"
            ),
            {"token": token, "user_id": user_id, "expires": expires},
        )
        db.commit()
        return token
    finally:
        db.close()


def destroy_session(token: str | None) -> None:
    """Revoke a session token (logout). No-op when missing."""
    if not token:
        return
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM sessions WHERE token = :token"), {"token": token})
        db.commit()
    finally:
        db.close()


def get_session_user(request: Request) -> dict | None:
    """Return ``{"id", "username"}`` for a valid session cookie, else None."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT u.id, u.username FROM sessions s "
                "JOIN users u ON u.id = s.user_id "
                "WHERE s.token = :token AND s.expires_at > now()"
            ),
            {"token": token},
        ).fetchone()
        if not row:
            return None
        return {"id": row.id, "username": row.username}
    finally:
        db.close()


def require_user(request: Request) -> dict:
    """FastAPI-style guard: 401 when the request has no valid session."""
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user


def get_owned_notebook_or_404(notebook_id: int | None, user_id: int) -> dict:
    """Return the notebook if it belongs to the user, else 404.

    A missing notebook_id is a 400 (callers that reach here operate on one
    specific notebook). Using 404 for foreign notebooks avoids leaking
    other users' notebook existence.
    """
    if notebook_id is None:
        raise HTTPException(status_code=400, detail="notebook_id is required.")
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT id, name FROM notebooks WHERE id = :id AND user_id = :user_id"),
            {"id": notebook_id, "user_id": user_id},
        ).fetchone()
    finally:
        db.close()
    if not row:
        raise HTTPException(status_code=404, detail="Notebook not found.")
    return {"id": row.id, "name": row.name}


def check_document_ids_or_404(user_id: int, document_ids: list[int] | None) -> None:
    """Raise 404 if any requested document is outside the user's notebooks."""
    if not document_ids:
        return
    unique_ids = sorted(set(document_ids))
    ids_param = "{" + ",".join(str(i) for i in unique_ids) + "}"
    db = SessionLocal()
    try:
        count = db.execute(
            text(
                "SELECT COUNT(*) FROM documents d "
                "JOIN notebooks n ON n.id = d.notebook_id "
                "WHERE d.id = ANY(CAST(:ids AS INT[])) AND n.user_id = :user_id"
            ),
            {"ids": ids_param, "user_id": user_id},
        ).scalar()
    finally:
        db.close()
    if count != len(unique_ids):
        raise HTTPException(status_code=404, detail="Document not found.")
