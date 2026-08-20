"""Hadith analysis endpoints: corpus overview, isnad coverage, grade
distribution, top narrators / transmission pairs, chain-length and
transmission-verb statistics, and per-passage corroborations (متابعات).

The corpus-wide aggregations scan ~1M isnad rows, so results are cached
in-process (the data only changes on ETL runs) and warmed at startup."""
import time
from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from ..db import db, q, q1

router = APIRouter(prefix="/analytics", tags=["analytics"])

_CACHE: dict[str, tuple[float, Any]] = {}
_TTL = 12 * 3600


def _cached(key: str, build: Callable[[], Any]) -> Any:
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    val = build()
    _CACHE[key] = (time.time(), val)
    return val


def warm_cache() -> None:
    """Prime the heavy corpus-wide aggregations (called from startup)."""
    overview()
    grades(None)
    top_narrators(25)
    top_narrators(20)
    top_pairs(25)
    top_pairs(20)
    chain_lengths()
    transmission_verbs(None)


@router.get("/overview")
def overview():
    return _cached("overview", _overview)


def _overview():
    with db() as conn:
        totals = q1(conn, """
            SELECT
              (SELECT count(*) FROM passages)                              AS passages,
              (SELECT count(*) FROM passages WHERE kind='unit')            AS units,
              (SELECT count(*) FROM isnad_chains)                          AS chains,
              (SELECT count(*) FROM isnad_links)                           AS links,
              (SELECT count(*) FROM isnad_links WHERE narrator_id IS NOT NULL) AS links_resolved,
              (SELECT count(*) FROM narrators)                             AS narrators,
              (SELECT count(*) FROM hadith_grades)                         AS graded
        """)
        books = q(conn, """
            SELECT e.edition_id, w.title_ar, e.source,
                   count(*) FILTER (WHERE p.kind='unit')                   AS units,
                   count(c.chain_id)                                       AS chains,
                   count(c.sanad_end_raw)                                  AS matn_boundaries,
                   count(g.passage_id)                                     AS graded
            FROM editions e
            JOIN works w USING (work_id)
            JOIN passages p USING (edition_id)
            LEFT JOIN isnad_chains c ON c.passage_id = p.passage_id
            LEFT JOIN hadith_grades g ON g.passage_id = p.passage_id
            WHERE w.kind='matn'
            GROUP BY 1, 2, 3
            HAVING count(*) FILTER (WHERE p.kind='unit') > 0
            ORDER BY units DESC
        """)
    return {"totals": totals, "books": books}


@router.get("/grades")
def grades(edition_id: int | None = None):
    return _cached(f"grades:{edition_id}", lambda: _grades(edition_id))


def _grades(edition_id: int | None):
    with db() as conn:
        args: tuple = ()
        where = ""
        if edition_id:
            where = "JOIN passages p USING (passage_id) WHERE p.edition_id=%s"
            args = (edition_id,)
        dist = q(conn, f"""
            SELECT grade_norm, count(*) AS n
            FROM hadith_grades {where}
            GROUP BY grade_norm ORDER BY n DESC
        """, args)
        by_source = q(conn, """
            SELECT source, count(*) AS n FROM hadith_grades GROUP BY source ORDER BY n DESC
        """)
    return {"distribution": dist, "by_source": by_source}


@router.get("/top-narrators")
def top_narrators(limit: int = 25):
    return _cached(f"top-narrators:{limit}", lambda: _top_narrators(limit))


def _top_narrators(limit: int):
    with db() as conn:
        rows = q(conn, """
            SELECT n.narrator_id, n.canonical_ar, n.generation, n.death_year_h,
                   count(*)                        AS mentions,
                   count(DISTINCT l.chain_id)      AS chains,
                   count(DISTINCT p.edition_id)    AS books
            FROM isnad_links l
            JOIN narrators n USING (narrator_id)
            JOIN isnad_chains c USING (chain_id)
            JOIN passages p ON p.passage_id = c.passage_id
            GROUP BY 1, 2, 3, 4
            ORDER BY mentions DESC LIMIT %s
        """, (min(limit, 100),))
    return rows


