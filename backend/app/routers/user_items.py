import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import db, q
from ..services.auth import current_user

router = APIRouter(prefix="/me/items", tags=["user items"])

# diacritic-tolerant Prophet-speech markers, applied to the RAW text (the
# stored offsets machinery may not have annotated the passage yet)
_DIA = "[\u064b-\u0652\u0670\u0640]*"


def _tol(word: str) -> str:
    return _DIA.join(re.escape(c) for c in word) + _DIA


def _phrase(p: str) -> str:
    return r"\s+".join(_tol(w) for w in p.split())


_MATN_MARK = re.compile("(?:" + "|".join([
    _phrase("قال رسول الله"), _phrase("قالت رسول الله"),
    _phrase("قال النبي"),
    "[اأإ]" + _tol("ن") + r"\s+" + _phrase("رسول الله"),
    "[اأإ]" + _tol("ن") + r"\s+" + _phrase("النبي"),
    _phrase("سمعت رسول الله"), _phrase("يقول"),
]) + ")")


class ItemBody(BaseModel):
    kind: str            # favourite | note | saved_search
    ref: dict
    body: str | None = None


@router.get("")
def list_items(kind: str | None = None, user: dict = Depends(current_user)):
    with db() as conn:
        if kind:
            items = q(conn, "SELECT * FROM user_items WHERE user_id=%s AND kind=%s ORDER BY created_at DESC",
                      (user["user_id"], kind))
        else:
            items = q(conn, "SELECT * FROM user_items WHERE user_id=%s ORDER BY created_at DESC",
                      (user["user_id"],))
        _attach_passage_hints(conn, items)
        return items


def _attach_passage_hints(conn, items: list[dict]) -> None:
    """Favorites/notes only store a passage ref; attach book title, hadith
    number and the opening MATN words (the sanad is skipped so the hint shows
    what the hadith says, not who transmitted it)."""
    pids = {int(i["ref"]["passage_id"]) for i in items
            if isinstance(i.get("ref"), dict) and i["ref"].get("passage_id")}
    if not pids:
        return
    rows = q(conn, """
        SELECT p.passage_id, p.hadith_num,
               w.title_ar AS work_title,
               left(p.text_raw, 6000) AS excerpt,
               b.sanad_end_raw,
               st.spans
        FROM passages p
        JOIN editions e USING (edition_id)
        JOIN works w USING (work_id)
        LEFT JOIN LATERAL (
            SELECT c.sanad_end_raw FROM isnad_chains c
            WHERE c.passage_id = p.passage_id AND c.sanad_end_raw IS NOT NULL
            ORDER BY c.confidence DESC LIMIT 1
        ) b ON true
        LEFT JOIN LATERAL (
            SELECT a.payload->'spans' AS spans FROM passage_annotations a
            WHERE a.passage_id = p.passage_id AND a.layer='structure'
              AND a.engine='neural-indexing'
            ORDER BY a.version DESC LIMIT 1
        ) st ON true
        WHERE p.passage_id = ANY(%s)
    """, (list(pids),))
    info = {r["passage_id"]: r for r in rows}
    for i in items:
        ref = i.get("ref")
        if not (isinstance(ref, dict) and ref.get("passage_id")):
            continue
        r = info.get(int(ref["passage_id"]))
        if r:
            i["passage"] = {
                "hadith_num": r["hadith_num"],
                "work_title": r["work_title"],
                "snippet": _matn_snippet(r["excerpt"] or "",
                                         r["sanad_end_raw"], r["spans"]),
            }


def _matn_snippet(text: str, sanad_end: int | None, spans, n_words: int = 20) -> str:
    """First ~20 words of the matn: prefer the extracted isnad boundary
    (aljam3 units), else the first neural MATN span (shamela pages), else the
    last Prophet-speech marker, else the passage opening."""
    start = 0
    if sanad_end and 0 < sanad_end < len(text):
        start = sanad_end
    elif isinstance(spans, list) and any(
            isinstance(s, list) and len(s) == 3 and s[2] == "MATN"
            and 0 <= s[0] < len(text) for s in spans):
        start = next(s[0] for s in spans
                     if isinstance(s, list) and len(s) == 3
                     and s[2] == "MATN" and 0 <= s[0] < len(text))
    elif "§" in text:
        # Shamela editions mark the matn start with «§»
        start = text.index("§") + 1
    else:
        last = None
        for m in _MATN_MARK.finditer(text):
            last = m
        if last and len(text) - last.start() > 30:
            start = last.start()
    words = text[start:].replace("§", "").split()
    snip = " ".join(words[:n_words])
    return snip + (" …" if len(words) > n_words else "")


@router.post("")
def add_item(item: ItemBody, user: dict = Depends(current_user)):
    if item.kind not in ("favourite", "note", "saved_search"):
        raise HTTPException(400, "unknown item kind")
    with db() as conn:
        row = conn.execute(
            "INSERT INTO user_items (user_id, kind, ref, body) VALUES (%s,%s,%s,%s) RETURNING *",
            (user["user_id"], item.kind, json.dumps(item.ref, ensure_ascii=False), item.body),
        ).fetchone()
        conn.commit()
    return row


@router.delete("/{item_id}")
def delete_item(item_id: int, user: dict = Depends(current_user)):
    with db() as conn:
        row = conn.execute(
            "DELETE FROM user_items WHERE item_id=%s AND user_id=%s RETURNING item_id",
            (item_id, user["user_id"]),
        ).fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, "item not found")
    return {"deleted": item_id}
