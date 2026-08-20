"""Apply the KG/analytics schema deltas to the Railway Postgres before the
isnad/grades data transfer. Reads RAILWAY_PG_URL from env (never printed)."""
import os
import sys

import psycopg

url = os.environ.get("RAILWAY_PG_URL")
if not url:
    sys.exit("RAILWAY_PG_URL not set")

DDL = """
ALTER TABLE isnad_chains ADD COLUMN IF NOT EXISTS sanad_end_raw int;

CREATE TABLE IF NOT EXISTS hadith_grades (
    passage_id bigint PRIMARY KEY REFERENCES passages,
    grade_ar   text NOT NULL,
    grade_norm text NOT NULL,
    source     text NOT NULL,
    meta       jsonb DEFAULT '{}'::jsonb,
    created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS hadith_grades_norm ON hadith_grades (grade_norm);

CREATE INDEX IF NOT EXISTS isnad_links_mention ON isnad_links (mention_norm);
"""

with psycopg.connect(url, connect_timeout=20) as conn:
    conn.execute(DDL)
    conn.commit()
    cols = conn.execute("""
        SELECT count(*) FROM information_schema.columns
        WHERE table_name='isnad_chains' AND column_name='sanad_end_raw'
    """).fetchone()[0]
    tbl = conn.execute("""
        SELECT count(*) FROM information_schema.tables WHERE table_name='hadith_grades'
    """).fetchone()[0]
    print("sanad_end_raw column:", bool(cols), "| hadith_grades table:", bool(tbl))
