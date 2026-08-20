from fastapi import APIRouter, HTTPException

from ..db import db, q, q1
from ..services.classify import TRANSMISSION_CLASSES, transmission_class
from ..services.diacritics import from_html

router = APIRouter(tags=["passages"])


@router.get("/passages/{passage_id}")
def get_passage(passage_id: int, lang: str | None = None):
    with db() as conn:
        p = q1(conn, """
            SELECT p.*, e.title_ar AS edition_title, e.source AS edition_source,
                   w.work_id, w.title_ar AS work_title, w.author_ar
            FROM passages p
            JOIN editions e USING (edition_id)
            JOIN works w USING (work_id)
            WHERE p.passage_id=%s
        """, (passage_id,))
        if not p:
            raise HTTPException(404, "passage not found")
        p.pop("tsv", None)

        p["text_diac"] = None
        if p.get("source") == "sunna" and p.get("html"):
            p["text_diac"] = from_html(p["text_raw"], p["html"])
        if not p["text_diac"]:
            diac = q1(conn, """
                SELECT payload->>'text' AS text FROM passage_annotations
                WHERE passage_id=%s AND layer='diacritized' AND engine='neural-tashkeel'
                LIMIT 1
            """, (passage_id,))
            p["text_diac"] = diac["text"] if diac else None

        # breadcrumbs from the TOC anchor upward
        crumbs = []
        node_id = p.get("toc_node_id")
        while node_id:
            node = q1(conn, "SELECT toc_node_id, parent_id, title FROM toc_nodes WHERE toc_node_id=%s",
                      (node_id,))
            if not node:
                break
            crumbs.append({"toc_node_id": node["toc_node_id"], "title": node["title"]})
            node_id = node["parent_id"]
        p["breadcrumbs"] = list(reversed(crumbs))

        p["subjects"] = q(conn, """
            SELECT s.subject_id, s.title
            FROM subject_links sl JOIN subjects s USING (subject_id)
            WHERE sl.passage_id=%s ORDER BY sl.ord LIMIT 30
        """, (passage_id,))

        boundary = q1(conn, """
            SELECT sanad_end_raw FROM isnad_chains
            WHERE passage_id=%s AND sanad_end_raw IS NOT NULL
            ORDER BY confidence DESC LIMIT 1
        """, (passage_id,))
        p["sanad_end_raw"] = boundary["sanad_end_raw"] if boundary else None

        p["grade"] = q1(conn, """
            SELECT grade_ar, grade_norm, source FROM hadith_grades WHERE passage_id=%s
        """, (passage_id,))

        p["hadith_type"] = q1(conn, """
            SELECT type_norm, type_ar, confidence FROM hadith_types WHERE passage_id=%s
        """, (passage_id,))

        # means-of-transmission classes present in this passage's isnad
        tverbs = q(conn, """
            SELECT DISTINCT l.verb FROM isnad_chains c
            JOIN isnad_links l USING (chain_id)
            WHERE c.passage_id=%s AND l.verb IS NOT NULL
        """, (passage_id,))
        seen: dict[str, dict] = {}
        for row in tverbs:
            key = transmission_class(row["verb"])
            if key and key not in seen:
                seen[key] = {"key": key, "ar": TRANSMISSION_CLASSES[key]["ar"]}
        p["transmission"] = list(seen.values())

        # neighbours in reading order
        p["prev"] = q1(conn, """
            SELECT passage_id, seq FROM passages
            WHERE edition_id=%s AND seq < %s ORDER BY seq DESC LIMIT 1
        """, (p["edition_id"], p["seq"]))
        p["next"] = q1(conn, """
            SELECT passage_id, seq FROM passages
            WHERE edition_id=%s AND seq > %s ORDER BY seq LIMIT 1
        """, (p["edition_id"], p["seq"]))

        if lang and lang != "ar":
            tr = q1(conn, """
                SELECT text, status, source, meta FROM translations
                WHERE obj_type='passage' AND obj_id=%s AND field='text' AND lang=%s
            """, (passage_id, lang))
            p["translation"] = tr
    return p


@router.get("/passages/{passage_id}/same-work")
def same_work_editions(passage_id: int):
    """Cross-edition links: other editions of the same work (compare view)."""
    with db() as conn:
        row = q1(conn, """
            SELECT e.work_id, p.edition_id FROM passages p JOIN editions e USING (edition_id)
            WHERE p.passage_id=%s
        """, (passage_id,))
        if not row:
            raise HTTPException(404, "passage not found")
        others = q(conn, """
            SELECT edition_id, source, title_ar, passage_count
            FROM editions WHERE work_id=%s AND edition_id != %s
        """, (row["work_id"], row["edition_id"]))
    return others
