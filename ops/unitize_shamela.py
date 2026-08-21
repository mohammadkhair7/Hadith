"""Unitize shamela page-archive editions into hadith units + crosswalk to aljam3.

Plan reference: docs/ALSHAMELA_BOOK_SOURCES.md §5A (steps 12-14).

- shamela_units: one row per hadith. A unit starts at a hadith-number line
  («123 - حدثنا …», Arabic or Latin digits) and ends at the next unit start or
  heading line (heading grammar reused from build_shamela_toc). Units may span
  pages. hadith_seq (1..N per book) is the unique per-book number; the global
  identifier is 'S<bkid>:<hadith_seq>'. sanad_end_off comes from the neural
  indexing 'structure' spans when the start page has them.
- unit_map: aljam3 unit passage -> shamela unit, matched by printed hadith
  number + normalized-token overlap. Permanent traceability record.

Deterministic: rebuilt per environment (never copied by serial id).

    python ops\\unitize_shamela.py --edition 123 [--rebuild]
    python ops\\unitize_shamela.py --all [--rebuild]
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import psycopg

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "etl"))
from build_shamela_toc import classify  # noqa: E402
from normalize import normalize_arabic  # noqa: E402

# «272 - (168) حدثنا …»: leading number, optional parenthesized global number
# (Muslim-style two-number convention: per-kitab counter + عبد الباقي global).
HNUM = re.compile(
    r"^\s*([\d\u0660-\u0669]+)\s*[-–—]\s*(?:\(\s*([\d\u0660-\u0669]+)\s*\))?")
# «(1098) وحدثناه …»: repeated-chain unit carrying only the global number.
# Gated on proximity to the previous global number to reject footnote markers.
HNUM_PAREN = re.compile(r"^\s*\(\s*([\d\u0660-\u0669]+)\s*\)\s*\S")
_EAST = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

DDL = """
CREATE TABLE IF NOT EXISTS shamela_units (
    unit_id          bigserial PRIMARY KEY,
    edition_id       int NOT NULL REFERENCES editions ON DELETE CASCADE,
    bkid             int NOT NULL,
    hadith_seq       int NOT NULL,
    hadith_num       text,
    start_passage_id bigint NOT NULL REFERENCES passages ON DELETE CASCADE,
    end_passage_id   bigint NOT NULL REFERENCES passages ON DELETE CASCADE,
    start_off        int NOT NULL,
    end_off          int NOT NULL,
    sanad_end_off    int,
    meta             jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (edition_id, hadith_seq)
);
CREATE INDEX IF NOT EXISTS shamela_units_num  ON shamela_units (edition_id, hadith_num);
CREATE INDEX IF NOT EXISTS shamela_units_page ON shamela_units (start_passage_id);
CREATE TABLE IF NOT EXISTS unit_map (
    aljam3_passage_id bigint PRIMARY KEY REFERENCES passages ON DELETE CASCADE,
    unit_id           bigint REFERENCES shamela_units ON DELETE SET NULL,
    bkid              int NOT NULL,
    hadith_seq        int NOT NULL,
    hadith_num        text,
    method            text NOT NULL,
    confidence        real,
    matched_at        timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS unit_map_unit ON unit_map (unit_id);
"""


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("LOCAL_PG_URL")
    if url:
        return url
    root = Path(__file__).resolve().parents[1]
    for env in (root / ".env.local",):
        if env.exists():
            for line in env.read_text(encoding="utf-8-sig").splitlines():
                if line.startswith(("DATABASE_URL=", "LOCAL_PG_URL=")):
                    return line.split("=", 1)[1].strip().strip('"')
    sys.exit("no DATABASE_URL / LOCAL_PG_URL found")


def _num(tok: str) -> str:
    return tok.translate(_EAST).lstrip("0") or "0"


def segment(pages: list[tuple[int, str]]) -> list[dict]:
    """pages: [(passage_id, text_raw)] in seq order -> list of unit dicts."""
    units: list[dict] = []
    open_u: dict | None = None
    last_global: int | None = None

    def close(pid: int, off: int) -> None:
        nonlocal open_u
        if open_u is not None:
            open_u["end_pid"], open_u["end_off"] = pid, off
            units.append(open_u)
            open_u = None

    for pid, raw in pages:
        raw = raw or ""
        pos = 0
        for line in raw.split("\n"):
            start, pos = pos, pos + len(line) + 1
            s = line.strip()
            if not s:
                continue
            m = HNUM.match(line)
            if m:
                close(pid, start)
                num = _num(m.group(2)) if m.group(2) else _num(m.group(1))
                meta = {"local_num": _num(m.group(1))} if m.group(2) else {}
                open_u = {"start_pid": pid, "start_off": start,
                          "num": num, "meta": meta}
                last_global = int(num)
                continue
            mp = HNUM_PAREN.match(line)
            if mp:
                num_i = int(_num(mp.group(1)))
                # repeated-chain start: global number stays close to the
                # previous one; distant small numbers are footnote markers
                if last_global is not None and abs(num_i - last_global) <= 20:
                    close(pid, start)
                    open_u = {"start_pid": pid, "start_off": start,
                              "num": str(num_i), "meta": {"repeat": True}}
                    last_global = num_i
                    continue
            if open_u is not None and classify(s) is not None:
                close(pid, start)
    if pages:
        last_pid, last_raw = pages[-1]
        close(last_pid, len(last_raw or ""))
    for i, u in enumerate(units, 1):
        u["seq"] = i
    return units


def fill_sanad_end(conn, edition_id: int) -> int:
    """Take the first MATN span after the unit start (with an ISNAD span in
    between) from the neural structure annotations of the start page."""
    rows = conn.execute("""
        SELECT u.unit_id, u.start_off,
               CASE WHEN u.start_passage_id = u.end_passage_id
                    THEN u.end_off ELSE NULL END AS lim,
               a.payload->'spans' AS spans
        FROM shamela_units u
        JOIN passage_annotations a ON a.passage_id = u.start_passage_id
             AND a.layer = 'structure' AND a.engine = 'neural-indexing'
        WHERE u.edition_id = %s AND u.sanad_end_off IS NULL
    """, (edition_id,)).fetchall()
    updates = []
    for unit_id, start_off, lim, spans in rows:
        isnad_seen = False
        for s, e, label in spans or []:
            if e <= start_off or (lim is not None and s >= lim):
                continue
            if label == "ISNAD":
                isnad_seen = True
            elif label == "MATN" and isnad_seen and s > start_off:
                updates.append((s, unit_id))
                break
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE shamela_units SET sanad_end_off=%s WHERE unit_id=%s", updates)
    return len(updates)


def crosswalk(conn, edition_id: int, bkid: int) -> dict | None:
    """Match aljam3 units of the same work by printed hadith number + token
    overlap; write unit_map. Returns report dict or None (no aljam3 side)."""
    row = conn.execute("""
        SELECT e2.edition_id FROM editions e1
        JOIN editions e2 ON e2.work_id = e1.work_id AND e2.source = 'sunna'
        WHERE e1.edition_id = %s
    """, (edition_id,)).fetchone()
    if not row:
        return None
    sunna_ed = row[0]
    alj = conn.execute("""
        SELECT passage_id, hadith_num, text_norm FROM passages
        WHERE edition_id = %s AND kind = 'unit'
          AND hadith_num ~ '^[0-9]+$'
    """, (sunna_ed,)).fetchall()
    if not alj:
        return {"sunna_edition": sunna_ed, "aljam3_units": 0}

    # shamela unit start-page slices, normalized token sets
    su = conn.execute("""
        SELECT u.unit_id, u.hadith_seq, u.hadith_num, u.start_off,
               CASE WHEN u.start_passage_id = u.end_passage_id
                    THEN u.end_off ELSE NULL END AS lim,
               p.text_raw
        FROM shamela_units u JOIN passages p ON p.passage_id = u.start_passage_id
        WHERE u.edition_id = %s AND u.hadith_num IS NOT NULL
    """, (edition_id,)).fetchall()
    by_num: dict[str, list] = {}
    for unit_id, seq, num, off, lim, raw in su:
        sl = (raw or "")[off:lim if lim is not None else off + 800][:800]
        toks = set(normalize_arabic(sl).split())
        by_num.setdefault(num, []).append((unit_id, seq, num, toks))

    matched = high = 0
    confs = []
    rows_out = []
    for pid, hnum, tnorm in alj:
        cands = by_num.get(_num(hnum))
        if not cands:
            continue
        # aljam3 text_norm often opens with the باب heading; compare from the
        # hadith number onward, and drop digits / single-letter tokens (ح …)
        toks_all = (tnorm or "").split()
        num = _num(hnum)
        for i, t in enumerate(toks_all):
            if t == num or t == hnum:
                toks_all = toks_all[i + 1:]
                break
        atoks = [t for t in toks_all if not t.isdigit() and len(t) > 1][:25]
        best = None
        for unit_id, seq, num, toks in cands:
            conf = (sum(1 for t in atoks if t in toks) / len(atoks)) if atoks else 0.0
            if best is None or conf > best[3]:
                best = (unit_id, seq, num, conf)
        matched += 1
        confs.append(best[3])
        if best[3] >= 0.6:
            high += 1
        rows_out.append((pid, best[0], bkid, best[1], best[2],
                         "hnum+overlap", round(best[3], 4)))
    with conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO unit_map (aljam3_passage_id, unit_id, bkid, hadith_seq,
                                  hadith_num, method, confidence)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (aljam3_passage_id) DO UPDATE
            SET unit_id=EXCLUDED.unit_id, bkid=EXCLUDED.bkid,
                hadith_seq=EXCLUDED.hadith_seq, hadith_num=EXCLUDED.hadith_num,
                method=EXCLUDED.method, confidence=EXCLUDED.confidence,
                matched_at=now()
        """, rows_out)
    return {
        "sunna_edition": sunna_ed, "aljam3_units": len(alj), "matched": matched,
        "coverage": round(matched / len(alj), 4) if alj else None,
        "mean_conf": round(sum(confs) / len(confs), 4) if confs else None,
        "high_conf": high,
        "high_share": round(high / matched, 4) if matched else None,
    }


