"""Dataset builders for the §12.9 neural models. Runs with the BACKEND venv
(needs Postgres + camel-tools); training/inference then run in the GPU venv
from the JSONL files this script writes to Arabic-lib/training/data/.

    .venv\\Scripts\\python Arabic-lib\\training\\build_datasets.py --task all
"""
import argparse
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "backend"))
sys.path.insert(0, str(_ROOT / "Arabic-lib"))

from app.db import pool  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"
_D = re.compile(r"[\u064B-\u0652]")
_AR = re.compile(r"[\u0621-\u064A]")
_JUNK = re.compile(r"AddHistory\([^)]*\)[^;]*;?|\[\d+/\d+\]")


def _split_of(key: str) -> str:
    import hashlib
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % 100
    return "train" if h < 90 else ("dev" if h < 95 else "test")


def _write(name: str, rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{name}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"{path.name}: {len(rows)} samples {dict(Counter(r['split'] for r in rows))}")


def _windows(text: str, max_chars: int = 380) -> list[str]:
    words = text.split()
    out, cur, ln = [], [], 0
    for w in words:
        if ln + len(w) + 1 > max_chars and cur:
            out.append(" ".join(cur))
            cur, ln = [], 0
        cur.append(w)
        ln += len(w) + 1
    if cur:
        out.append(" ".join(cur))
    return out


def build_tashkeel(target_windows: int) -> None:
    """Vocalized windows from the densest shamela editions (density >= 0.6)."""
    pool.open()
    rows_out: list[dict] = []
    with pool.connection() as conn:
        # the replaced Bukhari (91, Dar al-Sha'b, fully vocalized) leads so its
        # clean tashkeel is guaranteed a large share of the corpus
        eds = conn.execute("""
            SELECT edition_id FROM editions WHERE source='shamela'
            ORDER BY (edition_id = 91) DESC, edition_id
        """).fetchall()
        for e in eds:
            if len(rows_out) >= target_windows:
                break
            batch = conn.execute("""
                SELECT text_raw FROM passages
                WHERE edition_id=%s AND length(text_raw) > 200
                ORDER BY random() LIMIT 3000
            """, (e["edition_id"],)).fetchall()
            for r in batch:
                text = _JUNK.sub(" ", r["text_raw"])
                for win in _windows(text):
                    letters = len(_AR.findall(win))
                    if letters < 60:
                        continue
                    if len(_D.findall(win)) / letters < 0.6:
                        continue
                    rows_out.append({"text": win, "split": _split_of(win)})
                    if len(rows_out) >= target_windows:
                        break
                if len(rows_out) >= target_windows:
                    break
    _write("tashkeel", rows_out)


def build_pos(n_passages: int) -> None:
    """Silver POS tags from the CAMeL morphology engine (ensemble member)."""
    from arabiclib.engines.camel_morphology import CamelMorphologyEngine
    from arabiclib.schema import whitespace_tokenize

    eng = CamelMorphologyEngine()
    if not eng.available():
        sys.exit(f"camel engine unavailable: {eng.unavailable_reason}")
    pool.open()
    with pool.connection() as conn:
        rows = conn.execute("""
            SELECT passage_id, text_raw FROM passages
            WHERE kind='unit' AND length(text_raw) BETWEEN 200 AND 2500
            ORDER BY random() LIMIT %s
        """, (n_passages,)).fetchall()
    out: list[dict] = []
    B = 32
    for i in range(0, len(rows), B):
        batch = rows[i:i + B]
        texts = [_JUNK.sub(" ", r["text_raw"]) for r in batch]
        anns = eng.annotate_batch(texts)
        for r, text, ann in zip(batch, texts, anns):
            toks = [t.text for t in whitespace_tokenize(text)]
            tags = {p["token_idx"]: p["tag"] for p in ann["pos"]}
            tag_list = [tags.get(j, "x") or "x" for j in range(len(toks))]
            if len(toks) >= 8:
                out.append({"tokens": toks, "tags": tag_list,
                            "split": _split_of(str(r["passage_id"]))})
        if (i // B) % 10 == 0:
            print(f"  pos: {min(i + B, len(rows))}/{len(rows)}", flush=True)
    _write("pos", out)


def build_indexing(n_units: int, n_headings: int) -> None:
    """Units with the rule-extractor's raw matn boundary + TOC headings."""
    pool.open()
    out: list[dict] = []
    with pool.connection() as conn:
        rows = conn.execute("""
            SELECT p.passage_id, p.text_raw, c.sanad_end_raw
            FROM isnad_chains c JOIN passages p USING (passage_id)
            WHERE c.sanad_end_raw IS NOT NULL AND c.sanad_end_raw > 30
              AND c.ord = 0 AND c.confidence >= 0.9
              AND length(p.text_raw) BETWEEN 150 AND 4000
            ORDER BY random() LIMIT %s
        """, (n_units,)).fetchall()
        for r in rows:
            out.append({"text": r["text_raw"], "sanad_end": r["sanad_end_raw"],
                        "split": _split_of(str(r["passage_id"]))})
        heads = conn.execute("""
            SELECT toc_node_id, title FROM toc_nodes
            WHERE length(title) BETWEEN 15 AND 200
            ORDER BY random() LIMIT %s
        """, (n_headings,)).fetchall()
        for h in heads:
            out.append({"text": h["title"], "kind": "heading",
                        "split": _split_of(f"h{h['toc_node_id']}")})
    _write("indexing", out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="all",
                    choices=["all", "tashkeel", "pos", "indexing"])
    ap.add_argument("--tashkeel-windows", type=int, default=70000)
    ap.add_argument("--pos-passages", type=int, default=4000)
    ap.add_argument("--indexing-units", type=int, default=40000)
    ap.add_argument("--indexing-headings", type=int, default=8000)
    args = ap.parse_args()
    if args.task in ("all", "tashkeel"):
        build_tashkeel(args.tashkeel_windows)
    if args.task in ("all", "indexing"):
        build_indexing(args.indexing_units, args.indexing_headings)
    if args.task in ("all", "pos"):
        build_pos(args.pos_passages)


if __name__ == "__main__":
    main()
