"""Phase 6 KG builder (§9.2): extract isnad chains from a matn edition's
hadith units, resolve narrator mentions to entities, and build the Apache AGE
graph `hadith_graph` (Narrator nodes + NARRATED_FROM edges).

    .venv\\Scripts\\python ops\\build_kg.py --edition 1            # صحيح البخاري
    .venv\\Scripts\\python ops\\build_kg.py --edition 1 --rebuild-graph
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Arabic-lib"))

from app.db import pool  # noqa: E402
from app.services.normalize import normalize_arabic  # noqa: E402
from arabiclib.isnad import parse_isnad  # noqa: E402

GRAPH = "hadith_graph"
MIN_MENTION_COUNT = 2          # mentions seen once are kept in links but not promoted to entities
EXTRACTOR = "rule-0.2"

_BAD_MENTION = re.compile(
    r"^(رسول الله|النبي|الله|ابيه|ابيها|جده|امه)\b")


def extract_chains(edition_id: int) -> dict:
    """Stage 1-2: parse isnads for every unit passage; write chains + links."""
    with pool.connection() as conn:
        rows = conn.execute("""
            SELECT passage_id, text_raw FROM passages
            WHERE edition_id=%s AND kind='unit' ORDER BY seq
        """, (edition_id,)).fetchall()
        conn.execute("""
            DELETE FROM isnad_links WHERE chain_id IN (
                SELECT chain_id FROM isnad_chains c JOIN passages p USING (passage_id)
                WHERE p.edition_id=%s)
        """, (edition_id,))
        conn.execute("""
            DELETE FROM isnad_chains WHERE passage_id IN (
                SELECT passage_id FROM passages WHERE edition_id=%s)
        """, (edition_id,))
        conn.commit()

    n_chains = n_links = 0
    with pool.connection() as conn:
        cur = conn.cursor()
        for r in rows:
            p = parse_isnad(r["text_raw"])
            if len(p.hops) < 2 or p.confidence < 0.5:
                continue
            chain_id = cur.execute("""
                INSERT INTO isnad_chains (passage_id, ord, confidence, extractor,
                                          sanad_end_raw, meta)
                VALUES (%s, 0, %s, %s, %s, %s) RETURNING chain_id
            """, (r["passage_id"], p.confidence, EXTRACTOR,
                  p.sanad_end_raw if p.sanad_end_raw > 0 else None,
                  json.dumps({"flags": p.flags} if p.flags else {}))).fetchone()["chain_id"]
            for hop in p.hops:
                mention_norm = normalize_arabic(hop.mention)
                if _BAD_MENTION.match(mention_norm):
                    continue
                cur.execute("""
                    INSERT INTO isnad_links (chain_id, pos, mention_ar, mention_norm,
                                             verb, confidence)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (chain_id, pos) DO NOTHING
                """, (chain_id, hop.pos, hop.mention, mention_norm, hop.verb,
                      p.confidence))
                n_links += 1
            n_chains += 1
        conn.commit()
    return {"units": len(rows), "chains": n_chains, "links": n_links}


def resolve_entities() -> dict:
    """Stage 3-4 baseline, set-based: frequent normalized mention forms become
    narrator entities with aliases; links get narrator_id via one joined
    UPDATE (row-at-a-time UPDATEs over ~1M links took hours)."""
    with pool.connection() as conn:
        conn.execute("CREATE INDEX IF NOT EXISTS isnad_links_mention "
                     "ON isnad_links (mention_norm)")
        created = conn.execute("""
            WITH freq AS (
                SELECT mention_norm,
                       (array_agg(mention_ar ORDER BY length(mention_ar)))[1] AS raw
                FROM isnad_links GROUP BY mention_norm HAVING count(*) >= %s
            ), new AS (
                SELECT f.* FROM freq f
                WHERE NOT EXISTS (SELECT 1 FROM narrator_aliases a
                                  WHERE a.alias_norm = f.mention_norm)
            ), ins AS (
                INSERT INTO narrators (canonical_ar, canonical_norm)
                SELECT raw, mention_norm FROM new
                RETURNING narrator_id, canonical_norm
            ), alias_ins AS (
                INSERT INTO narrator_aliases (narrator_id, alias_ar, alias_norm, alias_kind)
                SELECT i.narrator_id, n.raw, i.canonical_norm, 'name'
                FROM ins i JOIN new n ON n.mention_norm = i.canonical_norm
                ON CONFLICT (narrator_id, alias_norm, alias_kind) DO NOTHING
                RETURNING 1
            )
            SELECT count(*) AS n FROM ins
        """, (MIN_MENTION_COUNT,)).fetchone()["n"]
        conn.commit()
        conn.execute("""
            UPDATE isnad_links l SET narrator_id = a.narrator_id
            FROM (SELECT DISTINCT ON (alias_norm) alias_norm, narrator_id
                  FROM narrator_aliases ORDER BY alias_norm, narrator_id) a
            WHERE l.narrator_id IS NULL AND l.mention_norm = a.alias_norm
        """)
        conn.commit()
        resolved = conn.execute(
            "SELECT count(*) AS n FROM isnad_links WHERE narrator_id IS NOT NULL"
        ).fetchone()["n"]
    return {"narrators_created": created, "links_resolved": resolved}


def _agtype_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def build_graph(rebuild: bool = False, min_mentions: int = 5,
                min_weight: int = 2) -> dict:
    """Stage 6: project narrators + aggregated NARRATED_FROM edges into AGE.
    Thresholds keep the openCypher graph at NL2CYPHER-scale (the app's own
    graph views read the relational isnad_links directly)."""
    with pool.connection() as conn:
        conn.execute("ANALYZE isnad_links, isnad_chains, narrators")
        conn.execute("LOAD 'age'")
        conn.execute('SET search_path = ag_catalog, "$user", public')
        exists = conn.execute(
            "SELECT count(*) AS n FROM ag_catalog.ag_graph WHERE name=%s",
            (GRAPH,)).fetchone()["n"]
        if exists and rebuild:
            conn.execute("SELECT drop_graph(%s, true)", (GRAPH,))
            exists = 0
        if not exists:
            conn.execute("SELECT create_graph(%s)", (GRAPH,))
        conn.commit()

        narrators = conn.execute("""
            SELECT n.narrator_id, n.canonical_ar, count(*) AS mentions
            FROM narrators n JOIN isnad_links l USING (narrator_id)
            GROUP BY 1, 2 HAVING count(*) >= %s
        """, (min_mentions,)).fetchall()
        kept = {r["narrator_id"] for r in narrators}

        # student(pos i) -[NARRATED_FROM]-> teacher(pos i+1), aggregated
        edges = conn.execute("""
            SELECT a.narrator_id AS student, b.narrator_id AS teacher, count(*) AS n
            FROM isnad_links a
            JOIN isnad_links b ON b.chain_id = a.chain_id AND b.pos = a.pos + 1
            WHERE a.narrator_id IS NOT NULL AND b.narrator_id IS NOT NULL
              AND a.narrator_id != b.narrator_id
            GROUP BY 1, 2 HAVING count(*) >= %s
        """, (min_weight,)).fetchall()
        edges = [e for e in edges if e["student"] in kept and e["teacher"] in kept]

        # fresh graph -> plain CREATE (no MERGE label scan per node);
        # pipelined to avoid one round-trip per node on remote DBs
        for i in range(0, len(narrators), 2000):
            with conn.pipeline():
                for row in narrators[i:i + 2000]:
                    name = _agtype_str(row["canonical_ar"])
                    conn.execute(
                        f"SELECT * FROM cypher('{GRAPH}', $$ "
                        f"CREATE (:Narrator {{narrator_id: {row['narrator_id']}, "
                        f"name: '{name}', mentions: {row['mentions']}}}) $$) AS (v agtype)")
            conn.commit()

        # expression index so the per-edge MATCH is a lookup, not a label scan
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS narrator_prop_id_idx
            ON {GRAPH}."Narrator"
            ((ag_catalog.agtype_access_operator(properties, '"narrator_id"'::agtype)))
        """)
        conn.commit()

        # pipeline mode: one network round-trip per batch (critical when the
        # DB is remote, e.g. rebuilding the Railway graph over the TCP proxy)
        done = 0
        for i in range(0, len(edges), 2000):
            with conn.pipeline():
                for row in edges[i:i + 2000]:
                    conn.execute(
                        f"SELECT * FROM cypher('{GRAPH}', $$ "
                        f"MATCH (s:Narrator {{narrator_id: {row['student']}}}), "
                        f"(t:Narrator {{narrator_id: {row['teacher']}}}) "
                        f"CREATE (s)-[:NARRATED_FROM {{count: {row['n']}}}]->(t) "
                        f"$$) AS (v agtype)")
            conn.commit()
            done += len(edges[i:i + 2000])
            if done % 20000 < 2000:
                print(f"  graph edges: {done}/{len(edges)}", flush=True)
    return {"nodes": len(narrators), "edges": len(edges)}


