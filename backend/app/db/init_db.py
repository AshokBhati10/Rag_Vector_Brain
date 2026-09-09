import pathlib

from sqlalchemy import text

from app.db.session import engine

SCHEMA_PATH = pathlib.Path(__file__).parent / "schema.sql"


def init_db() -> None:
    """Execute schema.sql against the database. Idempotent — safe to run on every boot."""
    sql = SCHEMA_PATH.read_text()
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()
