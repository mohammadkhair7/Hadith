from fastapi import APIRouter, HTTPException

from ..db import db, q, q1
from ..services.diacritics import from_html

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
            SELECT p.passage_id, p.edition_id, p.source, p.source_page_id, p.seq, p.kind,
                   p.hadith_num, p.part, p.page, p.toc_node_id, p.text_raw, p.html, p.meta,
                   g.grade_ar, g.grade_norm, d.payload->>'text' AS text_diac,
                   st.payload->'spans' AS structure_spans, b.sanad_end_raw
            FROM passages p
            LEFT JOIN hadith_grades g USING (passage_id)
            LEFT JOIN passage_annotations d
                   ON d.passage_id = p.passage_id AND d.layer = 'diacritized'
                  AND d.engine = 'neural-tashkeel'
            LEFT JOIN passage_annotations st
                   ON st.passage_id = p.passage_id AND st.layer = 'structure'
                  AND st.engine = 'neural-indexing'
            LEFT JOIN LATERAL (
                SELECT c.sanad_end_raw FROM isnad_chains c
                WHERE c.passage_id = p.passage_id AND c.sanad_end_raw IS NOT NULL
                ORDER BY c.confidence DESC LIMIT 1
            ) b ON true
            WHERE p.edition_id=%s AND p.seq >= %s
            ORDER BY p.seq LIMIT %s
        """, (edition_id, seq, limit))
        if limit <= 10:
            # authentic source tashkeel beats the neural layer when available
            for r in rows:
                if r["source"] == "sunna" and r["html"]:
                    d = from_html(r["text_raw"], r["html"])
                    if d:
                        r["text_diac"] = d
        total = q1(conn, "SELECT passage_count AS n FROM editions WHERE edition_id=%s", (edition_id,))
    return {"total": total["n"] if total else 0, "items": rows}
