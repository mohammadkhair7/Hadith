"""Arabic linguistic frame for NL2CYPHER (§12.3): pure-Python query-time
subset — normalization + transmission-verb intent + narrator-alias lexicon
grounding + book-title grounding. Additive context, never a gate; the heavier
engine layers (Farasa/CAMeL) enrich this at batch time, not query time (§12.5)."""
import re
from typing import Any

from .normalize import normalize_arabic

_TRANSMISSION = re.compile(
    r"\b(روي|يروي|رووا|روت|حدث|حدثنا|حدثني|اخبر|اخبرنا|انبا|سمع|عن|تلميذ|شيخ|اسناد|سند)\b")
_STOPWORDS = {"من", "عن", "في", "علي", "الي", "ما", "هل", "كم", "اي", "الذي",
              "التي", "الذين", "و", "ثم", "قال", "بن", "ابن", "ابو", "ام"}


def build_frame(conn, question: str) -> dict[str, Any] | None:
    """Entities (narrator candidates), relation intent, and work references
    extracted from the question. Returns None when nothing resolves."""
    qnorm = normalize_arabic(question)

    relation = None
    verbs = _TRANSMISSION.findall(qnorm)
    if verbs:
        relation = {"intent": "NARRATED_FROM", "verbs": sorted(set(verbs))}

    entities = _resolve_narrators(conn, qnorm)
    works = _resolve_works(conn, qnorm)

    if not (relation or entities or works):
        return None
    return {"entities": entities, "relation": relation, "works": works}


def _resolve_narrators(conn, qnorm: str) -> list[dict]:
    """Slide n-grams (4..2 words) over the question and match them against the
    narrator alias lexicon; longest match wins per span."""
    words = qnorm.split()
    found: list[dict] = []
    used: set[int] = set()
    for size in (4, 3, 2):
        for i in range(len(words) - size + 1):
            if any(j in used for j in range(i, i + size)):
                continue
            gram = " ".join(words[i:i + size])
            if all(w in _STOPWORDS for w in words[i:i + size]):
                continue
            rows = conn.execute("""
                SELECT DISTINCT n.narrator_id, n.canonical_ar
                FROM narrator_aliases a JOIN narrators n USING (narrator_id)
                WHERE a.alias_norm = %s LIMIT 3
            """, (gram,)).fetchall()
            if rows:
                found.append({"mention": gram,
                              "candidates": [{"narrator_id": r["narrator_id"],
                                              "name": r["canonical_ar"]} for r in rows]})
                used.update(range(i, i + size))
    return found


def _resolve_works(conn, qnorm: str) -> list[dict]:
    rows = conn.execute("""
        SELECT work_id, title_ar FROM works
        WHERE %s LIKE '%%' || title_norm || '%%'
           OR (length(title_norm) > 8 AND title_norm LIKE '%%' || %s || '%%')
        ORDER BY length(title_norm) DESC LIMIT 3
    """, (qnorm, qnorm)).fetchall()
    return [{"work_id": r["work_id"], "title": r["title_ar"]} for r in rows]
