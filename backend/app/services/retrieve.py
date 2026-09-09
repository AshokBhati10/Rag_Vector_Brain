from sqlalchemy import text

from app.services.ingest import _embedding_model
from app.db.session import SessionLocal


def preprocess_query(question: str) -> str:
    """Light cleanup before embedding: strip ends, collapse internal whitespace.

    Only normalizes formatting — the user's meaning is preserved, and the
    original (stripped) question is still used for answer generation.
    """
    return " ".join(question.strip().split())


def embed_query(text_input: str) -> list[float]:
    """Embed a query string using the shared embedding model instance (384-dim)."""
    embedding = _embedding_model.encode([text_input])
    return embedding[0].tolist()


def search_chunks(
    query_embedding: list[float],
    limit: int = 5,
    document_ids: list[int] | None = None,
    notebook_id: int | None = None,
) -> list[dict]:
    """
    Find the nearest chunks to the query embedding using pgvector cosine distance (<=>).
    Optionally filters by a list of document_ids or a notebook_id.
    """
    db = SessionLocal()
    try:
        filters: list[str] = []
        params: dict = {"embedding": str(query_embedding), "limit": limit}

        if notebook_id is not None:
            filters.append("d.notebook_id = :notebook_id")
            params["notebook_id"] = notebook_id

        if document_ids:
            params["doc_ids"] = "{" + ",".join(str(i) for i in document_ids) + "}"
            filters.append("d.id = ANY(CAST(:doc_ids AS INT[]))")

        where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""

        sql = f"""
            SELECT
                c.content,
                d.filename,
                d.id AS document_id,
                c.page_number,
                c.embedding <=> cast(:embedding AS vector) AS distance
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            {where_clause}
            ORDER BY distance ASC
            LIMIT :limit
        """

        print(f"\n--- [SEARCH CHUNKS] PARAMS: notebook_id={notebook_id}, document_ids={document_ids} ---")
        print(f"SQL QUERY:\n{sql}")
        print(f"PARAMS: { {k: (v if k != 'embedding' else '[vector...]') for k, v in params.items()} }")

        rows = db.execute(text(sql), params).fetchall()

        print(f"RETRIEVED {len(rows)} CHUNKS:")
        for idx, r in enumerate(rows):
            print(f"  [{idx + 1}] File: {r.filename} (ID: {r.document_id}), Page: {r.page_number}, Distance: {r.distance:.4f}")
            print(f"      Snippet: {r.content[:150]}...")
        print("-----------------------------------------------------------------\n")

        return [
            {
                "content": row.content,
                "filename": row.filename,
                "document_id": row.document_id,
                "page_number": row.page_number,
                "distance": float(row.distance),
            }
            for row in rows
        ]
    finally:
        db.close()
