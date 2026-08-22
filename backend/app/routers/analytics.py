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
    narrator_profile()
    top_narrators(1000, 0)
    top_pairs(1000, 0)
    chain_lengths()
    transmission_verbs(None)
    from .narrators import narrators_directory
    narrators_directory(limit=1000, offset=0)   # default research-directory page


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


@router.get("/narrator-profile")
def narrator_profile():
    """Narrator population by rijal grade (الدرجة) and tabaqa (الطبقة)."""
    return _cached("narrator-profile", _narrator_profile)


# canonical severity order for the grade chart (best → worst)
_NGRADE_ORDER = ["sahabi", "thiqa", "saduq", "maqbul", "layyin",
                 "daif", "majhul", "matruk", "kadhdhab", "other"]


def _narrator_profile():
    with db() as conn:
        # rijal grades are free text from Taqrib (ثقه حافظ, صدوق يهم …);
        # bucket them into the canonical categories. starts_with() avoids
        # LIKE-% placeholders. Spellings follow normalize_arabic (ه for ة).
        grades = q(conn, """
            SELECT CASE
                WHEN starts_with(g, 'صحابي') THEN 'sahabi'
                WHEN starts_with(g, 'ثقه') OR starts_with(g, 'متفق')
                     OR starts_with(g, 'امام') THEN 'thiqa'
                WHEN starts_with(g, 'صدوق') OR starts_with(g, 'لا باس') THEN 'saduq'
                WHEN starts_with(g, 'مقبول') THEN 'maqbul'
                WHEN starts_with(g, 'لين') THEN 'layyin'
                WHEN starts_with(g, 'ضعيف') THEN 'daif'
                WHEN starts_with(g, 'مجهول') THEN 'majhul'
                WHEN starts_with(g, 'متروك') THEN 'matruk'
                WHEN starts_with(g, 'كذاب') THEN 'kadhdhab'
                ELSE 'other' END AS bucket,
                count(*) AS n
            FROM (SELECT meta->>'rijal_grade' AS g FROM narrators
                  WHERE meta->>'rijal_grade' IS NOT NULL) s
            GROUP BY 1
        """)
        tabaqat = q(conn, r"""
            SELECT (meta->>'tabaqa')::int AS tabaqa,
                   mode() WITHIN GROUP (ORDER BY meta->>'tabaqa_label') AS label,
                   count(*) AS n
            FROM narrators
            WHERE meta->>'tabaqa' ~ '^\d+$'
            GROUP BY 1 ORDER BY 1
        """)
    order = {k: i for i, k in enumerate(_NGRADE_ORDER)}
    grades.sort(key=lambda r: order.get(r["bucket"], 99))
    return {
        "grades": grades,
        "graded_total": sum(r["n"] for r in grades),
        "tabaqat": tabaqat,
        "tabaqa_total": sum(r["n"] for r in tabaqat),
    }


@router.get("/top-narrators")
def top_narrators(limit: int = 25, offset: int = 0):
    """Full listing via limit/offset paging (each page cached); the UI pages
    1000 at a time with a scrollable panel."""
    return _cached(f"top-narrators:{limit}:{offset}",
                   lambda: _top_narrators(limit, offset))


def _top_narrators(limit: int, offset: int):
    with db() as conn:
        total = _cached("top-narrators:total", lambda: q1(conn, """
            SELECT count(DISTINCT narrator_id) AS n
            FROM isnad_links WHERE narrator_id IS NOT NULL
        """)["n"])
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
            ORDER BY mentions DESC, n.narrator_id
            LIMIT %s OFFSET %s
        """, (min(limit, 1000), max(offset, 0)))
    return {"total": total, "items": rows}


@router.get("/top-pairs")
def top_pairs(limit: int = 25, offset: int = 0):
    """Unlimited listing via limit/offset paging (each page cached)."""
    return _cached(f"top-pairs:{limit}:{offset}",
                   lambda: _top_pairs(limit, offset))


def _top_pairs(limit: int, offset: int):
    with db() as conn:
        total = _cached("top-pairs:total", lambda: q1(conn, """
            SELECT count(*) AS n FROM (
                SELECT a.narrator_id, b.narrator_id
                FROM isnad_links a
                JOIN isnad_links b ON b.chain_id = a.chain_id AND b.pos = a.pos + 1
                WHERE a.narrator_id IS NOT NULL AND b.narrator_id IS NOT NULL
                  AND a.narrator_id != b.narrator_id
                GROUP BY 1, 2
            ) x
        """)["n"])
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
            ORDER BY weight DESC, student_id, teacher_id
            LIMIT %s OFFSET %s
        """, (min(limit, 1000), max(offset, 0)))
    return {"total": total, "items": rows}


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


