"""Stage locally computed Shamela embeddings into Railway Postgres.

Railway's Redis is only reachable from inside the Railway network, so the
transfer is two-hop: this script copies the vectors from the LOCAL Redis into
a `vector_stage` table on the Railway Postgres (remapping edition/passage ids
by natural key — serial ids differ between environments), then the production
app imports the staged rows into its own Redis via
POST /admin/embeddings/import-staged (Admin → Embeddings button).

Only source='shamela' editions are pushed (owner directive 2026-08-21: the
sunna pilot embedding of الشمائل المحمدية is NOT uploaded — the Shamela
edition of that work is included like every other Shamela book). Stale sunna
ledger rows on Railway are removed so coverage reflects reality.

Usage (local shell):
    $env:RAILWAY_PG_URL = <public proxy url>   # never printed
    python ops\\railway_push_vectors.py
"""
import os
import sys
import time
from pathlib import Path

import psycopg
import redis

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import settings  # noqa: E402

BATCH = 2000


def main() -> None:
    dst_url = os.environ.get("RAILWAY_PG_URL")
    if not dst_url:
        sys.exit("RAILWAY_PG_URL not set")
    local_pg = os.environ.get("LOCAL_PG_URL") or settings.database_url
    r = redis.from_url(settings.redis_url, decode_responses=False)
    prefix = f"{settings.redis_prefix}:emb:"

    with psycopg.connect(local_pg) as src, psycopg.connect(dst_url) as dst:
        # natural-key maps: local passage -> (bkid, seq) -> railway passage
        l_ed = {row[0]: row[1] for row in src.execute(
            "SELECT edition_id, source_book_id FROM editions WHERE source='shamela'")}
        r_ed = {row[1]: (row[0], row[2]) for row in dst.execute(
            "SELECT edition_id, source_book_id, work_id FROM editions WHERE source='shamela'")}
        print(f"editions: local {len(l_ed)}, railway {len(r_ed)}")

        l_pass: dict[int, tuple[int, int]] = {}
        for pid, eid, seq in src.execute(
                "SELECT p.passage_id, p.edition_id, p.seq FROM passages p "
                "JOIN editions e USING (edition_id) WHERE e.source='shamela'"):
            l_pass[pid] = (l_ed[eid], seq)
        r_pass: dict[tuple[int, int], int] = {}
        for pid, bkid, seq in dst.execute(
                "SELECT p.passage_id, e.source_book_id, p.seq FROM passages p "
                "JOIN editions e USING (edition_id) WHERE e.source='shamela'"):
            r_pass[(bkid, seq)] = pid
        print(f"passages: local {len(l_pass)}, railway {len(r_pass)}")

        dst.execute("""
            CREATE TABLE IF NOT EXISTS vector_stage (
                edition_id   int NOT NULL,
                passage_id   bigint NOT NULL,
                chunk_no     int NOT NULL,
                work_id      int NOT NULL,
                kind         text NOT NULL,
                source       text NOT NULL,
                hadith_num   text,
                content_hash text NOT NULL,
                vec          bytea NOT NULL
            )
        """)
        dst.execute("TRUNCATE vector_stage")
        # stale ledger: rows claiming embeddings that are not in Railway Redis
        n = dst.execute(
            "DELETE FROM embedding_jobs j USING editions e "
            "WHERE e.edition_id = j.edition_id AND e.source='sunna'").rowcount
        print(f"removed {n} stale sunna ledger rows on railway")
        dst.commit()

        pushed = skipped = missing = 0
        t0 = time.time()
        with dst.cursor().copy(
                "COPY vector_stage (edition_id, passage_id, chunk_no, work_id, "
                "kind, source, hadith_num, content_hash, vec) FROM STDIN "
                "(FORMAT binary)") as cp:
            cp.set_types(["int4", "int8", "int4", "int4", "text", "text",
                          "text", "text", "bytea"])
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor=cursor, match=prefix + "*", count=5000)
                if keys:
                    pipe = r.pipeline(transaction=False)
                    for k in keys:
                        pipe.hgetall(k)
                    for k, h in zip(keys, pipe.execute()):
                        try:
                            _, _, led, lpid, chunk = k.decode().rsplit(":", 4)
                            led, lpid, chunk = int(led), int(lpid), int(chunk)
                        except ValueError:
                            continue
                        nat = l_pass.get(lpid)
                        if nat is None:              # non-shamela (sunna pilot)
                            skipped += 1
                            continue
                        rp = r_pass.get(nat)
                        red = r_ed.get(nat[0])
                        if rp is None or red is None:
                            missing += 1
                            continue
                        cp.write_row((
                            red[0], rp, chunk, red[1],
                            h.get(b"kind", b"").decode(),
                            h.get(b"source", b"").decode(),
                            h.get(b"hadith_num", b"").decode() or None,
                            h.get(b"content_hash", b"").decode(),
                            h[b"vec"],
                        ))
                        pushed += 1
                        if pushed % 50000 == 0:
                            print(f"  staged {pushed:,} ({time.time()-t0:.0f}s)",
                                  flush=True)
                if cursor == 0:
                    break
        dst.commit()
        total = dst.execute("SELECT count(*) FROM vector_stage").fetchone()[0]
        print(f"staged {pushed:,} vectors in {time.time()-t0:.0f}s "
              f"(skipped {skipped} non-shamela, {missing} unmatched); "
              f"vector_stage rows: {total:,}")
        print("next: Admin → Embeddings → 'Import staged vectors' on production")


if __name__ == "__main__":
    main()
