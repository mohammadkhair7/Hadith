"""Hadith translation waterfall (§11.6, approved D11):
1. Kalimat.dev lookup (authenticated sunnah.com-based translations) with a
   normalized-similarity guard against wrong-hadith matches;
2. gemini-2.5-flash fallback (and primary path for non-hadith content).

Rows land in `translations` with src_hash for staleness detection; the
`translation_jobs` ledger makes batches resumable and idempotent."""
import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import settings
from ..db import pool
from .llm import generate_text
from .normalize import normalize_arabic

KALIMAT_URL = "https://api.kalimat.dev/search"
SIMILARITY_THRESHOLD = 0.55
BATCH_SLEEP = 0.15

GEMINI_SYSTEM = """You are a scholarly translator of classical Arabic hadith texts into English.
Rules:
- Faithful, complete rendering; no summarising, no commentary.
- Keep hadith technical terms transliterated with translation on first use when needed
  (isnad, matn, ṣaḥīḥ, ḥasan).
- Render the honorific ﷺ as "(peace be upon him)".
- Keep narrator chains as "X narrated from Y".
- Output ONLY the translation text."""


def src_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _token_overlap(a_norm: str, b_norm: str) -> float:
    ta, tb = set(a_norm.split()), set(b_norm.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


import re as _re

_MATN_MARK = _re.compile(
    r"(قال\s+رسول\s+الله|قال\s+النبي|ان\s+رسول\s+الله|ان\s+النبي|يقول)")


def _matn_of(text_raw: str) -> str:
    """Heuristic matn extraction for the Kalimat query: text from the LAST
    Prophet-speech marker onward (the isnad hurts search recall); falls back
    to the passage tail."""
    norm = normalize_arabic(text_raw)
    last = None
    for m in _MATN_MARK.finditer(norm):
        last = m
    if last and len(norm) - last.start() > 25:
        return norm[last.start():][:600]
    return norm[-500:] if len(norm) > 500 else norm


def kalimat_lookup(matn_ar: str) -> dict[str, Any] | None:
    """Authenticated English for a hadith matn, or None (no match / failed
    similarity guard / API error). URL layout per the reference implementation:
    indexes quotes must be pre-encoded as %22 (§11.6)."""
    if not settings.kalimat_api_key:
        return None
    from urllib.parse import quote
    url = (f"{KALIMAT_URL}?query={quote(matn_ar[:1200], safe='')}"
           f"&numResults=1&getText=2&getTotalResultsNum=1&indexes=[%22sunnah_lk%22]")
    try:
        r = httpx.get(url, headers={"X-Api-Key": settings.kalimat_api_key}, timeout=30)
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception:
        return None

    hits = data.get("results", []) if isinstance(data, dict) else data
    if not hits:
        return None
    hit = hits[0]
    ar = hit.get("matn_ar") or hit.get("text") or ""
    matn_en = (hit.get("matn_en") or "").strip()
    isnad_en = (hit.get("isnad_en") or "").strip()
    en = (isnad_en + " " + matn_en).strip() if matn_en else (hit.get("en_text") or "").strip()
    if not en:
        return None
    # similarity guard: the returned hadith must actually be ours (§11.6 step 2)
    sim = _token_overlap(normalize_arabic(matn_ar), normalize_arabic(ar))
    if sim < SIMILARITY_THRESHOLD:
        return None
    return {"en_text": en,
            "meta": {"kalimat_id": hit.get("id"),
                     "source_book": hit.get("source_book"),
                     "hadith_number": hit.get("hadith_number"),
                     "grade_en": hit.get("grade_en"),
                     "similarity": round(sim, 3)}}


def gemini_translate(text: str, lang: str = "en") -> str:
    target = {"en": "English"}.get(lang, lang)
    return generate_text(
        f"Translate this classical Arabic text into {target}:\n\n{text}",
        system=GEMINI_SYSTEM, temperature=0.1).strip()


def translate_passage(conn, passage_id: int, lang: str = "en",
                      overwrite: bool = False) -> dict[str, Any]:
    """Run the waterfall for one passage; returns {source, status}."""
    p = conn.execute(
        "SELECT passage_id, text_raw, kind FROM passages WHERE passage_id=%s",
        (passage_id,)).fetchone()
    if not p:
        raise ValueError("passage not found")
    h = src_hash(p["text_raw"])

    existing = conn.execute("""
        SELECT src_hash, source FROM translations
        WHERE obj_type='passage' AND obj_id=%s AND field='text' AND lang=%s
    """, (passage_id, lang)).fetchone()
    if existing and not overwrite and existing["src_hash"] == h:
        return {"source": existing["source"], "status": "skipped"}

    source, text, status, meta = None, None, "machine", {}
    if lang == "en" and p["kind"] == "unit":
        k = kalimat_lookup(_matn_of(p["text_raw"]))
        if k:
            source, text, status, meta = "kalimat", k["en_text"], "reviewed", k["meta"]
    if text is None:
        text = gemini_translate(p["text_raw"], lang)
        source = "gemini-2.5-flash"
    if not text:
        raise RuntimeError("empty translation")

    conn.execute("""
        INSERT INTO translations (obj_type, obj_id, field, lang, text, status,
                                  source, src_hash, meta)
        VALUES ('passage', %s, 'text', %s, %s, %s, %s, %s, %s)
        ON CONFLICT (obj_type, obj_id, field, lang)
        DO UPDATE SET text=EXCLUDED.text, status=EXCLUDED.status,
                      source=EXCLUDED.source, src_hash=EXCLUDED.src_hash,
                      meta=EXCLUDED.meta, updated_at=now()
    """, (passage_id, lang, text, status, source,
          h, json.dumps(meta, ensure_ascii=False)))
    conn.commit()
    return {"source": source, "status": "done"}


# --- batch job runner (mirrors embed_jobs) -----------------------------------

_jobs: dict[str, dict[str, Any]] = {}


def job_status(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def list_jobs() -> list[dict]:
    return sorted(_jobs.values(), key=lambda j: j["started_at"], reverse=True)


def cancel_job(job_id: str) -> bool:
    j = _jobs.get(job_id)
    if j and j["status"] == "running":
        j["cancel"] = True
        return True
    return False


def coverage(conn, lang: str = "en") -> list[dict]:
    return conn.execute("""
        SELECT e.edition_id, e.source, e.title_ar, e.passage_count,
               w.kind AS work_kind,
               coalesce(t.total, 0) AS translated,
               coalesce(t.kalimat, 0) AS authenticated,
               coalesce(t.stale, 0) AS stale
        FROM editions e
        JOIN works w USING (work_id)
        LEFT JOIN LATERAL (
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE tr.source='kalimat') AS kalimat,
                   count(*) FILTER (WHERE tr.src_hash IS DISTINCT FROM
                       substr(encode(sha256(convert_to(p.text_raw,'UTF8')),'hex'),1,16)) AS stale
            FROM translations tr
            JOIN passages p ON p.passage_id = tr.obj_id
            WHERE tr.obj_type='passage' AND tr.field='text' AND tr.lang=%s
              AND p.edition_id = e.edition_id
        ) t ON true
        ORDER BY w.kind, e.edition_id
    """, (lang,)).fetchall()


def start_job(edition_ids: list[int], lang: str = "en", mode: str = "skip",
              limit: int | None = None, started_by: str = "") -> str:
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "job_id": job_id, "edition_ids": edition_ids, "lang": lang, "mode": mode,
        "limit": limit, "status": "running", "done": 0, "total": None,
        "kalimat": 0, "gemini": 0, "skipped": 0, "errors": 0, "cancel": False,
        "started_by": started_by,
        "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None,
        "error": None,
    }
    threading.Thread(target=_run, args=(job_id,), daemon=True).start()
    return job_id


def _run(job_id: str) -> None:
    import time
    j = _jobs[job_id]
    try:
        with pool.connection() as conn:
            rows = conn.execute(
                "SELECT passage_id FROM passages WHERE edition_id = ANY(%s) "
                "ORDER BY edition_id, seq" + (f" LIMIT {int(j['limit'])}" if j["limit"] else ""),
                (j["edition_ids"],)).fetchall()
        j["total"] = len(rows)
        for r in rows:
            if j["cancel"]:
                break
            try:
                with pool.connection() as conn:
                    res = translate_passage(conn, r["passage_id"], j["lang"],
                                            overwrite=(j["mode"] == "overwrite"))
                if res["status"] == "skipped":
                    j["skipped"] += 1
                elif res["source"] == "kalimat":
                    j["kalimat"] += 1
                else:
                    j["gemini"] += 1
            except Exception:
                j["errors"] += 1
            j["done"] += 1
            time.sleep(BATCH_SLEEP)
        j["status"] = "cancelled" if j["cancel"] else "done"
    except Exception as e:
        j["status"] = "failed"
        j["error"] = f"{type(e).__name__}: {e}"
    finally:
        j["finished_at"] = datetime.now(timezone.utc).isoformat()
