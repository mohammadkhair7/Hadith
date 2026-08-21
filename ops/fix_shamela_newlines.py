"""Shamela page text uses bare carriage returns (\r) as line separators, which
render as nothing in the reader and defeat heading detection. Replace \r with
\n in passages.text_raw for shamela passages. Same-length replacement, so all
stored raw-text offsets (isnad_chains boundaries, passage_annotations spans)
remain valid. text_norm is whitespace-collapsed already and needs no change.
DATABASE_URL-driven (local + Railway)."""
import os
import sys

import psycopg

sys.stdout.reconfigure(encoding="utf-8")
url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit("DATABASE_URL not set")

with psycopg.connect(url) as conn:
    before = conn.execute("""
        SELECT count(*) FROM passages
        WHERE source='shamela' AND text_raw LIKE '%' || chr(13) || '%'
    """).fetchone()[0]
    print(f"shamela passages containing CR: {before}")
    if before:
        n = conn.execute("""
            UPDATE passages
            SET text_raw = replace(text_raw, chr(13), chr(10))
            WHERE source='shamela' AND text_raw LIKE '%' || chr(13) || '%'
        """).rowcount
        conn.commit()
        print(f"updated {n} passages")
    print("done")
