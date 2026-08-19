from fastapi import APIRouter, HTTPException

from ..db import db, q, q1

router = APIRouter(tags=["works"])


@router.get("/works")
def list_works(kind: str | None = None, source: str | None = None):
    with db() as conn:
        where, params = ["1=1"], []
        if kind:
            where.append("w.kind = %s")
            params.append(kind)
        if source:
            where.append("EXISTS (SELECT 1 FROM editions e2 WHERE e2.work_id=w.work_id AND e2.source=%s)")
            params.append(source)
        rows = q(conn, f"""
            SELECT w.work_id, w.title_ar, w.author_ar, w.kind,
                   json_agg(json_build_object(
                       'edition_id', e.edition_id, 'source', e.source,
                       'title_ar', e.title_ar, 'section_name', e.section_name,
                       'book_type', e.book_type, 'passage_count', e.passage_count)
                       ORDER BY e.source) AS editions
            FROM works w
            JOIN editions e USING (work_id)
            WHERE {' AND '.join(where)}
            GROUP BY w.work_id
            ORDER BY w.work_id
        """, params)
    return rows


@router.get("/works/{work_id}")
def get_work(work_id: int):
    with db() as conn:
        w = q1(conn, "SELECT * FROM works WHERE work_id=%s", (work_id,))
        if not w:
            raise HTTPException(404, "work not found")
        w["editions"] = q(conn, """
            SELECT edition_id, source, source_book_id, title_ar, section_name,
                   book_type, passage_count, meta
            FROM editions WHERE work_id=%s ORDER BY source
        """, (work_id,))
    return w


@router.get("/editions/{edition_id}/toc")
def edition_toc(edition_id: int, parent_id: int | None = None, depth: int = 2):
    """Return the TOC subtree starting at parent_id (or roots), limited depth
    for lazy loading of huge trees."""
    with db() as conn:
        base = q1(conn, "SELECT edition_id, title_ar, passage_count FROM editions WHERE edition_id=%s",
                  (edition_id,))
        if not base:
            raise HTTPException(404, "edition not found")
        if parent_id is None:
            roots = q(conn, """
                SELECT toc_node_id, source_node_id, title, is_leaf, ord, depth,
                       EXISTS (SELECT 1 FROM toc_nodes c WHERE c.parent_id = t.toc_node_id) AS has_children
                FROM toc_nodes t
                WHERE edition_id=%s AND parent_id IS NULL
                ORDER BY ord, toc_node_id
            """, (edition_id,))
        else:
            roots = q(conn, """
                SELECT toc_node_id, source_node_id, title, is_leaf, ord, depth,
                       EXISTS (SELECT 1 FROM toc_nodes c WHERE c.parent_id = t.toc_node_id) AS has_children
                FROM toc_nodes t
                WHERE edition_id=%s AND parent_id=%s
                ORDER BY ord, toc_node_id
            """, (edition_id, parent_id))
    return {"edition": base, "nodes": roots}


@router.get("/editions/{edition_id}/toc-leaf/{toc_node_id}")
def toc_leaf_passage(edition_id: int, toc_node_id: int):
    """Resolve a TOC node to the first passage anchored at or under it."""
    with db() as conn:
        row = q1(conn, """
            SELECT passage_id, seq FROM passages
            WHERE edition_id=%s AND toc_node_id=%s
            ORDER BY seq LIMIT 1
        """, (edition_id, toc_node_id))
        if not row:
            row = q1(conn, """
                WITH RECURSIVE sub AS (
                    SELECT toc_node_id FROM toc_nodes WHERE toc_node_id=%s
                    UNION ALL
                    SELECT t.toc_node_id FROM toc_nodes t JOIN sub ON t.parent_id = sub.toc_node_id
                )
                SELECT p.passage_id, p.seq FROM passages p
                JOIN sub ON p.toc_node_id = sub.toc_node_id
                WHERE p.edition_id=%s
                ORDER BY p.seq LIMIT 1
            """, (toc_node_id, edition_id))
    if not row:
        raise HTTPException(404, "no passage anchored to this node")
    return row


@router.get("/editions/{edition_id}/passages")
def edition_passages(edition_id: int, seq: int = 0, limit: int = 1):
    """Reader fetch: passages by reading order."""
    limit = max(1, min(limit, 20))
    with db() as conn:
        rows = q(conn, """
            SELECT passage_id, edition_id, source, source_page_id, seq, kind,
                   hadith_num, part, page, toc_node_id, text_raw, html, meta
            FROM passages
            WHERE edition_id=%s AND seq >= %s
            ORDER BY seq LIMIT %s
        """, (edition_id, seq, limit))
        total = q1(conn, "SELECT passage_count AS n FROM editions WHERE edition_id=%s", (edition_id,))
    return {"total": total["n"] if total else 0, "items": rows}
