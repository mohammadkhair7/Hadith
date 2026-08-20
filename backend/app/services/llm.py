"""Thin Gemini helper: JSON-mode generation with retries. Default model is
settings.llm_model; callers may request another (e.g. settings.nl_query_model
for NL2SQL/NL2CYPHER), which falls back to llm_model when unavailable."""
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


def _model_unavailable(e: Exception) -> bool:
    s = str(e)
    return "NOT_FOUND" in s or "404" in s or "not found" in s.lower()


def generate_json(prompt: str, *, system: str | None = None,
                  temperature: float = 0.1, retries: int = 2,
                  model: str | None = None) -> dict:
    cfg = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        system_instruction=system,
    )
    models = [model or settings.llm_model]
    if model and model != settings.llm_model:
        models.append(settings.llm_model)
    last: Exception | None = None
    for m in models:
        for attempt in range(retries + 1):
            try:
                resp = client().models.generate_content(
                    model=m, contents=prompt, config=cfg)
                return json.loads(resp.text)
            except Exception as e:
                last = e
                if _model_unavailable(e):
                    break  # skip retries, move to the fallback model
                time.sleep(1.5 * (attempt + 1))
    raise last  # type: ignore[misc]


def generate_text(prompt: str, *, system: str | None = None,
                  temperature: float = 0.3) -> str:
    cfg = types.GenerateContentConfig(temperature=temperature,
                                      system_instruction=system)
    resp = client().models.generate_content(
        model=settings.llm_model, contents=prompt, config=cfg)
    return resp.text or ""