def matn_editions() -> list[dict]:
    with pool.connection() as conn:
        return conn.execute("""
            SELECT e.edition_id, w.title_ar,
                   (SELECT count(*) FROM passages p
                    WHERE p.edition_id=e.edition_id AND p.kind='unit') AS units
            FROM editions e JOIN works w USING (work_id)
            WHERE w.kind='matn'
            ORDER BY units
        """).fetchall()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edition", type=int, default=1)
    ap.add_argument("--all-matn", action="store_true",
                    help="extract chains for every matn edition, then resolve once")
    ap.add_argument("--rebuild-graph", action="store_true")
    ap.add_argument("--skip-extract", action="store_true")
    ap.add_argument("--skip-graph", action="store_true")
    ap.add_argument("--resolve-only", action="store_true",
                    help="run entity resolution on already-extracted links")
    args = ap.parse_args()

    pool.open()
    stats = {}
    if args.resolve_only:
        stats["resolve"] = resolve_entities()
        print("resolve:", json.dumps(stats["resolve"]), flush=True)
        if not args.skip_graph:
            stats["graph"] = build_graph(rebuild=args.rebuild_graph)
            print("graph:", json.dumps(stats["graph"]), flush=True)
        pool.close()
        return
    if not args.skip_extract:
        if args.all_matn:
            for ed in matn_editions():
                if not ed["units"]:
                    continue
                s = extract_chains(ed["edition_id"])
                print(f"extract edition {ed['edition_id']} ({ed['title_ar']}):",
                      json.dumps(s), flush=True)
        else:
            stats["extract"] = extract_chains(args.edition)
            print("extract:", json.dumps(stats["extract"]), flush=True)
        stats["resolve"] = resolve_entities()
        print("resolve:", json.dumps(stats["resolve"]), flush=True)
    if not args.skip_graph:
        stats["graph"] = build_graph(rebuild=args.rebuild_graph)
        print("graph:", json.dumps(stats["graph"]), flush=True)
    pool.close()


if __name__ == "__main__":
    main()
