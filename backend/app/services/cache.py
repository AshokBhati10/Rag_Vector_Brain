import json
from sqlalchemy import text
from app.db.session import SessionLocal

# Threshold for semantic similarity.
# pgvector <=> operator computes Cosine Distance.
# Cosine Similarity = 1 - Cosine Distance.
# For similarity >= 0.92, distance must be <= 0.08.
SIMILARITY_THRESHOLD = 0.85


def check_cache(
    question_embedding: list[float],
    document_ids: list[int] | None = None,
    notebook_id: int | None = None,
) -> dict | None:
    """
    Checks the semantic cache for a similar question under the same notebook and document selection.
    Returns the cached {answer, sources} if found, otherwise None.
    """
    db = SessionLocal()
    try:
        # Sort document IDs to ensure array equality is order-insensitive
        sorted_docs = sorted(document_ids) if document_ids else None

        params = {
            "embedding": str(question_embedding),
            "max_distance": float(1.0 - SIMILARITY_THRESHOLD),
        }

        filters = []
        if notebook_id is not None:
            filters.append("notebook_id = :notebook_id")
            params["notebook_id"] = notebook_id
        else:
            filters.append("notebook_id IS NULL")

        if sorted_docs is not None:
            params["doc_ids"] = "{" + ",".join(str(i) for i in sorted_docs) + "}"
            filters.append("document_ids = CAST(:doc_ids AS INT[])")
        else:
            filters.append("document_ids IS NULL")

        where_clause = " AND ".join(filters)

        sql = f"""
            SELECT answer, sources, (question_embedding <=> cast(:embedding AS vector)) AS distance
            FROM query_cache
            WHERE {where_clause} AND (question_embedding <=> cast(:embedding AS vector)) <= :max_distance
            ORDER BY distance ASC
            LIMIT 1
        """

        row = db.execute(text(sql), params).fetchone()
        if row:
            similarity = 1.0 - float(row.distance)
            print(f"\n[CACHE HIT] Found match with similarity={similarity:.4f} (threshold={SIMILARITY_THRESHOLD})")
            return {
                "answer": row.answer,
                "sources": json.loads(row.sources) if isinstance(row.sources, str) else row.sources,
            }
        
        print("\n[CACHE MISS] No semantically similar question found in cache.")
        return None
    finally:
        db.close()


def store_cache(
    question: str,
    question_embedding: list[float],
    answer: str,
    sources: list[dict],
    document_ids: list[int] | None = None,
    notebook_id: int | None = None,
) -> None:
    """
    Stores a query, its embedding, and the generated answer/sources in the cache.
    """
    db = SessionLocal()
    try:
        # Sort document IDs for consistent array ordering
        sorted_docs = sorted(document_ids) if document_ids else None

        params = {
            "notebook_id": notebook_id,
            "question": question,
            "embedding": str(question_embedding),
            "answer": answer,
            "sources": json.dumps(sources),
            "doc_ids": sorted_docs,  # SQLAlchemy handles list parameter to postgres array
        }

        sql = """
            INSERT INTO query_cache (notebook_id, question, question_embedding, answer, sources, document_ids)
            VALUES (:notebook_id, :question, cast(:embedding AS vector), :answer, cast(:sources AS jsonb), :doc_ids)
        """
        db.execute(text(sql), params)
        db.commit()
        print(f"[CACHE STORE] Question cached: '{question}'")
    except Exception as e:
        db.rollback()
        print(f"[CACHE ERROR] Failed to store cache: {str(e)}")
    finally:
        db.close()
