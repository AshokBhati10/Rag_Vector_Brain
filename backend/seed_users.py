"""Seed demo login accounts (assignment/demo helper).

Usage:
    docker compose exec backend python seed_users.py
    # or: python seed_users.py  (with DATABASE_URL set)

Credentials come from the DEMO_USERS environment variable so they are easy
to change later without editing code:

    DEMO_USERS="ashok:ashok123,friend:friend123"

Behavior (idempotent — safe to re-run):
- Creates each user, or updates their password hash if the username exists
  (so changing DEMO_USERS passwords and re-running rotates credentials).
- Assigns any legacy notebooks with no owner (user_id IS NULL) to the FIRST
  demo user, so pre-existing test data stays visible to that account instead
  of becoming orphaned by per-user scoping.

Also called automatically on backend startup (see app.main lifespan).
"""
import os

from sqlalchemy import text

from app.auth import hash_password
from app.db.init_db import init_db
from app.db.session import SessionLocal

DEFAULT_DEMO_USERS = "ashok:ashok123,friend:friend123"


def parse_seed_users(raw: str) -> list[tuple[str, str]]:
    users: list[tuple[str, str]] = []
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        username, password = entry.split(":", 1)
        username, password = username.strip(), password.strip()
        if username and password:
            users.append((username, password))
    return users


def seed_demo_users(raw: str | None = None) -> list[str]:
    entries = parse_seed_users(raw if raw is not None else os.getenv("DEMO_USERS", DEFAULT_DEMO_USERS))
    if not entries:
        print("[SEED] No demo users configured; skipping.")
        return []
    db = SessionLocal()
    try:
        ids: list[int] = []
        for username, password in entries:
            row = db.execute(
                text("SELECT id FROM users WHERE username = :username"),
                {"username": username},
            ).fetchone()
            if row:
                db.execute(
                    text("UPDATE users SET password_hash = :ph WHERE id = :id"),
                    {"ph": hash_password(password), "id": row.id},
                )
                user_id = row.id
            else:
                user_id = db.execute(
                    text(
                        "INSERT INTO users (username, password_hash) "
                        "VALUES (:username, :ph) RETURNING id"
                    ),
                    {"username": username, "ph": hash_password(password)},
                ).scalar()
            ids.append(user_id)
        # Adopt pre-existing ownerless notebooks under the first demo user.
        adopted = db.execute(
            text("UPDATE notebooks SET user_id = :user_id WHERE user_id IS NULL"),
            {"user_id": ids[0]},
        ).rowcount
        db.commit()
        names = [u for u, _ in entries]
        print(f"[SEED] Demo users ready: {names} (adopted {adopted} legacy notebooks).")
        return names
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    seed_demo_users()
