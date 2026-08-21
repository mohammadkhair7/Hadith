"""Remove the redundant duplicate work: شرح مشكل الآثار (work with aljam3 #85,
1,004 pages) — a much shorter duplicate of the complete work (aljam3 #31,
7,274 pages). Approved in docs/ALSHAMELA_BOOK_SOURCES.md §4.3 decision 1.

Deletes the sunna edition (source_book_id=85), all passage dependents, and the
now-empty work row. DATABASE_URL-driven (local + Railway); idempotent."""
import os
import sys
from pathlib import Path

import psycopg

sys.stdout.reconfigure(encoding="utf-8")


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("LOCAL_PG_URL")
    if url:
        return url
    env = Path(__file__).resolve().parents[1] / ".env.local"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith(("DATABASE_URL=", "LOCAL_PG_URL=")):
                return line.split("=", 1)[1].strip().strip('"')
    sys.exit("no DATABASE_URL / LOCAL_PG_URL found")


DEPENDENTS = [
    ("translations", "DELETE FROM translations t USING passages p "
     "WHERE t.obj_type='passage' AND t.obj_id=p.passage_id AND p.edition_id=%s"),
    ("grades", "DELETE FROM hadith_grades g USING passages p "
     "WHERE g.passage_id=p.passage_id AND p.edition_id=%s"),
    ("subject_links", "DELETE FROM subject_links s USING passages p "
     "WHERE s.passage_id=p.passage_id AND p.edition_id=%s"),
    ("annotations", "DELETE FROM passage_annotations a USING passages p "
     "WHERE a.passage_id=p.passage_id AND p.edition_id=%s"),
    ("hadith_types", "DELETE FROM hadith_types h USING passages p "
     "WHERE h.passage_id=p.passage_id AND p.edition_id=%s"),
    ("hadith_dates", "DELETE FROM hadith_dates h USING passages p "
     "WHERE h.passage_id=p.passage_id AND p.edition_id=%s"),
    ("embedding_jobs", "DELETE FROM embedding_jobs WHERE edition_id=%s"),
    ("isnad_links", "DELETE FROM isnad_links l USING isnad_chains c, passages p "
     "WHERE l.chain_id=c.chain_id AND c.passage_id=p.passage_id AND p.edition_id=%s"),
    ("isnad_chains", "DELETE FROM isnad_chains c USING passages p "
     "WHERE c.passage_id=p.passage_id AND p.edition_id=%s"),
    ("toc_nodes", "DELETE FROM toc_nodes WHERE edition_id=%s"),
    ("passages", "DELETE FROM passages WHERE edition_id=%s"),
    ("editions", "DELETE FROM editions WHERE edition_id=%s"),
]


def main() -> None:
    with psycopg.connect(_db_url()) as conn:
        # unit_map may not exist yet on this environment
        if conn.execute("SELECT to_regclass('unit_map')").fetchone()[0]:
            DEPENDENTS.insert(0, (
                "unit_map", "DELETE FROM unit_map m USING passages p "
                "WHERE m.aljam3_passage_id=p.passage_id AND p.edition_id=%s"))
        row = conn.execute("""
            SELECT edition_id, work_id, title_ar, passage_count FROM editions
            WHERE source='sunna' AND source_book_id=85
        """).fetchone()
        if not row:
            print("sunna edition #85 already gone")
            return
        eid, wid, title, count = row
        if count > 1100:
            sys.exit(f"unexpected passage count {count}; aborting")
        stats = {}
        for label, sql in DEPENDENTS:
            stats[label] = conn.execute(sql, (eid,)).rowcount
        others = conn.execute(
            "SELECT count(*) FROM editions WHERE work_id=%s", (wid,)).fetchone()[0]
        if others == 0:
            conn.execute("DELETE FROM works WHERE work_id=%s", (wid,))
        conn.commit()
        removed = {k: v for k, v in stats.items() if v}
        print(f"edition {eid} «{title}» (work {wid}) removed: {removed}; "
              f"work row {'deleted' if others == 0 else 'kept (other editions)'}")


if __name__ == "__main__":
    main()
