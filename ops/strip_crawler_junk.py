"""Remove crawler JavaScript artifacts (AddHistory(...) calls) that leaked
into passages.text_raw/text_norm during the sunna crawl (106k service pages).
The tsv column is GENERATED from text_norm, so it refreshes automatically.
Runs against DATABASE_URL/LOCAL_PG_URL (set DATABASE_URL to run on Railway).
"""
import sys
import time
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import settings  # noqa: E402

PATTERN = r"AddHistory\s*\([^)]*\)\s*;?"

with psycopg.connect(settings.database_url) as conn:
    n = conn.execute(
        "SELECT count(*) FROM passages WHERE text_raw ~ %s", (PATTERN,)).fetchone()[0]
    print(f"passages with crawler junk: {n}", flush=True)
    t0 = time.time()
    upd = conn.execute(f"""
        UPDATE passages
        SET text_raw  = btrim(regexp_replace(text_raw,  %s, ' ', 'g')),
            text_norm = btrim(regexp_replace(text_norm, %s, ' ', 'g'))
        WHERE text_raw ~ %s
    """, (PATTERN, PATTERN, PATTERN))
    conn.commit()
    left = conn.execute(
        "SELECT count(*) FROM passages WHERE text_raw ~ %s", (PATTERN,)).fetchone()[0]
    print(f"updated {upd.rowcount} rows in {time.time()-t0:.0f}s; remaining: {left}")
