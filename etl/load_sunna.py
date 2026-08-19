"""Load hadith.db (sunna.alifta.gov.sa crawl) into the unified schema.

Creates: works + editions (one per book), toc_nodes, passages, subjects,
subject_links. Resumable at book granularity via etl_state.
"""
import json
import sqlite3

from db import SOURCES, connect
from normalize import normalize_arabic

BATCH = 2000


def state_done(pg, step: str) -> bool:
    row = pg.execute("SELECT status FROM etl_state WHERE step=%s", (step,)).fetchone()
    return bool(row and row[0] == "done")


def state_mark(pg, step: str, status: str = "done", detail: dict | None = None) -> None:
    pg.execute(
        "INSERT INTO etl_state(step,status,detail,updated_at) VALUES (%s,%s,%s,now()) "
        "ON CONFLICT (step) DO UPDATE SET status=EXCLUDED.status, detail=EXCLUDED.detail, updated_at=now()",
        (step, status, json.dumps(detail or {})),
    )


def load_books(sq, pg) -> dict[int, int]:
    """books -> works + editions; returns {book_id: edition_id}."""
    editions: dict[int, int] = {}
    for bid, name, ord_, book_type, section_id, section_name in sq.execute(
        "SELECT id, name, ord, book_type, section_id, section_name FROM books ORDER BY ord"
    ):
        kind = "matn" if book_type == "matn" else "service"
        norm = normalize_arabic(name)
        row = pg.execute(
            "SELECT e.edition_id, e.work_id FROM editions e WHERE e.source='sunna' AND e.source_book_id=%s",
            (bid,),
        ).fetchone()
        if row:
            editions[bid] = row[0]
            continue
        work_id = pg.execute(
            "INSERT INTO works (title_ar, title_norm, kind) VALUES (%s,%s,%s) RETURNING work_id",
            (name, norm, kind),
        ).fetchone()[0]
        edition_id = pg.execute(
            "INSERT INTO editions (work_id, source, source_book_id, title_ar, section_name, book_type, meta) "
            "VALUES (%s,'sunna',%s,%s,%s,%s,%s) RETURNING edition_id",
            (work_id, bid, name, section_name, book_type,
             json.dumps({"ord": ord_, "section_id": section_id})),
        ).fetchone()[0]
        editions[bid] = edition_id
    pg.commit()
    print(f"[sunna] books: {len(editions)} editions ready")
    return editions


def load_toc(sq, pg, editions: dict[int, int]) -> None:
    for bid, edition_id in editions.items():
        step = f"sunna_toc_{bid}"
        if state_done(pg, step):
            continue
        rows = sq.execute(
            "SELECT node_id, parent_id, title, is_leaf, ord FROM toc WHERE book_id=? ORDER BY node_id",
            (bid,),
        ).fetchall()
        if not rows:
            state_mark(pg, step)
            pg.commit()
            continue
        pg.execute("DELETE FROM toc_nodes WHERE edition_id=%s", (edition_id,))
        # first pass: insert all nodes keyed by source_node_id
        with pg.cursor() as cur:
            with cur.copy(
                "COPY toc_nodes (edition_id, source_node_id, title, title_norm, is_leaf, ord) FROM STDIN"
            ) as cp:
                for node_id, parent_id, title, is_leaf, ord_ in rows:
                    title = title or ""
                    cp.write_row((edition_id, node_id, title, normalize_arabic(title),
                                  bool(is_leaf), ord_ or 0))
        # second pass: wire parents + depth (computed in Python, applied in bulk)
        parent_map = {node_id: parent_id for node_id, parent_id, *_ in rows}
        depth: dict[int, int] = {}

        def get_depth(nid: int) -> int:
            # iterative to avoid recursion limits on deep trees
            chain = []
            cur_id = nid
            while cur_id not in depth:
                chain.append(cur_id)
                p = parent_map.get(cur_id)
                if p is None or p < 0 or p not in parent_map:
                    depth[cur_id] = 0
                    chain.pop()
                    break
                cur_id = p
            for c in reversed(chain):
                p = parent_map.get(c)
                depth[c] = depth[p] + 1 if p is not None and p in depth else 0
            return depth[nid]

        id_map = dict(pg.execute(
            "SELECT source_node_id, toc_node_id FROM toc_nodes WHERE edition_id=%s",
            (edition_id,),
        ).fetchall())
        updates = []
        for node_id, parent_id, *_ in rows:
            pid = id_map.get(parent_id) if parent_id is not None and parent_id >= 0 else None
            updates.append((pid, get_depth(node_id), id_map[node_id]))
        with pg.cursor() as cur:
            cur.executemany(
                "UPDATE toc_nodes SET parent_id=%s, depth=%s WHERE toc_node_id=%s", updates
            )
        state_mark(pg, step, detail={"nodes": len(rows)})
        pg.commit()
        print(f"[sunna] toc book {bid}: {len(rows)} nodes")


