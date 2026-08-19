from fastapi import APIRouter, HTTPException

from ..db import db, q, q1
from ..services.normalize import normalize_arabic

router = APIRouter(tags=["subjects"])


@router.get("/subjects/tree")
def subjects_tree(parent_id: int | None = None, search: str | None = None, limit: int = 200):
    with db() as conn:
        if search:
            rows = q(conn, """
                SELECT subject_id, parent_id, title, is_leaf,
                       (SELECT count(*) FROM subject_links sl WHERE sl.subject_id=s.subject_id) AS passages
                FROM subjects s
                WHERE title_norm LIKE '%%' || %s || '%%'
                ORDER BY length(title) LIMIT %s
            """, (normalize_arabic(search), min(limit, 500)))
        elif parent_id is None:
            rows = q(conn, """
                SELECT subject_id, parent_id, title, is_leaf,
                       EXISTS (SELECT 1 FROM subjects c WHERE c.parent_id=s.subject_id) AS has_children
                FROM subjects s WHERE parent_id IS NULL
                ORDER BY ord, subject_id LIMIT %s
            """, (min(limit, 500),))
        else:
            rows = q(conn, """
                SELECT subject_id, parent_id, title, is_leaf,
                       EXISTS (SELECT 1 FROM subjects c WHERE c.parent_id=s.subject_id) AS has_children,
                       (SELECT count(*) FROM subject_links sl WHERE sl.subject_id=s.subject_id) AS passages
                FROM subjects s WHERE parent_id=%s
                ORDER BY ord, subject_id LIMIT %s
            """, (parent_id, min(limit, 500)))
    return rows


@router.get("/subjects/{subject_id}/passages")
def subject_passages(subject_id: int, limit: int = 20, offset: int = 0):
    with db() as conn:
        s = q1(conn, "SELECT subject_id, title FROM subjects WHERE subject_id=%s", (subject_id,))
        if not s:
            raise HTTPException(404, "subject not found")
        total = q1(conn, "SELECT count(*) AS n FROM subject_links WHERE subject_id=%s",
                   (subject_id,))["n"]
        rows = q(conn, """
            SELECT p.passage_id, p.edition_id, p.hadith_num, p.kind,
                   left(p.text_raw, 400) AS preview,
                   e.title_ar AS edition_title, w.title_ar AS work_title
            FROM subject_links sl
            JOIN passages p USING (passage_id)
            JOIN editions e ON e.edition_id = p.edition_id
            JOIN works w USING (work_id)
            WHERE sl.subject_id=%s
            ORDER BY sl.ord, p.passage_id
            LIMIT %s OFFSET %s
        """, (subject_id, min(limit, 100), offset))
    return {"subject": s, "total": total, "items": rows}
