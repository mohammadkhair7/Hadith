"""Isnad chain quality report (chain-completeness QA).

Checks, per matn edition and corpus-wide:
  1. coverage        — units with an extracted chain / total units
  2. boundary source — strong Prophet-speech marker vs generic speech opener
                       vs none (no stored boundary)
  3. dropped_mention — chains where a candidate narrator mention was REJECTED
                       (length bounds); these are the "possibly missing
                       narrator" cases and are flagged for review
  4. position gaps   — consecutive-pair joins skipped to avoid false edges
  5. hop statistics  — distribution sanity (median chain length)

Run after every extraction round:
    .venv\\Scripts\\python ops\\validate_chains.py           # local
    DATABASE_URL=... python ops/validate_chains.py           # Railway
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

from app.db import pool  # noqa: E402

pool.open()
with pool.connection() as conn:
    tot = conn.execute("""
        SELECT
          (SELECT count(*) FROM passages WHERE kind='unit')           AS units,
          count(*)                                                    AS chains,
          count(*) FILTER (WHERE sanad_end_raw IS NOT NULL)           AS with_boundary,
          count(*) FILTER (WHERE meta->'flags' ? 'speech_boundary')   AS speech_boundary,
          count(*) FILTER (WHERE meta->'flags' ? 'dropped_mention')   AS dropped_mention,
          count(*) FILTER (WHERE meta->'flags' ? 'no_matn_marker')    AS no_marker,
          round(avg(confidence)::numeric, 3)                          AS avg_conf
        FROM isnad_chains
    """).fetchone()
    print("=== corpus totals ===")
    print(f"units:            {tot['units']:,}")
    print(f"chains:           {tot['chains']:,}  "
          f"(coverage {100 * tot['chains'] / max(tot['units'], 1):.1f}%)")
    print(f"matn boundary:    {tot['with_boundary']:,} stored "
          f"({tot['speech_boundary']:,} via generic speech opener)")
    print(f"no matn marker:   {tot['no_marker']:,}")
    print(f"DROPPED MENTION:  {tot['dropped_mention']:,} chains flagged "
          f"({100 * tot['dropped_mention'] / max(tot['chains'], 1):.2f}%) — review queue")
    print(f"avg confidence:   {tot['avg_conf']}")

    gaps = conn.execute("""
        SELECT count(*) AS n FROM (
            SELECT chain_id, pos, lead(pos) OVER (PARTITION BY chain_id ORDER BY pos) AS nxt
            FROM isnad_links) s
        WHERE nxt - pos > 1
    """).fetchone()["n"]
    print(f"position gaps:    {gaps:,} (pair joins safely skipped)")

    hops = conn.execute("""
        SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY n) AS median,
               min(n) AS min, max(n) AS max
        FROM (SELECT chain_id, count(*) AS n FROM isnad_links GROUP BY chain_id) s
    """).fetchone()
    print(f"hops per chain:   median {hops['median']}, min {hops['min']}, max {hops['max']}")

    print("\n=== per-edition (worst coverage first) ===")
    rows = conn.execute("""
        SELECT w.title_ar,
               count(DISTINCT p.passage_id) FILTER (WHERE p.kind='unit')  AS units,
               count(DISTINCT c.chain_id)                                  AS chains,
               count(DISTINCT c.chain_id)
                 FILTER (WHERE c.meta->'flags' ? 'dropped_mention')        AS flagged
        FROM editions e
        JOIN works w USING (work_id)
        JOIN passages p USING (edition_id)
        LEFT JOIN isnad_chains c ON c.passage_id = p.passage_id
        WHERE w.kind='matn'
        GROUP BY 1 HAVING count(*) FILTER (WHERE p.kind='unit') > 0
        ORDER BY count(DISTINCT c.chain_id)::float
                 / NULLIF(count(DISTINCT p.passage_id) FILTER (WHERE p.kind='unit'), 0)
    """).fetchall()
    for r in rows:
        cov = 100 * r["chains"] / max(r["units"], 1)
        print(f"  {cov:5.1f}%  {r['chains']:>7,}/{r['units']:<7,} "
              f"flagged {r['flagged']:>5,}  {r['title_ar']}")

    print("\n=== review sample: dropped-mention chains (top confidence) ===")
    rows = conn.execute("""
        SELECT c.passage_id, p.hadith_num, w.title_ar,
               left(p.text_raw, 100) AS head
        FROM isnad_chains c
        JOIN passages p USING (passage_id)
        JOIN editions e ON e.edition_id = p.edition_id
        JOIN works w USING (work_id)
        WHERE c.meta->'flags' ? 'dropped_mention'
        ORDER BY c.confidence DESC LIMIT 5
    """).fetchall()
    for r in rows:
        print(f"  p{r['passage_id']} [{r['title_ar']} #{r['hadith_num']}] {r['head']}...")
