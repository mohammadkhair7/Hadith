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
            return q(conn, "SELECT * FROM user_items WHERE user_id=%s AND kind=%s ORDER BY created_at DESC",
                     (user["user_id"], kind))
        return q(conn, "SELECT * FROM user_items WHERE user_id=%s ORDER BY created_at DESC",
                 (user["user_id"],))


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
