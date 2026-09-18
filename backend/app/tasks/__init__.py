"""Celery task stages for async PDF ingestion.

Stage 1 (``document_tasks.parse_document``): Docling PDF → pages.
Stage 2 (``embedding_tasks.embed_and_store``): chunk → embed → pgvector.
"""
