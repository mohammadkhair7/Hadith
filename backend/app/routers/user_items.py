import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import db, q
from ..services.auth import current_user

router = APIRouter(prefix="/me/items", tags=["user items"])


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
    number and the opening words so the account listing is recognizable."""
    pids = {int(i["ref"]["passage_id"]) for i in items
            if isinstance(i.get("ref"), dict) and i["ref"].get("passage_id")}
    if not pids:
        return
    rows = q(conn, r"""
        SELECT p.passage_id, p.hadith_num,
               w.title_ar AS work_title,
               regexp_replace(left(p.text_raw, 600), '\s+', ' ', 'g') AS excerpt
        FROM passages p
        JOIN editions e USING (edition_id)
        JOIN works w USING (work_id)
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
                "snippet": " ".join((r["excerpt"] or "").split()[:15]),
            }


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
