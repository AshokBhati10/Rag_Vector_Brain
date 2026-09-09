"""Phase 2: simple relevance handling for retrieved chunks.

Uses the cosine similarity derived from pgvector's cosine distance
(``similarity = 1 - distance``) of the already-retrieved top-5 chunks.
No rescoring, no reranker, no extra model calls.

Threshold rationale (measured live with multi-qa-MiniLM-L6-cos-v1, Phase 2):
  - specific relevant question  -> best-chunk similarity ~0.70-0.76
  - related-domain question     -> best-chunk similarity ~0.42
  - broad summary question      -> best-chunk similarity ~0.15-0.23
  - unrelated questions         -> best-chunk similarity ~0.00-0.02 (rest negative)
0.10 keeps a ~5x margin above unrelated noise while still admitting
broad but legitimate questions (e.g. "summarize the documents").
Borderline cases fall through to the LLM, which is separately
instructed to refuse when the sources lack the answer.
"""

import os

RELEVANCE_THRESHOLD = float(os.getenv("RELEVANCE_THRESHOLD", "0.10"))

NO_RELEVANT_INFO_RESPONSE = (
    "I couldn't find relevant information in the uploaded documents."
)


def chunk_similarity(chunk: dict) -> float:
    """Cosine similarity of a retrieved chunk (pgvector <=> is cosine distance)."""
    return 1.0 - float(chunk["distance"])


def is_relevant(chunks: list[dict], threshold: float = RELEVANCE_THRESHOLD) -> bool:
    """True when the single best chunk meets the similarity threshold.

    Top-5 retrieval itself is unchanged; this only decides whether the
    retrieved context is worth sending to the LLM.
    """
    if not chunks:
        return False
    return max(chunk_similarity(c) for c in chunks) >= threshold
