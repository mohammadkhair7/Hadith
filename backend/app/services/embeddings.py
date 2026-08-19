"""Gemini embedding client — gemini-embedding-001 @ 768-d (§7.1).
Tashkeel is preserved in embedded text (it carries meaning)."""
import time

from google import genai
from google.genai import types

from ..config import settings

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def embed_texts(texts: list[str], *, task_type: str = "RETRIEVAL_DOCUMENT",
                retries: int = 3) -> list[list[float]]:
    """Embed up to 100 texts per API call. Returns 768-d float vectors."""
    out: list[list[float]] = []
    cfg = types.EmbedContentConfig(
        task_type=task_type,
        output_dimensionality=settings.embedding_dimensions,
    )
    for i in range(0, len(texts), 100):
        batch = texts[i:i + 100]
        for attempt in range(retries):
            try:
                resp = client().models.embed_content(
                    model=settings.embedding_model, contents=batch, config=cfg)
                out.extend([e.values for e in resp.embeddings])
                break
            except Exception:
                if attempt == retries - 1:
                    raise
                time.sleep(2 ** attempt * 2)
    return out


def embed_query(text: str) -> list[float]:
    return embed_texts([text], task_type="RETRIEVAL_QUERY")[0]


def chunk_text(text: str, max_chars: int = 1500, overlap: int = 200) -> list[str]:
    """Split a passage into ≤max_chars chunks with overlap, preferring
    whitespace boundaries (§7.1)."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            ws = text.rfind(" ", start + max_chars - 300, end)
            if ws > start:
                end = ws
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]