def run_edition(conn, edition_id: int, rebuild: bool) -> None:
    ed = conn.execute("""
        SELECT source_book_id, title_ar FROM editions
        WHERE edition_id=%s AND source='shamela'
    """, (edition_id,)).fetchone()
    if not ed:
        sys.exit(f"edition {edition_id} is not a shamela edition")
    bkid, title = ed
    existing = conn.execute(
        "SELECT count(*) FROM shamela_units WHERE edition_id=%s", (edition_id,)
    ).fetchone()[0]
    if existing and not rebuild:
        print(f"edition {edition_id} ({title[:30]}): {existing} units exist, skip")
        return
    if existing:
        conn.execute("DELETE FROM shamela_units WHERE edition_id=%s", (edition_id,))

    pages = conn.execute("""
        SELECT passage_id, text_raw FROM passages
        WHERE edition_id=%s ORDER BY seq
    """, (edition_id,)).fetchall()
    units = segment(pages)
    with conn.cursor() as cur:
        with cur.copy("""
            COPY shamela_units (edition_id, bkid, hadith_seq, hadith_num,
                start_passage_id, end_passage_id, start_off, end_off, meta)
            FROM STDIN
        """) as cp:
            for u in units:
                cp.write_row((edition_id, bkid, u["seq"], u["num"],
                              u["start_pid"], u["end_pid"],
                              u["start_off"], u["end_off"],
                              json.dumps(u.get("meta") or {})))
    n_sanad = fill_sanad_end(conn, edition_id)
    nums = [u["num"] for u in units]
    hno = conn.execute("""
        SELECT count(*) FILTER (WHERE p.meta->>'hno' IS NOT NULL),
               count(*) FILTER (WHERE p.meta->>'hno' = u.hadith_num)
        FROM shamela_units u JOIN passages p ON p.passage_id = u.start_passage_id
        WHERE u.edition_id = %s
    """, (edition_id,)).fetchone()
    report = {"edition": edition_id, "bkid": bkid, "pages": len(pages),
              "units": len(units), "distinct_nums": len(set(nums)),
              "hno_pages": hno[0], "hno_agree": hno[1],
              "sanad_end_filled": n_sanad}
    xw = crosswalk(conn, edition_id, bkid)
    if xw:
        report["crosswalk"] = xw
    conn.commit()
    print(f"== {title[:40]} (edition {edition_id}, bkid {bkid})")
    print(json.dumps(report, ensure_ascii=False, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edition", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--fill-sanad", action="store_true",
                    help="only fill sanad_end_off from new structure annotations")
    args = ap.parse_args()
    if not args.edition and not args.all:
        sys.exit("need --edition N or --all")
    with psycopg.connect(_db_url()) as conn:
        conn.execute(DDL)
        conn.commit()
        if args.fill_sanad:
            eds = ([(args.edition,)] if args.edition else conn.execute(
                "SELECT DISTINCT edition_id FROM shamela_units ORDER BY 1").fetchall())
            for (eid,) in eds:
                n = fill_sanad_end(conn, eid)
                conn.commit()
                print(f"edition {eid}: sanad_end filled for {n} units")
            print("done")
            return
        if args.edition:
            run_edition(conn, args.edition, args.rebuild)
        else:
            eds = conn.execute("""
                SELECT edition_id FROM editions WHERE source='shamela'
                ORDER BY passage_count, edition_id
            """).fetchall()
            for (eid,) in eds:
                run_edition(conn, eid, args.rebuild)
    print("done")


if __name__ == "__main__":
    main()
