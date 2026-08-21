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


_SORTS = {
    "mentions": "mentions DESC",
    "chains": "chains DESC",
    "death": "n.death_year_h ASC NULLS LAST",
    "death_desc": "n.death_year_h DESC NULLS LAST",
    "name": "n.canonical_ar ASC",
    "id": "n.narrator_id ASC",
}


@router.get("/narrators/directory")
def narrators_directory(
        q_name: str | None = None, narrator_id: int | None = None,
        generation: str | None = None, grade: str | None = None,
        place: str | None = None,
        death_from: int | None = None, death_to: int | None = None,
        teacher: str | None = None, student: str | None = None,
        edition_id: int | None = None, topic: str | None = None,
        min_mentions: int = 0, sort: str = "mentions",
        limit: int = 25, offset: int = 0):
    """Research directory: list/filter/sort narrators on multiple criteria
    (name, trustworthiness grade, death year, place, teacher/student, book,
    hadith topic...)."""
    where, args = ["true"], {}
    if narrator_id:
        where.append("n.narrator_id = %(nid)s")
        args["nid"] = narrator_id
    if q_name:
        where.append("""(n.canonical_norm LIKE '%%' || %(qn)s || '%%'
            OR EXISTS (SELECT 1 FROM narrator_aliases a
                       WHERE a.narrator_id=n.narrator_id
                         AND a.alias_norm LIKE '%%' || %(qn)s || '%%'))""")
        args["qn"] = normalize_arabic(q_name)
    if generation:
        where.append("n.generation = %(gen)s")
        args["gen"] = generation
    if grade:
        # stored grades are normalized Arabic (ثقه not ثقة)
        where.append("n.meta->>'rijal_grade' LIKE '%%' || %(grade)s || '%%'")
        args["grade"] = normalize_arabic(grade)
    if place:
        where.append("""EXISTS (SELECT 1 FROM jsonb_array_elements_text(
            CASE WHEN jsonb_typeof(n.meta->'places')='array'
                 THEN n.meta->'places' ELSE '[]'::jsonb END) pl
            WHERE pl LIKE '%%' || %(place)s || '%%')""")
        args["place"] = place
    if death_from is not None:
        where.append("n.death_year_h >= %(dfrom)s")
        args["dfrom"] = death_from
    if death_to is not None:
        where.append("n.death_year_h <= %(dto)s")
        args["dto"] = death_to
    if teacher:
        where.append("""EXISTS (
            SELECT 1 FROM isnad_links a
            JOIN isnad_links b ON b.chain_id=a.chain_id AND b.pos=a.pos+1
            JOIN narrators tn ON tn.narrator_id=b.narrator_id
            WHERE a.narrator_id=n.narrator_id
              AND tn.canonical_norm LIKE '%%' || %(teacher)s || '%%')""")
        args["teacher"] = normalize_arabic(teacher)
    if student:
        where.append("""EXISTS (
            SELECT 1 FROM isnad_links b
            JOIN isnad_links a ON a.chain_id=b.chain_id AND a.pos=b.pos-1
            JOIN narrators sn ON sn.narrator_id=a.narrator_id
            WHERE b.narrator_id=n.narrator_id
              AND sn.canonical_norm LIKE '%%' || %(student)s || '%%')""")
        args["student"] = normalize_arabic(student)
    if edition_id:
        where.append("""EXISTS (
            SELECT 1 FROM isnad_links l
            JOIN isnad_chains c USING (chain_id)
            JOIN passages p ON p.passage_id=c.passage_id
            WHERE l.narrator_id=n.narrator_id AND p.edition_id=%(ed)s)""")
        args["ed"] = edition_id
    if topic:
        where.append("""EXISTS (
            SELECT 1 FROM isnad_links l
            JOIN isnad_chains c USING (chain_id)
            JOIN subject_links sl ON sl.passage_id=c.passage_id
            JOIN subjects sj ON sj.subject_id=sl.subject_id
            WHERE l.narrator_id=n.narrator_id
              AND sj.title_norm LIKE '%%' || %(topic)s || '%%')""")
        args["topic"] = normalize_arabic(topic)
    if min_mentions > 0:
        where.append("coalesce(s.mentions, 0) >= %(minm)s")
        args["minm"] = min_mentions

    cond = " AND ".join(where)
    order_by = _SORTS.get(sort, _SORTS["mentions"])
    args["limit"] = min(limit, 100)
    args["offset"] = max(offset, 0)

    with db() as conn:
        base = f"""
            FROM narrators n
            LEFT JOIN (
                SELECT narrator_id, count(*) AS mentions,
                       count(DISTINCT chain_id) AS chains
                FROM isnad_links WHERE narrator_id IS NOT NULL GROUP BY 1
            ) s USING (narrator_id)
            WHERE {cond}"""
        total = q1(conn, f"SELECT count(*) AS n {base}", args)["n"]
        rows = q(conn, f"""
            SELECT n.narrator_id, n.canonical_ar, n.generation, n.death_year_h,
                   n.meta->>'rijal_grade'  AS rijal_grade,
                   n.meta->>'tabaqa_label' AS tabaqa_label,
                   n.meta->'places'        AS places,
                   coalesce(s.mentions, 0) AS mentions,
                   coalesce(s.chains, 0)   AS chains,
                   (SELECT count(DISTINCT p.edition_id)
                    FROM isnad_links l
                    JOIN isnad_chains c USING (chain_id)
                    JOIN passages p ON p.passage_id=c.passage_id
                    WHERE l.narrator_id=n.narrator_id) AS books
            {base}
            ORDER BY {order_by}, n.narrator_id
            LIMIT %(limit)s OFFSET %(offset)s
        """, args)
    return {"total": total, "items": rows}


