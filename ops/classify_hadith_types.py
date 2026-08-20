"""Populate hadith_types (نوع الحديث) for every chain-bearing passage using
the rule classifier v0.1 (backend/app/services/classify.py). Idempotent:
recreates the classification for the whole corpus each run. Works against
DATABASE_URL, so the same script serves local and Railway."""
import os
import sys
import time
from collections import Counter
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.stdout.reconfigure(encoding="utf-8")
from app.services.classify import HADITH_TYPES, classify_hadith_type  # noqa: E402

DDL = """
CREATE TABLE IF NOT EXISTS hadith_types (
    passage_id  bigint PRIMARY KEY REFERENCES passages ON DELETE CASCADE,
    type_norm   text NOT NULL,
    type_ar     text NOT NULL,
    method      text NOT NULL DEFAULT 'rule-0.1',
    confidence  real DEFAULT 0,
    updated_at  timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS hadith_types_norm ON hadith_types (type_norm);
"""


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    t0 = time.time()
    with psycopg.connect(url) as conn:
        conn.execute(DDL)
        conn.execute("DELETE FROM hadith_types WHERE method='rule-0.1'")
        rows = conn.execute("""
            SELECT c.passage_id, p.text_raw, c.sanad_end_raw, n.generation
            FROM isnad_chains c
            JOIN passages p USING (passage_id)
            LEFT JOIN LATERAL (
                SELECT nr.generation
                FROM isnad_links l JOIN narrators nr ON nr.narrator_id = l.narrator_id
                WHERE l.chain_id = c.chain_id
                ORDER BY l.pos DESC LIMIT 1
            ) n ON true
            WHERE c.ord = 0
        """).fetchall()
        print(f"chains to classify: {len(rows)} ({time.time()-t0:.0f}s fetch)")

        dist: Counter = Counter()
        buf = []
        for pid, raw, end, gen in rows:
            r = classify_hadith_type(raw or "", end, gen)
            if not r:
                dist["(none)"] += 1
                continue
            key, conf = r
            dist[key] += 1
            buf.append((pid, key, HADITH_TYPES[key], conf))
        print(f"classified in {time.time()-t0:.0f}s; inserting {len(buf)}")

        with conn.cursor() as cur:
            with cur.copy(
                "COPY hadith_types (passage_id, type_norm, type_ar, confidence) FROM STDIN"
            ) as cp:
                for row in buf:
                    cp.write_row(row)
        conn.execute("ANALYZE hadith_types")
        conn.commit()
    print(f"done in {time.time()-t0:.0f}s; distribution:")
    for k, v in dist.most_common():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