@router.get("/top-pairs")
def top_pairs(limit: int = 25):
    return _cached(f"top-pairs:{limit}", lambda: _top_pairs(limit))


def _top_pairs(limit: int):
    with db() as conn:
        rows = q(conn, """
            SELECT sn.narrator_id AS student_id, sn.canonical_ar AS student,
                   tn.narrator_id AS teacher_id, tn.canonical_ar AS teacher,
                   count(*) AS weight
            FROM isnad_links a
            JOIN isnad_links b ON b.chain_id = a.chain_id AND b.pos = a.pos + 1
            JOIN narrators sn ON sn.narrator_id = a.narrator_id
            JOIN narrators tn ON tn.narrator_id = b.narrator_id
            WHERE a.narrator_id != b.narrator_id
            GROUP BY 1, 2, 3, 4
            ORDER BY weight DESC LIMIT %s
        """, (min(limit, 100),))
    return rows


@router.get("/chain-lengths")
def chain_lengths():
    return _cached("chain-lengths", _chain_lengths)


def _chain_lengths():
    with db() as conn:
        rows = q(conn, """
            SELECT hops, count(*) AS n FROM (
                SELECT chain_id, count(*) AS hops FROM isnad_links GROUP BY chain_id
            ) s GROUP BY hops ORDER BY hops
        """)
    return rows


@router.get("/verbs")
def transmission_verbs(edition_id: int | None = None):
    """حدثنا vs عن ... — the معنعن ratio is a classic isnad-criticism signal."""
    return _cached(f"verbs:{edition_id}", lambda: _verbs(edition_id))


def _verbs(edition_id: int | None):
    with db() as conn:
        if edition_id:
            rows = q(conn, """
                SELECT l.verb, count(*) AS n
                FROM isnad_links l
                JOIN isnad_chains c USING (chain_id)
                JOIN passages p ON p.passage_id = c.passage_id
                WHERE p.edition_id=%s
                GROUP BY l.verb ORDER BY n DESC
            """, (edition_id,))
        else:
            rows = q(conn, "SELECT verb, count(*) AS n FROM isnad_links GROUP BY verb ORDER BY n DESC")
    return rows


@router.get("/passages/{passage_id}/mutabaat")
def mutabaat(passage_id: int, limit: int = 12):
    """Corroborating transmissions: other hadiths whose chains share
    consecutive (student, teacher) pairs with this passage's chain."""
    with db() as conn:
        if not q1(conn, "SELECT 1 AS x FROM passages WHERE passage_id=%s", (passage_id,)):
            raise HTTPException(404, "passage not found")
        rows = q(conn, """
            WITH my_pairs AS (
                SELECT a.narrator_id AS s, b.narrator_id AS t
                FROM isnad_chains c
                JOIN isnad_links a USING (chain_id)
                JOIN isnad_links b ON b.chain_id = a.chain_id AND b.pos = a.pos + 1
                WHERE c.passage_id=%s
                  AND a.narrator_id IS NOT NULL AND b.narrator_id IS NOT NULL
            )
            SELECT p.passage_id, p.hadith_num, left(p.text_raw, 220) AS preview,
                   w.title_ar AS work_title, count(*) AS shared_pairs
            FROM my_pairs mp
            JOIN isnad_links a ON a.narrator_id = mp.s
            JOIN isnad_links b ON b.chain_id = a.chain_id AND b.pos = a.pos + 1
                              AND b.narrator_id = mp.t
            JOIN isnad_chains c ON c.chain_id = a.chain_id
            JOIN passages p ON p.passage_id = c.passage_id
            JOIN editions e USING (edition_id)
            JOIN works w USING (work_id)
            WHERE c.passage_id != %s
            GROUP BY 1, 2, 3, 4
            ORDER BY shared_pairs DESC, p.passage_id
            LIMIT %s
        """, (passage_id, passage_id, min(limit, 50)))
    return rows
