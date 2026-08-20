"""Neural POS model — §12.9-C: distilled from the Arabic-lib engine ensemble
(CAMeL morphology silver tags over our own corpus).

CLI (GPU venv, run from AdvancedHadith/):
    Arabic-lib\\.venv-gpu\\Scripts\\python -m arabiclib.neural.pos train --epochs 4
    Arabic-lib\\.venv-gpu\\Scripts\\python -m arabiclib.neural.pos eval
    Arabic-lib\\.venv-gpu\\Scripts\\python -m arabiclib.neural.pos infer --text "حدثنا قتيبة بن سعيد"
"""
import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn

from .common import (DATA_DIR, MODELS_DIR, Vocab, WordTagger, device,
                     encode_words, load_ckpt, pad_batch, pad_words,
                     read_jsonl, save_ckpt, seed_all)

CKPT = MODELS_DIR / "pos_wordtagger.pt"
DATA = DATA_DIR / "pos.jsonl"
MAX_WORDS = 120


def _prepare(rows: list[dict]) -> list[tuple[list[str], list[str]]]:
    out = []
    for r in rows:
        toks, tags = r["tokens"], r["tags"]
        if len(toks) != len(tags) or not toks:
            continue
        for i in range(0, len(toks), MAX_WORDS):
            out.append((toks[i:i + MAX_WORDS], tags[i:i + MAX_WORDS]))
    return out


def _batches(data, cvocab: Vocab, tvocab: Vocab, batch_size: int, shuffle: bool):
    import random
    idx = list(range(len(data)))
    if shuffle:
        random.shuffle(idx)
    for i in range(0, len(idx), batch_size):
        chunk = [data[j] for j in idx[i:i + batch_size]]
        x = pad_words([encode_words(w, cvocab) for w, _ in chunk])
        y = pad_batch([tvocab.encode(t) for _, t in chunk], pad=-100)
        yield x, y


@torch.no_grad()
def _evaluate(model, data, cvocab, tvocab, dev) -> dict:
    model.eval()
    total = errs = 0
    confusions: Counter = Counter()
    itos = {v: k for k, v in tvocab.stoi.items()}
    for x, y in _batches(data, cvocab, tvocab, 64, shuffle=False):
        pred = model(x.to(dev)).argmax(-1).cpu()
        mask = y != -100
        total += int(mask.sum())
        wrong = mask & (pred != y)
        errs += int(wrong.sum())
        for g, p in zip(y[wrong].tolist(), pred[wrong].tolist()):
            confusions[(itos.get(g, "?"), itos.get(p, "?"))] += 1
    return {"accuracy": 1 - errs / max(total, 1), "tokens": total,
            "top_confusions": confusions.most_common(8)}


def train(args) -> None:
    seed_all()
    dev = device()
    rows = read_jsonl(DATA, limit=args.limit)
    data = {s: [] for s in ("train", "dev", "test")}
    for r in rows:
        data[r["split"]].append(r)
    tr, dv = _prepare(data["train"]), _prepare(data["dev"])
    cvocab = Vocab.build((list("".join(w)) for w, _ in tr), max_size=400)
    tvocab = Vocab.build((t for _, t in tr), max_size=100)
    model = WordTagger(len(cvocab), len(tvocab)).to(dev)
    print(f"device={dev} train={len(tr)} dev={len(dv)} tags={len(tvocab)-2} "
          f"params={sum(p.numel() for p in model.parameters()):,}")

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    lossf = nn.CrossEntropyLoss(ignore_index=-100)
    best = 0.0
    for ep in range(1, args.epochs + 1):
        model.train()
        t0, tot, nb = time.time(), 0.0, 0
        for x, y in _batches(tr, cvocab, tvocab, args.batch_size, shuffle=True):
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
        print(f"epoch {ep}: loss {tot/max(nb,1):.4f} dev acc {m['accuracy']:.4f} "
              f"({time.time()-t0:.0f}s)", flush=True)
        if m["accuracy"] > best:
            best = m["accuracy"]
            save_ckpt(CKPT, model, {"char_vocab": cvocab.stoi, "tag_vocab": tvocab.stoi,
                                    "metrics": m, "task": "pos", "version": "0.1"})
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
    print(f"test tokens={m['tokens']}")
    print(f"accuracy: {m['accuracy']:.4f}")
    print("top confusions (gold -> pred):")
    for (g, p), n in m["top_confusions"]:
        print(f"  {g} -> {p}: {n}")


@torch.no_grad()
def infer(args) -> None:
    text = args.text or Path(args.file).read_text(encoding="utf-8")
    model, cvocab, tvocab = _load_model()
    dev = device()
    model.to(dev)
    itos = {v: k for k, v in tvocab.stoi.items()}
    out_lines = []
    for line in text.splitlines() or [text]:
        words = line.split()
        if not words:
            out_lines.append("")
            continue
        x = pad_words([encode_words(words[:MAX_WORDS], cvocab)]).to(dev)
        tags = model(x).argmax(-1)[0][:len(words)].tolist()
        out_lines.append(" ".join(f"{w}/{itos.get(t, '?')}" for w, t in zip(words, tags)))
    sys.stdout.buffer.write(("\n".join(out_lines) + "\n").encode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Neural POS model (§12.9-C)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    tp = sub.add_parser("train")
    tp.add_argument("--epochs", type=int, default=4)
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
