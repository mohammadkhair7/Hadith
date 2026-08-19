"""Narrator KG endpoints (§13): profile, hadiths, bounded subgraph, expansion,
per-passage isnad. Subgraph neighbor queries run on the relational isnad_links
(same data the AGE graph is projected from) for speed; NL2CYPHER uses AGE."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import db, q, q1
from ..services.normalize import normalize_arabic

router = APIRouter(tags=["narrators"])

MAX_CAP = 300


@router.get("/narrators")
def search_narrators(search: str, limit: int = 20):
    qnorm = normalize_arabic(search)
    with db() as conn:
        rows = q(conn, """
            SELECT n.narrator_id, n.canonical_ar, n.generation, n.death_year_h,
                   (SELECT count(*) FROM isnad_links l WHERE l.narrator_id=n.narrator_id) AS mentions
            FROM narrators n
            WHERE n.canonical_norm LIKE '%%' || %s || '%%'
               OR EXISTS (SELECT 1 FROM narrator_aliases a
                          WHERE a.narrator_id=n.narrator_id
                            AND a.alias_norm LIKE '%%' || %s || '%%')
            ORDER BY mentions DESC LIMIT %s
        """, (qnorm, qnorm, min(limit, 50)))
    return rows


@router.get("/narrators/{narrator_id}")
def get_narrator(narrator_id: int):
    with db() as conn:
        n = q1(conn, "SELECT * FROM narrators WHERE narrator_id=%s", (narrator_id,))
        if not n:
            raise HTTPException(404, "narrator not found")
        n["aliases"] = q(conn, """
            SELECT alias_ar, alias_kind FROM narrator_aliases WHERE narrator_id=%s
        """, (narrator_id,))
        n["assessments"] = q(conn, """
            SELECT critic, grade, quote, src_passage FROM narrator_assessments
            WHERE narrator_id=%s LIMIT 30
        """, (narrator_id,))
        stats = q1(conn, """
            SELECT count(DISTINCT chain_id) AS chains, count(*) AS mentions
            FROM isnad_links WHERE narrator_id=%s
        """, (narrator_id,))
        n.update(stats or {})
    return n


@router.get("/narrators/{narrator_id}/hadiths")
def narrator_hadiths(narrator_id: int, limit: int = 20, offset: int = 0):
    with db() as conn:
        total = q1(conn, """
            SELECT count(DISTINCT c.passage_id) AS n
            FROM isnad_links l JOIN isnad_chains c USING (chain_id)
            WHERE l.narrator_id=%s
        """, (narrator_id,))["n"]
        rows = q(conn, """
            SELECT DISTINCT ON (p.passage_id)
                   p.passage_id, p.hadith_num, p.source, left(p.text_raw, 300) AS preview,
                   w.title_ar AS work_title, l.pos, l.verb
            FROM isnad_links l
            JOIN isnad_chains c USING (chain_id)
            JOIN passages p ON p.passage_id = c.passage_id
            JOIN editions e USING (edition_id)
            JOIN works w USING (work_id)
            WHERE l.narrator_id=%s
            ORDER BY p.passage_id
            LIMIT %s OFFSET %s
        """, (narrator_id, min(limit, 100), offset))
    return {"total": total, "items": rows}


def _neighbors(conn, ids: list[int], cap: int):
    """Aggregated NARRATED_FROM edges touching the given narrator set."""
    return q(conn, """
        SELECT a.narrator_id AS student, b.narrator_id AS teacher, count(*) AS weight
        FROM isnad_links a
        JOIN isnad_links b ON b.chain_id = a.chain_id AND b.pos = a.pos + 1
        WHERE (a.narrator_id = ANY(%s) OR b.narrator_id = ANY(%s))
          AND a.narrator_id IS NOT NULL AND b.narrator_id IS NOT NULL
          AND a.narrator_id != b.narrator_id
        GROUP BY 1, 2 ORDER BY weight DESC LIMIT %s
    """, (ids, ids, cap))


def _node_details(conn, ids: list[int]):
    return q(conn, """
        SELECT n.narrator_id, n.canonical_ar AS name, n.generation, n.death_year_h,
               (SELECT count(*) FROM isnad_links l WHERE l.narrator_id=n.narrator_id) AS mentions
        FROM narrators n WHERE n.narrator_id = ANY(%s)
    """, (ids,))


@router.get("/narrators/{narrator_id}/graph")
def narrator_graph(narrator_id: int, depth: int = 1, cap: int = 100):
    cap = min(cap, MAX_CAP)
    depth = min(max(depth, 1), 3)
    with db() as conn:
        if not q1(conn, "SELECT 1 AS x FROM narrators WHERE narrator_id=%s", (narrator_id,)):
            raise HTTPException(404, "narrator not found")
        frontier = [narrator_id]
        seen = {narrator_id}
        edges: dict[tuple[int, int], int] = {}
        for _ in range(depth):
            if not frontier or len(seen) >= cap:
                break
            rows = _neighbors(conn, frontier, cap * 3)
            frontier = []
            for r in rows:
                if len(seen) >= cap and (r["student"] not in seen or r["teacher"] not in seen):
                    continue
                edges[(r["student"], r["teacher"])] = r["weight"]
                for nid in (r["student"], r["teacher"]):
                    if nid not in seen:
                        seen.add(nid)
                        frontier.append(nid)
        nodes = _node_details(conn, list(seen))
    return {"center": narrator_id,
            "nodes": nodes,
            "edges": [{"student": s, "teacher": t, "weight": w}
                      for (s, t), w in edges.items()],
            "capped": len(seen) >= cap}


class ExpandBody(BaseModel):
    node_ids: list[int]
    cap: int = 50


@router.post("/graph/expand")
def graph_expand(body: ExpandBody):
    cap = min(body.cap, MAX_CAP)
    with db() as conn:
        rows = _neighbors(conn, body.node_ids[:50], cap)
        ids = {body_id for body_id in body.node_ids}
        for r in rows:
            ids.add(r["student"])
            ids.add(r["teacher"])
        nodes = _node_details(conn, list(ids))
    return {"nodes": nodes,
            "edges": [{"student": r["student"], "teacher": r["teacher"],
                       "weight": r["weight"]} for r in rows]}


@router.get("/passages/{passage_id}/isnad")
def passage_isnad(passage_id: int):
    with db() as conn:
        chains = q(conn, """
            SELECT chain_id, ord, confidence, extractor FROM isnad_chains
            WHERE passage_id=%s ORDER BY ord
        """, (passage_id,))
        for c in chains:
            c["links"] = q(conn, """
                SELECT l.pos, l.mention_ar, l.verb, l.narrator_id, n.canonical_ar
                FROM isnad_links l LEFT JOIN narrators n USING (narrator_id)
                WHERE l.chain_id=%s ORDER BY l.pos
            """, (c["chain_id"],))
    return chains
