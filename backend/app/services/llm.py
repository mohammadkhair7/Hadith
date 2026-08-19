"""Thin gemini-2.5-flash helper: JSON-mode generation with retries."""
import json
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


def generate_json(prompt: str, *, system: str | None = None,
                  temperature: float = 0.1, retries: int = 2) -> dict:
    cfg = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        system_instruction=system,
    )
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = client().models.generate_content(
                model=settings.llm_model, contents=prompt, config=cfg)
            return json.loads(resp.text)
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last  # type: ignore[misc]


def generate_text(prompt: str, *, system: str | None = None,
                  temperature: float = 0.3) -> str:
    cfg = types.GenerateContentConfig(temperature=temperature,
                                      system_instruction=system)
    resp = client().models.generate_content(
        model=settings.llm_model, contents=prompt, config=cfg)
    return resp.text or ""
