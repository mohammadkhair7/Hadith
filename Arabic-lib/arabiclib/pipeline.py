"""Batch annotation pipeline (§12.2): stream passages from Postgres, annotate
with the engine registry, write passage_annotations. Resumable: existing
(passage_id, layer, engine, version) rows are skipped.

CLI (run from AdvancedHadith/):
    .venv\\Scripts\\python -m arabiclib.pipeline --edition 18 --layers roots,pos,ner
"""
import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "backend"))

from .engines.registry import ALL_LAYERS, annotate_batch, available_engines

BATCH = 32


def _pool():
    from app.db import pool
    pool.open()
    return pool


def annotate_edition(edition_id: int, layers: list[str], *, limit: int | None = None,
                     overwrite: bool = False) -> dict:
    pool = _pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT passage_id, text_raw FROM passages WHERE edition_id=%s "
            "ORDER BY seq" + (f" LIMIT {int(limit)}" if limit else ""),
            (edition_id,)).fetchall()
        done = {
            (r["passage_id"], r["layer"], r["engine"])
            for r in conn.execute(
                "SELECT DISTINCT passage_id, layer, engine FROM passage_annotations "
                "WHERE passage_id IN (SELECT passage_id FROM passages WHERE edition_id=%s)",
                (edition_id,)).fetchall()
        } if not overwrite else set()

    written = skipped = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        anns = annotate_batch([r["text_raw"] for r in batch], layers)
        payload_rows = []
        for r, ann in zip(batch, anns):
            engines = ann.meta.get("engines", {})
            for layer, payload in ann.to_payloads().items():
                engine = engines.get(layer, "?")
                if (r["passage_id"], layer, engine) in done:
                    skipped += 1
                    continue
                payload_rows.append((r["passage_id"], layer, engine, "0.1.0",
                                     json.dumps(payload, ensure_ascii=False)))
        if payload_rows:
            with pool.connection() as conn:
                conn.cursor().executemany("""
                    INSERT INTO passage_annotations (passage_id, layer, engine, version, payload)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (passage_id, layer, engine, version)
                    DO UPDATE SET payload=EXCLUDED.payload, created_at=now()
                """, payload_rows)
                conn.commit()
            written += len(payload_rows)
        print(f"  {min(i + BATCH, len(rows))}/{len(rows)} passages "
              f"({written} annotations written, {skipped} skipped)", flush=True)
    return {"passages": len(rows), "written": written, "skipped": skipped}


def main() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    ap = argparse.ArgumentParser(description="Batch-annotate passages")
    ap.add_argument("--edition", type=int, required=False)
    ap.add_argument("--layers", default=",".join(ALL_LAYERS))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--engines", action="store_true", help="show engine availability and exit")
    args = ap.parse_args()

    if args.engines:
        print(json.dumps(available_engines(), ensure_ascii=False, indent=1))
        return
    if not args.edition:
        ap.error("--edition required (or use --engines)")
    layers = [l.strip() for l in args.layers.split(",") if l.strip()]
    stats = annotate_edition(args.edition, layers, limit=args.limit,
                             overwrite=args.overwrite)
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