_FACETS_CACHE: dict = {}


@router.get("/narrators/directory/facets")
def directory_facets():
    import time
    if _FACETS_CACHE.get("at", 0) > time.time() - 3600:
        return _FACETS_CACHE["data"]
    with db() as conn:
        gens = q(conn, """
            SELECT generation, count(*) AS n FROM narrators
            WHERE generation IS NOT NULL GROUP BY 1 ORDER BY n DESC
        """)
        grades = q(conn, """
            SELECT meta->>'rijal_grade' AS grade, count(*) AS n FROM narrators
            WHERE meta->>'rijal_grade' IS NOT NULL
            GROUP BY 1 ORDER BY n DESC LIMIT 20
        """)
        places = q(conn, """
            SELECT pl AS place, count(*) AS n
            FROM narrators n,
                 jsonb_array_elements_text(
                     CASE WHEN jsonb_typeof(n.meta->'places')='array'
                          THEN n.meta->'places' ELSE '[]'::jsonb END) pl
            GROUP BY 1 ORDER BY n DESC LIMIT 30
        """)
        books = q(conn, """
            SELECT e.edition_id, w.title_ar FROM editions e
            JOIN works w USING (work_id)
            WHERE EXISTS (SELECT 1 FROM passages p
                          JOIN isnad_chains c ON c.passage_id = p.passage_id
                          WHERE p.edition_id = e.edition_id)
            ORDER BY w.title_ar
        """)
    data = {"generations": gens, "grades": grades, "places": places, "books": books}
    _FACETS_CACHE.update({"at": time.time(), "data": data})
    return data


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


@router.get("/narrators/pair/{student_id}/{teacher_id}/hadiths")
def pair_hadiths(student_id: int, teacher_id: int, limit: int = 50, offset: int = 0):
    """Hadiths whose isnad contains the consecutive link student→teacher
    (used when clicking a relationship edge in the graph)."""
    with db() as conn:
        total = q1(conn, """
            SELECT count(DISTINCT c.passage_id) AS n
            FROM isnad_links a
            JOIN isnad_links b ON b.chain_id = a.chain_id AND b.pos = a.pos + 1
            JOIN isnad_chains c ON c.chain_id = a.chain_id
            WHERE a.narrator_id=%s AND b.narrator_id=%s
        """, (student_id, teacher_id))["n"]
        rows = q(conn, """
            SELECT DISTINCT ON (p.passage_id)
                   p.passage_id, p.hadith_num, p.source, left(p.text_raw, 300) AS preview,
                   w.title_ar AS work_title
            FROM isnad_links a
            JOIN isnad_links b ON b.chain_id = a.chain_id AND b.pos = a.pos + 1
            JOIN isnad_chains c ON c.chain_id = a.chain_id
            JOIN passages p ON p.passage_id = c.passage_id
            JOIN editions e USING (edition_id)
            JOIN works w USING (work_id)
            WHERE a.narrator_id=%s AND b.narrator_id=%s
            ORDER BY p.passage_id
            LIMIT %s OFFSET %s
        """, (student_id, teacher_id, min(limit, 100), offset))
    return {"total": total, "items": rows}


def _neighbors(conn, ids: list[int], cap: int):
    """Aggregated NARRATED_FROM edges touching the given narrator set,
    with admin manual overrides applied (added edges join in, removed
    edges are hidden)."""
    from ..services.narrator_admin import ensure_tables
    ensure_tables(conn)
    return q(conn, """
        WITH derived AS (
            SELECT a.narrator_id AS student, b.narrator_id AS teacher,
                   count(*) AS weight
            FROM isnad_links a
            JOIN isnad_links b ON b.chain_id = a.chain_id AND b.pos = a.pos + 1
            WHERE (a.narrator_id = ANY(%s) OR b.narrator_id = ANY(%s))
              AND a.narrator_id IS NOT NULL AND b.narrator_id IS NOT NULL
              AND a.narrator_id != b.narrator_id
            GROUP BY 1, 2
        ), manual_add AS (
            SELECT student_id AS student, teacher_id AS teacher,
                   greatest(coalesce(weight, 1), 1)::bigint AS weight
            FROM narrator_edges_manual
            WHERE action = 'add'
              AND (student_id = ANY(%s) OR teacher_id = ANY(%s))
        ), combined AS (
            SELECT student, teacher, sum(weight)::bigint AS weight
            FROM (SELECT * FROM derived UNION ALL SELECT * FROM manual_add) u
            GROUP BY 1, 2
        )
        SELECT c.student, c.teacher, c.weight FROM combined c
        WHERE NOT EXISTS (SELECT 1 FROM narrator_edges_manual r
                          WHERE r.action = 'remove'
                            AND r.student_id = c.student
                            AND r.teacher_id = c.teacher)
        ORDER BY c.weight DESC LIMIT %s
    """, (ids, ids, ids, ids, cap))


