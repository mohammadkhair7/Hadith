"""Push locally precomputed passage_annotations (e.g. the neural-tashkeel
diacritized display layer) to the Railway Postgres.

Rows are mapped by the natural key (edition source, source_book_id, passage
seq) rather than raw passage_id, because serial passage ids can diverge
between local and remote after per-edition reloads (e.g. the Bukhari
replacement). Upserted per (passage_id, layer, engine, version); remote rows
absent locally are removed (local is canonical). Local URL comes from backend
settings; remote from RAILWAY_PG_URL env (never printed)."""
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

COPY_OUT = """
    COPY (
        SELECT e.source, e.source_book_id, p.seq,
               pa.layer, pa.engine, pa.version, pa.payload, pa.created_at
        FROM passage_annotations pa
        JOIN passages p USING (passage_id)
        JOIN editions e USING (edition_id)
    ) TO STDOUT (FORMAT binary)
"""

with psycopg.connect(settings.database_url) as src, \
        psycopg.connect(remote_url, connect_timeout=20) as dst:
    n_src = src.execute("SELECT count(*) FROM passage_annotations").fetchone()[0]
    t0 = time.time()
    dst.execute("""
        CREATE TEMP TABLE _pa_in (
            source text, source_book_id int, seq int,
            layer text, engine text, version text,
            payload jsonb, created_at timestamptz
        ) ON COMMIT DROP
    """)
    with src.cursor().copy(COPY_OUT) as out, \
            dst.cursor().copy("COPY _pa_in FROM STDIN (FORMAT binary)") as inp:
        for data in out:
            inp.write(data)
    staged = dst.execute("SELECT count(*) FROM _pa_in").fetchone()[0]

    # resolve to remote passage ids via the natural key
    dst.execute("""
        CREATE TEMP TABLE _pa_map ON COMMIT DROP AS
        SELECT p.passage_id, i.layer, i.engine, i.version,
               i.payload, i.created_at
        FROM _pa_in i
        JOIN editions e ON e.source = i.source
                       AND e.source_book_id = i.source_book_id
        JOIN passages p ON p.edition_id = e.edition_id AND p.seq = i.seq
    """)
    mapped = dst.execute("SELECT count(*) FROM _pa_map").fetchone()[0]
    if mapped < staged:
        print(f"WARNING: {staged - mapped} annotation rows had no matching "
              f"remote passage and were skipped")

    dst.execute("""
        INSERT INTO passage_annotations AS pa
            (passage_id, layer, engine, version, payload, created_at)
        SELECT passage_id, layer, engine, version, payload, created_at
        FROM _pa_map
        ON CONFLICT (passage_id, layer, engine, version)
        DO UPDATE SET payload = EXCLUDED.payload, created_at = EXCLUDED.created_at
    """)
    # mirror semantics: local is canonical — drop remote rows that no longer
    # exist locally (e.g. superseded annotation versions)
    stale = dst.execute("""
        DELETE FROM passage_annotations pa
        WHERE NOT EXISTS (
            SELECT 1 FROM _pa_map m
            WHERE m.passage_id = pa.passage_id AND m.layer = pa.layer
              AND m.engine = pa.engine AND m.version = pa.version
        )
    """).rowcount
    if stale:
        print(f"removed {stale} stale remote rows")
    n_dst = dst.execute("SELECT count(*) FROM passage_annotations").fetchone()[0]
    dst.execute("ANALYZE passage_annotations")
    dst.commit()
    print(f"passage_annotations: local={n_src} staged={staged} mapped={mapped} "
          f"remote={n_dst} in {time.time()-t0:.0f}s", flush=True)
print("done.")
