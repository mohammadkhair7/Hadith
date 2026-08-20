"""Keyword search: tashkeel-insensitive by default (FTS over text_norm),
optional exact-tashkeel post-filter over text_raw. Snippets via ts_headline."""
from typing import Any

from .normalize import normalize_arabic


def keyword_search(
    conn,
    query: str,
    *,
    exact: bool = False,
    source: str | None = None,
    edition_id: int | None = None,
    work_kind: str | None = None,
    subject_id: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    qnorm = normalize_arabic(query)
    if not qnorm:
        return {"total": 0, "items": []}

    where = ["p.tsv @@ websearch_to_tsquery('simple', %(q)s)"]
    params: dict[str, Any] = {"q": qnorm, "limit": limit, "offset": offset}

    if exact:
        where.append("p.text_raw LIKE %(exact)s")
        params["exact"] = f"%{query.strip()}%"
    if source:
        where.append("p.source = %(source)s")
        params["source"] = source
    else:
        # the alifta archive is reference material, not part of "all sources"
        where.append("p.source <> 'alifta'")
    if edition_id:
        where.append("p.edition_id = %(edition_id)s")
        params["edition_id"] = edition_id
    if work_kind:
        where.append("e.book_type = %(work_kind)s" if work_kind in ("matn", "service", "page-archive")
                      else "w.kind = %(work_kind)s")
        params["work_kind"] = work_kind
    if subject_id:
        where.append(
            "EXISTS (SELECT 1 FROM subject_links sl WHERE sl.passage_id = p.passage_id "
            "AND sl.subject_id = %(subject_id)s)"
        )
        params["subject_id"] = subject_id

    where_sql = " AND ".join(where)
    total = conn.execute(
        f"""
        SELECT count(*) AS n
        FROM passages p
        JOIN editions e USING (edition_id)
        JOIN works w USING (work_id)
        WHERE {where_sql}
        """,
        params,
    ).fetchone()["n"]

    items = conn.execute(
        f"""
        SELECT p.passage_id, p.edition_id, p.seq, p.kind, p.hadith_num, p.part, p.page,
               p.source,
               e.title_ar AS edition_title, w.work_id, w.title_ar AS work_title,
               ts_rank(p.tsv, websearch_to_tsquery('simple', %(q)s)) AS rank,
               ts_headline('simple', p.text_norm,
                           websearch_to_tsquery('simple', %(q)s),
                           'StartSel=<mark>, StopSel=</mark>, MaxWords=40, MinWords=20, MaxFragments=2, FragmentDelimiter= … ')
                   AS snippet
        FROM passages p
        JOIN editions e USING (edition_id)
        JOIN works w USING (work_id)
        WHERE {where_sql}
        ORDER BY rank DESC, p.passage_id
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
    ).fetchall()

    return {"total": total, "items": items}
