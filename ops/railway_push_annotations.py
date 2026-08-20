"""Push locally precomputed passage_annotations (e.g. the neural-tashkeel
diacritized display layer) to the Railway Postgres. Rows are upserted per
(passage_id, layer, engine, version) so re-runs are safe. Local URL comes
from backend settings; remote from RAILWAY_PG_URL env (never printed)."""
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

with psycopg.connect(settings.database_url) as src, \
        psycopg.connect(remote_url, connect_timeout=20) as dst:
    n_src = src.execute("SELECT count(*) FROM passage_annotations").fetchone()[0]
    t0 = time.time()
    dst.execute("""
        CREATE TEMP TABLE _pa_in
        (LIKE passage_annotations INCLUDING DEFAULTS) ON COMMIT DROP
    """)
    with src.cursor().copy(
            "COPY passage_annotations TO STDOUT (FORMAT binary)") as out, \
            dst.cursor().copy("COPY _pa_in FROM STDIN (FORMAT binary)") as inp:
        for data in out:
            inp.write(data)
    dst.execute("""
        INSERT INTO passage_annotations AS pa
        SELECT * FROM _pa_in
        ON CONFLICT (passage_id, layer, engine, version)
        DO UPDATE SET payload = EXCLUDED.payload, created_at = EXCLUDED.created_at
    """)
    n_dst = dst.execute("SELECT count(*) FROM passage_annotations").fetchone()[0]
    dst.execute("ANALYZE passage_annotations")
    dst.commit()
    print(f"passage_annotations: local={n_src} remote={n_dst} "
          f"in {time.time()-t0:.0f}s", flush=True)
print("done.")