def load_passages(sq, pg, editions: dict[int, int]) -> None:
    for bid, edition_id in editions.items():
        step = f"sunna_passages_{bid}"
        if state_done(pg, step):
            continue
        rows = sq.execute(
            "SELECT main_id, html, text_plain, hadith_num, part_page, prev_id, next_id "
            "FROM matn WHERE book_id=? AND main_id IS NOT NULL ORDER BY main_id",
            (bid,),
        ).fetchall()
        pg.execute("DELETE FROM subject_links WHERE passage_id IN (SELECT passage_id FROM passages WHERE edition_id=%s)", (edition_id,))
        pg.execute("DELETE FROM passages WHERE edition_id=%s", (edition_id,))
        kind_book = pg.execute(
            "SELECT book_type FROM editions WHERE edition_id=%s", (edition_id,)
        ).fetchone()[0]
        n = 0
        with pg.cursor() as cur:
            with cur.copy(
                "COPY passages (edition_id, source, source_page_id, seq, kind, hadith_num, "
                "part, page, text_raw, text_norm, html, meta) FROM STDIN"
            ) as cp:
                for seq, (main_id, html, text_plain, hadith_num, part_page, prev_id, next_id) in enumerate(rows):
                    text_raw = text_plain or ""
                    part, page = None, None
                    if part_page and "/" in str(part_page):
                        part, page = str(part_page).split("/", 1)
                    kind = "unit" if (kind_book == "matn") else "page"
                    meta = {"prev_id": prev_id, "next_id": next_id}
                    cp.write_row((
                        edition_id, "sunna", main_id, seq, kind,
                        str(hadith_num) if hadith_num is not None else None,
                        part, page, text_raw, normalize_arabic(text_raw), html,
                        json.dumps(meta, ensure_ascii=False),
                    ))
                    n += 1
        # anchor passages to leaf TOC nodes that share the source node id
        pg.execute(
            """
            UPDATE passages ps SET toc_node_id = t.toc_node_id
            FROM toc_nodes t
            WHERE ps.edition_id = %s AND t.edition_id = %s
              AND t.is_leaf AND t.source_node_id = ps.source_page_id
            """,
            (edition_id, edition_id),
        )
        pg.execute(
            "UPDATE editions SET passage_count=%s WHERE edition_id=%s", (n, edition_id)
        )
        state_mark(pg, step, detail={"passages": n})
        pg.commit()
        print(f"[sunna] passages book {bid}: {n}")


def load_subjects(sq, pg) -> None:
    if state_done(pg, "sunna_subjects"):
        return
    rows = sq.execute(
        "SELECT node_id, parent_id, title, is_leaf, ord FROM subjects ORDER BY node_id"
    ).fetchall()
    pg.execute("DELETE FROM subject_links")
    pg.execute("DELETE FROM subjects")
    with pg.cursor() as cur:
        with cur.copy(
            "COPY subjects (source_node_id, title, title_norm, is_leaf, ord) FROM STDIN"
        ) as cp:
            for node_id, parent_id, title, is_leaf, ord_ in rows:
                title = title or ""
                cp.write_row((node_id, title, normalize_arabic(title), bool(is_leaf), ord_ or 0))
    # parent wiring
    id_map = dict(pg.execute("SELECT source_node_id, subject_id FROM subjects").fetchall())
    parent_rows = [
        (id_map[parent_id], id_map[node_id])
        for node_id, parent_id, *_ in rows
        if parent_id is not None and parent_id >= 0 and parent_id in id_map and node_id in id_map
    ]
    with pg.cursor() as cur:
        cur.executemany("UPDATE subjects SET parent_id=%s WHERE subject_id=%s", parent_rows)
    state_mark(pg, "sunna_subjects", detail={"subjects": len(rows)})
    pg.commit()
    print(f"[sunna] subjects: {len(rows)}")


def load_subject_links(sq, pg) -> None:
    if state_done(pg, "sunna_subject_links"):
        return
    # passage lookup: (book_id, main_id) -> passage_id
    plook = {}
    for edition_id, book_id in pg.execute(
        "SELECT edition_id, source_book_id FROM editions WHERE source='sunna'"
    ).fetchall():
        for spid, pid in pg.execute(
            "SELECT source_page_id, passage_id FROM passages WHERE edition_id=%s", (edition_id,)
        ).fetchall():
            plook[(book_id, spid)] = pid
    slook = dict(pg.execute("SELECT source_node_id, subject_id FROM subjects").fetchall())
    pg.execute("DELETE FROM subject_links")
    n, missing = 0, 0
    seen: set[tuple[int, int]] = set()
    with pg.cursor() as cur:
        with cur.copy("COPY subject_links (subject_id, passage_id, ord) FROM STDIN") as cp:
            for subject_id, book_id, main_id, ord_ in sq.execute(
                "SELECT subject_id, book_id, main_id, ord FROM subject_hits"
            ):
                sid = slook.get(subject_id)
                pid = plook.get((book_id, main_id))
                if sid is None or pid is None:
                    missing += 1
                    continue
                if (sid, pid) in seen:
                    continue
                seen.add((sid, pid))
                cp.write_row((sid, pid, ord_ or 0))
                n += 1
    state_mark(pg, "sunna_subject_links", detail={"links": n, "missing": missing})
    pg.commit()
    print(f"[sunna] subject_links: {n} (missing refs: {missing})")


def main() -> None:
    sq = sqlite3.connect(SOURCES["hadith"])
    with connect() as pg:
        editions = load_books(sq, pg)
        load_toc(sq, pg, editions)
        load_passages(sq, pg, editions)
        load_subjects(sq, pg)
        load_subject_links(sq, pg)
    print("[sunna] done")


if __name__ == "__main__":
    main()
