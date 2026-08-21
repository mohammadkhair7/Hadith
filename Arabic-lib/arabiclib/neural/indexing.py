"""Neural page-indexing model — §12.9-A: raw hadith text -> display-ready
structure. Word-level labeling with classes HNUM (hadith number), ISNAD,
MATN, HEADING; ground truth auto-generated from the corpus (units with the
rule-extractor's sanad/matn boundary + TOC headings) — "the corpus is the
labeler". Training data comes from الجامع units (measured boundaries);
`annotate` deploys the model on الشاملة pages, storing raw-offset structure
spans in passage_annotations (layer='structure', engine='neural-indexing').

CLI (GPU venv, run from AdvancedHadith/):
    Arabic-lib\\.venv-gpu\\Scripts\\python -m arabiclib.neural.indexing train --epochs 3
    Arabic-lib\\.venv-gpu\\Scripts\\python -m arabiclib.neural.indexing eval
    Arabic-lib\\.venv-gpu\\Scripts\\python -m arabiclib.neural.indexing infer --text "حدثنا ..."
    Arabic-lib\\.venv-gpu\\Scripts\\python -m arabiclib.neural.indexing annotate --all-shamela
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn

from .common import (DATA_DIR, MODELS_DIR, Vocab, WordTagger, device,
                     encode_words, load_ckpt, pad_batch, pad_words,
                     read_jsonl, save_ckpt, seed_all)

CKPT = MODELS_DIR / "indexing_wordtagger.pt"
DATA = DATA_DIR / "indexing.jsonl"
TAGS = ["HNUM", "ISNAD", "MATN", "HEADING"]
MAX_WORDS = 220
_NUM = re.compile(r"^[\d\u0660-\u0669]+[-–.)\]]*$")


def _words_with_offsets(text: str) -> list[tuple[str, int]]:
    return [(m.group(), m.start()) for m in re.finditer(r"\S+", text)]


def _label_unit(text: str, sanad_end: int) -> tuple[list[str], list[str]]:
    words, tags = [], []
    for w, off in _words_with_offsets(text)[:MAX_WORDS]:
        words.append(w)
        if _NUM.match(w) and not tags:
            tags.append("HNUM")
        elif off < sanad_end:
            tags.append("ISNAD")
        else:
            tags.append("MATN")
    return words, tags


def _prepare(rows: list[dict]) -> list[tuple[list[str], list[str]]]:
    out = []
    for r in rows:
        if r.get("kind") == "heading":
            words = [w for w, _ in _words_with_offsets(r["text"])[:MAX_WORDS]]
            if len(words) >= 2:
                out.append((words, ["HEADING"] * len(words)))
        elif r.get("sanad_end", 0) > 0:
            words, tags = _label_unit(r["text"], r["sanad_end"])
            if len(words) >= 6 and "MATN" in tags and "ISNAD" in tags:
                out.append((words, tags))
    return out


def _batches(data, cvocab, tvocab, batch_size, shuffle):
    import random
    idx = list(range(len(data)))
    if shuffle:
        random.shuffle(idx)
    for i in range(0, len(idx), batch_size):
        chunk = [data[j] for j in idx[i:i + batch_size]]
        x = pad_words([encode_words(w, cvocab) for w, _ in chunk])
        y = pad_batch([tvocab.encode(t) for _, t in chunk], pad=-100)
        yield x, y, chunk


@torch.no_grad()
def _evaluate(model, data, cvocab, tvocab, dev) -> dict:
    model.eval()
    total = errs = 0
    boundary_hits = boundary_total = 0
    boundary_word_err = []
    matn_id = tvocab.stoi["MATN"]
    for x, y, chunk in _batches(data, cvocab, tvocab, 64, shuffle=False):
        pred = model(x.to(dev)).argmax(-1).cpu()
        mask = y != -100
        total += int(mask.sum())
        errs += int((pred[mask] != y[mask]).sum())
        for bi, (words, tags) in enumerate(chunk):
            if "ISNAD" not in tags or "MATN" not in tags:
                continue
            gold_b = tags.index("MATN")
            p = pred[bi][:len(words)].tolist()
            pred_b = next((i for i, t in enumerate(p) if t == matn_id), -1)
            boundary_total += 1
            if pred_b >= 0:
                d = abs(pred_b - gold_b)
                boundary_word_err.append(d)
                if d <= 2:
                    boundary_hits += 1
    boundary_word_err.sort()
    return {
        "word_accuracy": 1 - errs / max(total, 1),
        "tokens": total,
        "boundary_within_2_words": boundary_hits / max(boundary_total, 1),
        "boundary_median_word_err": (boundary_word_err[len(boundary_word_err) // 2]
                                     if boundary_word_err else None),
        "boundaries": boundary_total,
    }


def train(args) -> None:
    seed_all()
    dev = device()
    rows = read_jsonl(DATA, limit=args.limit)
    data = {s: [] for s in ("train", "dev", "test")}
    for r in rows:
        data[r["split"]].append(r)
    tr, dv = _prepare(data["train"]), _prepare(data["dev"])
    cvocab = Vocab.build((list("".join(w)) for w, _ in tr), max_size=400)
    tvocab = Vocab(dict({"<pad>": 0, "<unk>": 1},
                        **{t: i + 2 for i, t in enumerate(TAGS)}))
    model = WordTagger(len(cvocab), len(tvocab)).to(dev)
    print(f"device={dev} train={len(tr)} dev={len(dv)} "
          f"params={sum(p.numel() for p in model.parameters()):,}")

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    lossf = nn.CrossEntropyLoss(ignore_index=-100)
    best = 0.0
    for ep in range(1, args.epochs + 1):
        model.train()
        t0, tot, nb = time.time(), 0.0, 0
        for x, y, _ in _batches(tr, cvocab, tvocab, args.batch_size, shuffle=True):
            opt.zero_grad()
            out = model(x.to(dev))
            loss = lossf(out.reshape(-1, out.shape[-1]), y.to(dev).reshape(-1))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 2.0)
            opt.step()
            tot += float(loss)
            nb += 1
            if nb % 200 == 0:
                print(f"  ep{ep} batch {nb} loss {tot/nb:.4f}", flush=True)
        m = _evaluate(model, dv, cvocab, tvocab, dev)
        print(f"epoch {ep}: loss {tot/max(nb,1):.4f} dev acc {m['word_accuracy']:.4f} "
              f"boundary±2w {m['boundary_within_2_words']:.4f} ({time.time()-t0:.0f}s)",
              flush=True)
        if m["word_accuracy"] > best:
            best = m["word_accuracy"]
            save_ckpt(CKPT, model, {"char_vocab": cvocab.stoi, "tag_vocab": tvocab.stoi,
                                    "metrics": m, "task": "indexing", "version": "0.2"})
            print(f"  saved -> {CKPT}")


def _load_model():
    ck = load_ckpt(CKPT)
    cvocab, tvocab = Vocab(ck["char_vocab"]), Vocab(ck["tag_vocab"])
    model = WordTagger(len(cvocab), len(tvocab))
    model.load_state_dict(ck["state_dict"])
    model.eval()
    return model, cvocab, tvocab


def evaluate(args) -> None:
    dev = device()
    rows = [r for r in read_jsonl(DATA, limit=args.limit) if r["split"] == "test"]
    model, cvocab, tvocab = _load_model()
    model.to(dev)
    m = _evaluate(model, _prepare(rows), cvocab, tvocab, dev)
    print(f"test tokens={m['tokens']} boundaries={m['boundaries']}")
    print(f"word accuracy:          {m['word_accuracy']:.4f}")
    print(f"matn boundary ±2 words: {m['boundary_within_2_words']:.4f}")
    print(f"boundary median error:  {m['boundary_median_word_err']} words")


@torch.no_grad()
def infer(args) -> None:
    text = args.text or Path(args.file).read_text(encoding="utf-8")
    model, cvocab, tvocab = _load_model()
    dev = device()
    model.to(dev)
    itos = {v: k for k, v in tvocab.stoi.items()}
    out = []
    for line in text.splitlines() or [text]:
        words = line.split()
        if not words:
            continue
        x = pad_words([encode_words(words[:MAX_WORDS], cvocab)]).to(dev)
        tags = [itos.get(t, "?") for t in model(x).argmax(-1)[0][:len(words)].tolist()]
        # assemble contiguous spans into display segments
        spans: list[tuple[str, list[str]]] = []
        for w, tg in zip(words, tags):
            if spans and spans[-1][0] == tg:
                spans[-1][1].append(w)
            else:
                spans.append((tg, [w]))
        out.append("\n".join(f"[{tg}] {' '.join(ws)}" for tg, ws in spans))
    sys.stdout.buffer.write(("\n\n".join(out) + "\n").encode("utf-8"))


@torch.no_grad()
def page_spans(model, cvocab, tvocab, dev, text: str) -> list[list]:
    """Word-tag a full page and merge contiguous same-label words into
    [start, end, label] spans over RAW text offsets."""
    words = _words_with_offsets(text)
    if len(words) < 12:
        return []
    itos = {v: k for k, v in tvocab.stoi.items()}
    spans: list[list] = []
    for i in range(0, len(words), MAX_WORDS):
        chunk = words[i:i + MAX_WORDS]
        x = pad_words([encode_words([w for w, _ in chunk], cvocab)]).to(dev)
        tags = model(x).argmax(-1)[0][:len(chunk)].tolist()
        for (w, off), t in zip(chunk, tags):
            label = itos.get(t, "?")
            end = off + len(w)
            if spans and spans[-1][2] == label:
                spans[-1][1] = end
            else:
                spans.append([off, end, label])
    return spans


def _usable(spans: list[list]) -> bool:
    """Only store structure when the page really contains hadith anatomy:
    at least one ISNAD span and one MATN span of substance."""
    isnad = sum(e - s for s, e, label in spans if label == "ISNAD")
    matn = sum(e - s for s, e, label in spans if label == "MATN")
    return isnad >= 30 and matn >= 40


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("LOCAL_PG_URL")
    if url:
        return url
    root = Path(__file__).resolve().parents[3]
    for env in (root / ".env.local", root / "backend" / ".env", root / ".env"):
        if not env.exists():
            continue
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith(("DATABASE_URL=", "LOCAL_PG_URL=")):
                return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("no DATABASE_URL / LOCAL_PG_URL found")


def _annotate_edition(conn, edition_id: int, model, cvocab, tvocab, dev,
                      version: str, limit: int | None, resume: bool) -> tuple[int, int]:
    sql = "SELECT p.passage_id, p.text_raw FROM passages p WHERE p.edition_id=%s"
    params: list = [edition_id]
    if resume:
        sql += """ AND NOT EXISTS (
            SELECT 1 FROM passage_annotations a
            WHERE a.passage_id=p.passage_id AND a.layer='structure'
              AND a.engine='neural-indexing' AND a.version=%s)"""
        params.append(version)
    sql += " ORDER BY p.seq"
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    t0 = time.time()
    written = skipped = 0
    for n, (pid, raw) in enumerate(rows, 1):
        spans = page_spans(model, cvocab, tvocab, dev, raw or "")
        if spans and _usable(spans):
            conn.execute("""
                DELETE FROM passage_annotations
                WHERE passage_id=%s AND layer='structure'
                  AND engine='neural-indexing' AND version <> %s
            """, (pid, version))
            conn.execute("""
                INSERT INTO passage_annotations (passage_id, layer, engine, version, payload)
                VALUES (%s, 'structure', 'neural-indexing', %s, %s)
                ON CONFLICT (passage_id, layer, engine, version)
                DO UPDATE SET payload = EXCLUDED.payload, created_at = now()
            """, (pid, version, json.dumps({"spans": spans}, ensure_ascii=False)))
            written += 1
        else:
            skipped += 1
        if n % 500 == 0:
            conn.commit()
            print(f"  {n}/{len(rows)} written={written} skipped={skipped} "
                  f"({time.time()-t0:.0f}s)", flush=True)
    conn.commit()
    print(f"edition {edition_id} done: written={written} skipped={skipped} "
          f"in {time.time()-t0:.0f}s", flush=True)
    return written, skipped


def annotate(args) -> None:
    import psycopg
    ck = load_ckpt(CKPT)
    version = ck.get("version", "0.1")
    model, cvocab, tvocab = _load_model()
    dev = device()
    model.to(dev)
    with psycopg.connect(_db_url()) as conn:
        if not getattr(args, "all_shamela", False):
            if not args.edition:
                sys.exit("need --edition N or --all-shamela")
            _annotate_edition(conn, args.edition, model, cvocab, tvocab, dev,
                              version, args.limit, resume=False)
            return
        eds = conn.execute("""
            SELECT edition_id, passage_count FROM editions
            WHERE source='shamela' ORDER BY passage_count, edition_id
        """).fetchall()
        print(f"bulk: {len(eds)} shamela editions, device={dev}, model=v{version}",
              flush=True)
        tot_w = tot_s = 0
        for i, (eid, count) in enumerate(eds, 1):
            step = f"structure{version}_edition_{eid}"
            done = conn.execute(
                "SELECT 1 FROM etl_state WHERE step=%s AND status='done'", (step,)
            ).fetchone()
            if done:
                print(f"[{i}/{len(eds)}] edition {eid} ({count} pages): ledger done, skip",
                      flush=True)
                continue
            print(f"[{i}/{len(eds)}] edition {eid} ({count} pages)", flush=True)
            w, s = _annotate_edition(conn, eid, model, cvocab, tvocab, dev,
                                     version, None, resume=True)
            tot_w += w
            tot_s += s
            conn.execute("""
                INSERT INTO etl_state (step, status, detail)
                VALUES (%s, 'done', %s)
                ON CONFLICT (step) DO UPDATE SET status='done', detail=EXCLUDED.detail,
                    updated_at=now()
            """, (step, json.dumps({"written": w, "skipped": s})))
            conn.commit()
        print(f"bulk done: written={tot_w} skipped={tot_s}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Neural page-indexing model (§12.9-A)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    tp = sub.add_parser("train")
    tp.add_argument("--epochs", type=int, default=3)
    tp.add_argument("--batch-size", type=int, default=32)
    tp.add_argument("--lr", type=float, default=1e-3)
    tp.add_argument("--limit", type=int, default=None)
    ep = sub.add_parser("eval")
    ep.add_argument("--limit", type=int, default=None)
    ip = sub.add_parser("infer")
    ip.add_argument("--text")
    ip.add_argument("--file")
    an = sub.add_parser("annotate", help="store structure spans for shamela pages")
    an.add_argument("--edition", type=int)
    an.add_argument("--all-shamela", action="store_true", dest="all_shamela")
    an.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    {"train": train, "eval": evaluate, "infer": infer, "annotate": annotate}[args.cmd](args)


if __name__ == "__main__":
    main()
