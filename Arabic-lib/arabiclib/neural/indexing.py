"""Neural page-indexing model — §12.9-A: raw hadith text -> display-ready
structure. Word-level labeling with classes HNUM (hadith number), ISNAD,
MATN, HEADING; ground truth auto-generated from the corpus (units with the
rule-extractor's sanad/matn boundary + TOC headings) — "the corpus is the
labeler".

CLI (GPU venv, run from AdvancedHadith/):
    Arabic-lib\\.venv-gpu\\Scripts\\python -m arabiclib.neural.indexing train --epochs 3
    Arabic-lib\\.venv-gpu\\Scripts\\python -m arabiclib.neural.indexing eval
    Arabic-lib\\.venv-gpu\\Scripts\\python -m arabiclib.neural.indexing infer --text "حدثنا ..."
"""
import argparse
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
                                    "metrics": m, "task": "indexing", "version": "0.1"})
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
    args = ap.parse_args()
    {"train": train, "eval": evaluate, "infer": infer}[args.cmd](args)


if __name__ == "__main__":
    main()
