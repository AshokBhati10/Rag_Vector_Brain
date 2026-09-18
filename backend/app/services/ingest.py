import os
import tempfile

import tiktoken
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Embedding configuration (Phase 1 requirement: 384-dim vectors)
# ---------------------------------------------------------------------------
EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/multi-qa-MiniLM-L6-cos-v1"
)
EMBEDDING_DIM = 384

# ---------------------------------------------------------------------------
# Module-level singletons (loaded once, not per-request)
# ---------------------------------------------------------------------------
_embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
_tokenizer = tiktoken.get_encoding("cl100k_base")
_converter: DocumentConverter | None = None


def _get_converter() -> DocumentConverter:
    """Lazily build (once) and reuse the Docling PDF converter.

    Constructing a DocumentConverter initializes the whole PDF pipeline, which
    takes tens of seconds. Building it per upload pushed normal ingestions
    past the reverse-proxy read timeout, so the proxy returned 504 while the
    backend still committed — the client showed "Upload failed" even though
    the document landed in the database. Parsing behavior is unchanged.
    """
    global _converter
    if _converter is None:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False
        _converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
    return _converter


# ---------------------------------------------------------------------------
# 1. PDF parsing
# ---------------------------------------------------------------------------
def parse_pdf(file_bytes: bytes) -> list[dict]:
    """Parse a PDF into a list of ``{text, page_number}`` dicts via Docling,
    preserving page boundaries."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        result = _get_converter().convert(tmp_path)
        doc = result.document

        pages_dict: dict[int, list[str]] = {}
        for item, _level in doc.iterate_items():
            if hasattr(item, "text") and item.text:
                page_no = item.prov[0].page_no if item.prov else 1
                pages_dict.setdefault(page_no, []).append(item.text)

        return [
            {"text": "\n".join(pages_dict[pg]), "page_number": pg}
            for pg in sorted(pages_dict)
        ]
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# 2. Token-aware chunking
# ---------------------------------------------------------------------------
def chunk_text(
    pages: list[dict], chunk_size: int = 400, overlap: int = 50
) -> list[dict]:
    """Split page texts into ~400-token chunks with ~50-token overlap.

    Each chunk keeps its source ``page_number`` — the page it *starts* on.
    """
    all_tokens: list[int] = []
    token_page: list[int] = []

    for page in pages:
        tokens = _tokenizer.encode(page["text"])
        all_tokens.extend(tokens)
        token_page.extend([page["page_number"]] * len(tokens))

    chunks: list[dict] = []
    start = 0
    while start < len(all_tokens):
        end = min(start + chunk_size, len(all_tokens))
        chunk_tokens = all_tokens[start:end]
        chunks.append(
            {
                "content": _tokenizer.decode(chunk_tokens),
                "page_number": token_page[start],
            }
        )
        if end >= len(all_tokens):
            break
        start += chunk_size - overlap

    return chunks


# ---------------------------------------------------------------------------
# 3. Embedding
# ---------------------------------------------------------------------------
def embed_chunks(chunks: list[dict]) -> list[list[float]]:
    """Return 384-dim vectors for each chunk using multi-qa-MiniLM-L6-cos-v1."""
    texts = [c["content"] for c in chunks]
    embeddings = _embedding_model.encode(texts)
    return embeddings.tolist()
