from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.ingest import chunk_text, embed_chunks, parse_pdf

router = APIRouter()


@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    notebook_id: int | None = Form(None),
):
    """Ingest a PDF: parse → chunk → embed → store in Postgres."""

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    file_bytes = await file.read()
    file_size_kb = len(file_bytes) // 1024

    db = SessionLocal()
    try:
        # 1. Parse PDF into page-level text
        pages = parse_pdf(file_bytes)
        total_pages = len(pages)

        # 2. Chunk the text (~400 tokens, ~50 overlap)
        chunks = chunk_text(pages)

        # 3. Embed the chunks (384-dim vectors)
        embeddings = embed_chunks(chunks)

        # 4. Insert document row
        result = db.execute(
            text(
                "INSERT INTO documents (filename, total_pages, file_size_kb, notebook_id) "
                "VALUES (:filename, :total_pages, :file_size_kb, :notebook_id) RETURNING id"
            ),
            {
                "filename": file.filename,
                "total_pages": total_pages,
                "file_size_kb": file_size_kb,
                "notebook_id": notebook_id,
            },
        )
        doc_id = result.scalar()

        # 5. Insert chunk rows with embeddings
        for chunk, embedding in zip(chunks, embeddings):
            db.execute(
                text(
                    "INSERT INTO chunks (document_id, content, page_number, embedding) "
                    "VALUES (:doc_id, :content, :page_number, :embedding)"
                ),
                {
                    "doc_id": doc_id,
                    "content": chunk["content"],
                    "page_number": chunk["page_number"],
                    "embedding": str(embedding),
                },
            )

        db.commit()

        return {
            "id": doc_id,
            "filename": file.filename,
            "total_pages": total_pages,
            "chunk_count": len(chunks),
            "notebook_id": notebook_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    finally:
        db.close()
