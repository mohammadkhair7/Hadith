"""Remove the alifta page-archive pseudo-book (edition 131) from the app:
it is a notes/reference archive, not a book (user request 2026-08-20). The raw
html files remain on disk under Alifta.chat/data/raw as reference material.
Deletes passages -> edition -> orphaned work. DATABASE_URL-driven (local+Railway)."""
import os
import sys

import psycopg

EDITION_ID = 131

sys.stdout.reconfigure(encoding="utf-8")
url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit("DATABASE_URL not set")

with psycopg.connect(url) as conn:
    e = conn.execute(
        "SELECT work_id, source, title_ar, passage_count FROM editions WHERE edition_id=%s",
        (EDITION_ID,)).fetchone()
    if not e:
        print(f"edition {EDITION_ID} not present — nothing to do")
        sys.exit(0)
    work_id, source, title, count = e
    if source != "alifta":
        sys.exit(f"safety: edition {EDITION_ID} source is {source!r}, expected 'alifta'")
    print(f"removing edition {EDITION_ID} ({title}, {count} passages)")

    # no dependents were found in the audit; passages FKs cascade for
    # annotations/grades/types, the rest is deleted explicitly for clarity
    for tbl in ("passage_annotations", "hadith_grades", "hadith_types",
                "subject_links", "isnad_links"):
        if tbl == "isnad_links":
            n = conn.execute("""
                DELETE FROM isnad_links WHERE chain_id IN (
                    SELECT chain_id FROM isnad_chains c JOIN passages p USING (passage_id)
                    WHERE p.edition_id=%s)""", (EDITION_ID,)).rowcount
        else:
            n = conn.execute(f"""
                DELETE FROM {tbl} WHERE passage_id IN (
                    SELECT passage_id FROM passages WHERE edition_id=%s)""",
                (EDITION_ID,)).rowcount
        if n:
            print(f"  {tbl}: {n}")
    conn.execute("DELETE FROM isnad_chains WHERE passage_id IN "
                 "(SELECT passage_id FROM passages WHERE edition_id=%s)", (EDITION_ID,))
    n = conn.execute("DELETE FROM passages WHERE edition_id=%s", (EDITION_ID,)).rowcount
    print(f"  passages: {n}")
    conn.execute("DELETE FROM toc_nodes WHERE edition_id=%s", (EDITION_ID,))
    conn.execute("DELETE FROM editions WHERE edition_id=%s", (EDITION_ID,))
    orphan = conn.execute(
        "SELECT NOT EXISTS (SELECT 1 FROM editions WHERE work_id=%s)", (work_id,)
    ).fetchone()[0]
    if orphan:
        conn.execute("DELETE FROM works WHERE work_id=%s", (work_id,))
        print(f"  work {work_id}: removed (no other editions)")
    conn.execute("""
        INSERT INTO etl_state (step, status, detail)
        VALUES ('remove_alifta_edition_131', 'done', '{"reason": "notes archive, not a book"}')
        ON CONFLICT (step) DO UPDATE SET status='done', updated_at=now()
    """)
    conn.commit()
print("done")
