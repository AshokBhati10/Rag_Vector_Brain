import os
import time

from dotenv import load_dotenv
from groq import Groq

from app.services.relevance import NO_RELEVANT_INFO_RESPONSE

load_dotenv()

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

_groq_client: Groq | None = None


def _get_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _groq_client


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------
def build_prompt(question: str, retrieved_chunks: list[dict]) -> str:
    """Construct a grounded RAG prompt with clearly separated source blocks.

    Each of the top-5 chunks keeps its structured metadata (document
    filename + page number) in a deterministic SOURCE block. All chunks
    are included; no truncation is needed (5 x ~400 tokens fits easily
    in the model's context window).
    """
    context_parts = []
    for i, chunk in enumerate(retrieved_chunks, start=1):
        context_parts.append(
            f"SOURCE {i}\n"
            f"Document: {chunk['filename']}\n"
            f"Page: {chunk['page_number']}\n"
            f"Content:\n{chunk['content']}"
        )

    context = "\n\n".join(context_parts)

    return (
        "You are a research assistant. Answer the user's question using ONLY "
        "the retrieved sources provided below. Do not use any outside knowledge. "
        "When you use information from a source, cite it with the ACTUAL "
        "document filename and page number from that source's metadata, "
        "exactly in the form [filename, p. N] — for example, if SOURCE 1 has "
        "Document: report.pdf and Page: 3, cite it as [report.pdf, p. 3]. "
        "Use plain ASCII square brackets. "
        "Never use generic placeholders like [Document, p. N] or "
        "[Source 1, p. N]; always use the real filename.\n\n"

        "If the sources do not contain enough information to answer, "
        "respond exactly with:\n"
        f"\"{NO_RELEVANT_INFO_RESPONSE}\"\n\n"

        "Formatting Rules:\n"
        "- Use clear section headings.\n"
        "- Put every heading on a new line.\n"
        "- Leave one blank line between sections.\n"
        "- Use bullet points whenever possible.\n"
        "- Never return one long paragraph.\n"
        "- Keep comparisons in a structured format.\n\n"

        f"SOURCES:\n{context}\n\n"

        f"QUESTION:\n{question}\n\n"

        "ANSWER:"
    )


# ---------------------------------------------------------------------------
# Groq call with 429 retry
# ---------------------------------------------------------------------------
def call_groq(prompt: str, max_retries: int = 3) -> str:
    """Call Groq API (non-streaming). Retries on 429 with backoff."""
    client = _get_client()

    print("\n--- [GROQ CALL] FULL PROMPT SENT ---")
    print(prompt)
    print("------------------------------------\n")

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=GROQ_MODEL,
                max_tokens=4096,
                temperature=0.2,
                top_p=1,
                stream=False,
            )
            ans = response.choices[0].message.content or ""
            print("\n--- [GROQ CALL] RAW RESPONSE ---")
            print(ans)
            print("--------------------------------\n")
            return ans
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str:
                wait = 15 * (attempt + 1)
                time.sleep(wait)
                continue
            raise

    raise RuntimeError("Groq rate limit exceeded after retries. Try again in a minute.")


def call_groq_stream(prompt: str):
    """Call Groq API (streaming). Yields text deltas."""
    client = _get_client()

    print("\n--- [GROQ STREAM] FULL PROMPT SENT ---")
    print(prompt)
    print("--------------------------------------\n")

    stream = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=GROQ_MODEL,
        max_tokens=4096,
        temperature=0.2,
        top_p=1,
        stream=True,
    )

    print("\n--- [GROQ STREAM] RAW RESPONSE STREAMING START ---")
    for chunk in stream:
        content = chunk.choices[0].delta.content
        if content is not None:
            # Print to backend console so we can see the raw chunk
            print(content, end="", flush=True)
            yield content
    print("\n--- [GROQ STREAM] RAW RESPONSE STREAMING END ---\n")


# ---------------------------------------------------------------------------
# Backwards-compatible aliases (previous Cerebras names)
# ---------------------------------------------------------------------------
call_cerebras = call_groq
call_cerebras_stream = call_groq_stream
