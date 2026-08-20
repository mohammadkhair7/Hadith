"""Push the locally-built KG/analytics tables to the Railway Postgres:
narrators, narrator_aliases, narrator_assessments, isnad_chains, isnad_links,
hadith_grades. Children are truncated first, data is streamed with binary
COPY, and id sequences are resynced. Local URL comes from backend settings;
remote from RAILWAY_PG_URL env (never printed)."""
import os
import sys
import time
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import settings  # noqa: E402

remote_url = os.environ.get("RAILWAY_PG_URL")
if not remote_url:
    sys.exit("RAILWAY_PG_URL not set")

TABLES = ["narrators", "narrator_aliases", "narrator_assessments",
          "isnad_chains", "isnad_links", "hadith_grades"]
SEQS = [("narrators", "narrator_id"), ("narrator_aliases", "alias_id"),
        ("narrator_assessments", "assessment_id"), ("isnad_chains", "chain_id")]

with psycopg.connect(settings.database_url) as src, \
        psycopg.connect(remote_url, connect_timeout=20) as dst:
    dst.execute("TRUNCATE " + ", ".join(reversed(TABLES)) + " CASCADE")
    for t in TABLES:
        n_src = src.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        t0 = time.time()
        with src.cursor().copy(f"COPY {t} TO STDOUT (FORMAT binary)") as out, \
                dst.cursor().copy(f"COPY {t} FROM STDIN (FORMAT binary)") as inp:
            for data in out:
                inp.write(data)
        n_dst = dst.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        ok = "OK" if n_src == n_dst else "MISMATCH"
        print(f"{t}: {n_dst}/{n_src} rows in {time.time()-t0:.0f}s [{ok}]", flush=True)
    for t, col in SEQS:
        dst.execute(f"SELECT setval(pg_get_serial_sequence('{t}', '{col}'), "
                    f"GREATEST((SELECT COALESCE(MAX({col}),1) FROM {t}), 1))")
    dst.execute("ANALYZE " + ", ".join(TABLES))
    dst.commit()
print("done.")