def _node_details(conn, ids: list[int]):
    return q(conn, """
        SELECT n.narrator_id, n.canonical_ar AS name, n.generation, n.death_year_h,
               n.bio_summary,
               n.meta->>'rijal_grade'   AS rijal_grade,
               n.meta->>'tabaqa'        AS tabaqa,
               n.meta->>'tabaqa_label'  AS tabaqa_label,
               n.meta->'places'         AS places,
               n.meta->>'school'        AS school,
               (SELECT count(*) FROM isnad_links l WHERE l.narrator_id=n.narrator_id) AS mentions,
               (SELECT count(DISTINCT p.edition_id)
                  FROM isnad_links l JOIN isnad_chains c USING (chain_id)
                  JOIN passages p ON p.passage_id = c.passage_id
                 WHERE l.narrator_id=n.narrator_id) AS books
        FROM narrators n WHERE n.narrator_id = ANY(%s)
    """, (ids,))


def _name_tokens(name: str) -> list[str]:
    toks = normalize_arabic(name or "").split()
    if toks and toks[0] in ("ابا", "ابي"):
        toks[0] = "ابو"
    return ["بن" if t == "ابن" else t for t in toks]


def _kin_relation(student: dict, teacher: dict) -> tuple[str, str] | None:
    """Infer a family/peer relation from nasab strings + tabaqa. Returns
    (kind, arabic_label) or None when only the generic teacher/student holds."""
    s, t = _name_tokens(student.get("name", "")), _name_tokens(teacher.get("name", ""))
    if not s or not t:
        return None
    # student "X بن A بن B ..." — teacher's name matching at the first "بن"
    # segment means the teacher is the father; at the second, the grandfather.
    bn_positions = [i for i, w in enumerate(s) if w in ("بن", "بنت")]
    for depth, i in enumerate(bn_positions[:2]):
        rest = s[i + 1:]
        head_len = min(len(t), max(2, len(rest)))
        if rest and t[:len(rest[:head_len])] == rest[:head_len][:len(t)]:
            n = min(len(t), len(rest))
            if n >= 1 and t[:n] == rest[:n]:
                return ("father", "أبوه (روى عن أبيه)") if depth == 0 \
                    else ("grandfather", "جدّه (روى عن جدّه)")
    # siblings: both "X بن A [بن B]" sharing the nasab tail
    if bn_positions and any(w in ("بن", "بنت") for w in t):
        si = bn_positions[0]
        ti = next(i for i, w in enumerate(t) if w in ("بن", "بنت"))
        if s[:si] != t[:ti] and s[si:si + 4] == t[ti:ti + 4] and len(s[si:si + 4]) >= 2:
            return ("brother", "أخوه")
    ta_s, ta_t = student.get("tabaqa"), teacher.get("tabaqa")
    if ta_s and ta_t and ta_s == ta_t:
        return ("peer", "قرينه (من نفس الطبقة)")
    return None


def _edge_relations(nodes: list[dict], edges: list[dict]) -> None:
    by_id = {n["narrator_id"]: n for n in nodes}
    for e in edges:
        s, t = by_id.get(e["student"]), by_id.get(e["teacher"])
        rel = _kin_relation(s, t) if s and t else None
        e["relation"], e["relation_ar"] = rel if rel else ("teacher", "شيخه (تلميذ وشيخ)")


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
    edge_list = [{"student": s, "teacher": t, "weight": w}
                 for (s, t), w in edges.items()]
    _edge_relations(nodes, edge_list)
    return {"center": narrator_id,
            "nodes": nodes,
            "edges": edge_list,
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
    edge_list = [{"student": r["student"], "teacher": r["teacher"],
                  "weight": r["weight"]} for r in rows]
    _edge_relations(nodes, edge_list)
    return {"nodes": nodes, "edges": edge_list}


@router.get("/passages/{passage_id}/isnad")
def passage_isnad(passage_id: int):
    with db() as conn:
        chains = q(conn, """
            SELECT chain_id, ord, confidence, extractor, sanad_end_raw FROM isnad_chains
            WHERE passage_id=%s ORDER BY ord
        """, (passage_id,))
        for c in chains:
            c["links"] = q(conn, """
                SELECT l.pos, l.mention_ar, l.verb, l.narrator_id, n.canonical_ar
                FROM isnad_links l LEFT JOIN narrators n USING (narrator_id)
                WHERE l.chain_id=%s ORDER BY l.pos
            """, (c["chain_id"],))
    return chains