@router.get("/timeline")
def timeline():
    """Hadith origination timeline (docs/HADITH_TIMELINE_ANALYSIS.md):
    year distribution, dated events, seasonal anchors, companion windows."""
    return _cached("timeline", _timeline)


def _timeline():
    with db() as conn:
        # graceful empty response until ops/analyze_timeline.py has run
        if not q1(conn, "SELECT to_regclass('hadith_dates') AS t")["t"]:
            return {"coverage": {"units": 0, "dated": 0, "exact_year": 0,
                                 "windowed": 0, "season_only": 0, "seasonal": 0},
                    "years": [], "events": [], "seasons": [], "companions": []}
        coverage = q1(conn, """
            SELECT
              (SELECT count(*) FROM passages WHERE kind='unit')      AS units,
              count(*)                                               AS dated,
              count(*) FILTER (WHERE year_best IS NOT NULL)          AS exact_year,
              count(*) FILTER (WHERE basis='companion')              AS windowed,
              count(*) FILTER (WHERE basis='season')                 AS season_only,
              count(*) FILTER (WHERE season IS NOT NULL)             AS seasonal
            FROM hadith_dates
        """)
        years = q(conn, """
            SELECT year_best AS year, count(*) AS n
            FROM hadith_dates WHERE year_best IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """)
        events = q(conn, """
            SELECT e.event_key, e.title_ar, e.year_ah, e.era, count(d.passage_id) AS n
            FROM timeline_events e
            LEFT JOIN hadith_dates d ON d.event_key = e.event_key
            GROUP BY 1, 2, 3, 4
            HAVING count(d.passage_id) > 0
            ORDER BY e.year_ah, n DESC
        """)
        seasons = q(conn, """
            SELECT season, count(*) AS n FROM hadith_dates
            WHERE season IS NOT NULL GROUP BY 1 ORDER BY n DESC
        """)
        companions = q(conn, """
            SELECT companion_key, companion_ar,
                   min(year_min) AS win_from, max(year_max) AS win_to,
                   count(*) AS n
            FROM hadith_dates
            WHERE companion_key IS NOT NULL
            GROUP BY 1, 2 ORDER BY n DESC LIMIT 40
        """)
    return {"coverage": coverage, "years": years, "events": events,
            "seasons": seasons, "companions": companions}


@router.get("/timeline/hadiths")
def timeline_hadiths(event: str | None = None, year: int | None = None,
                     season: str | None = None, companion: str | None = None,
                     limit: int = 20, offset: int = 0):
    """Drill-down listing for one timeline bucket."""
    where, args = [], []
    if event:
        where.append("d.event_key = %s")
        args.append(event)
    if year is not None:
        where.append("d.year_best = %s")
        args.append(year)
    if season:
        where.append("d.season = %s")
        args.append(season)
    if companion:
        where.append("d.companion_key = %s")
        args.append(companion)
    if not where:
        raise HTTPException(400, "one of event/year/season/companion is required")
    cond = " AND ".join(where)
    with db() as conn:
        total = q1(conn, f"SELECT count(*) AS n FROM hadith_dates d WHERE {cond}",
                   tuple(args))["n"]
        rows = q(conn, f"""
            SELECT p.passage_id, p.hadith_num, left(p.text_raw, 220) AS preview,
                   w.title_ar AS work_title,
                   d.basis, d.year_min, d.year_max, d.year_best, d.season,
                   d.companion_ar, d.confidence,
                   e.title_ar AS event_ar, ht.type_ar AS hadith_type_ar
            FROM hadith_dates d
            JOIN passages p USING (passage_id)
            JOIN editions ed ON ed.edition_id = p.edition_id
            JOIN works w ON w.work_id = ed.work_id
            LEFT JOIN timeline_events e ON e.event_key = d.event_key
            LEFT JOIN hadith_types ht ON ht.passage_id = d.passage_id
            WHERE {cond}
            ORDER BY d.confidence DESC, p.passage_id
            LIMIT %s OFFSET %s
        """, tuple(args) + (min(limit, 50), max(offset, 0)))
    return {"total": total, "items": rows}


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
