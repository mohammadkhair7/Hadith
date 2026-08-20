"""Neural tashkeel (diacritization) model — §12.9-B.

Character-level classification: for every Arabic letter predict its diacritic
class (fatha/damma/kasra/sukun, tanwin forms, ± shadda, none). BiLSTM encoder
trained from scratch on vocalized corpus windows.

CLI (GPU venv, run from AdvancedHadith/):
    Arabic-lib\\.venv-gpu\\Scripts\\python -m arabiclib.neural.tashkeel train --epochs 3
    Arabic-lib\\.venv-gpu\\Scripts\\python -m arabiclib.neural.tashkeel eval
    Arabic-lib\\.venv-gpu\\Scripts\\python -m arabiclib.neural.tashkeel infer --text "قال رسول الله"
    Arabic-lib\\.venv-gpu\\Scripts\\python -m arabiclib.neural.tashkeel infer --file in.txt
"""
import argparse
import re
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn

from .common import (DATA_DIR, MODELS_DIR, PAD, Vocab, device, load_ckpt,
                     pad_batch, read_jsonl, save_ckpt, seed_all)

CKPT = MODELS_DIR / "tashkeel_bilstm.pt"
DATA = DATA_DIR / "tashkeel.jsonl"

# diacritic classes: vowel (8) x shadda (2) = 16
_VOWELS = ["", "\u064E", "\u064F", "\u0650", "\u0652",  # none fatha damma kasra sukun
           "\u064B", "\u064C", "\u064D"]                 # fathatan dammatan kasratan
_VOWEL_ID = {v: i for i, v in enumerate(_VOWELS)}
SHADDA = "\u0651"
N_CLASSES = len(_VOWELS) * 2
_MARK = re.compile(r"[\u064B-\u0652\u0670]")
_ARABIC_LETTER = re.compile(r"[\u0621-\u064A]")


def split_marks(vocalized: str) -> tuple[str, list[int]]:
    """Return (bare text, per-char class labels). Non-letter chars get class 0."""
    base_chars: list[str] = []
    labels: list[int] = []
    i = 0
    while i < len(vocalized):
        ch = vocalized[i]
        if _MARK.match(ch):
            i += 1
            continue
        marks = ""
        j = i + 1
        while j < len(vocalized) and _MARK.match(vocalized[j]):
            marks += vocalized[j]
            j += 1
        shadda = 1 if SHADDA in marks else 0
        vowel = next((m for m in marks if m in _VOWEL_ID and m), "")
        base_chars.append(ch)
        labels.append(_VOWEL_ID.get(vowel, 0) + len(_VOWELS) * shadda)
        i = j if j > i + 1 else i + 1
    return "".join(base_chars), labels


def apply_marks(text: str, labels: list[int]) -> str:
    out = []
    for ch, lab in zip(text, labels):
        out.append(ch)
        if _ARABIC_LETTER.match(ch) and lab:
            if lab >= len(_VOWELS):
                out.append(SHADDA)
                lab -= len(_VOWELS)
            if lab:
                out.append(_VOWELS[lab])
    return "".join(out)


class TashkeelNet(nn.Module):
    def __init__(self, n_chars: int, emb: int = 128, hid: int = 384):
        super().__init__()
        self.emb = nn.Embedding(n_chars, emb, padding_idx=PAD)
        self.lstm = nn.LSTM(emb, hid, num_layers=2, bidirectional=True,
                            batch_first=True, dropout=0.2)
        self.head = nn.Linear(hid * 2, N_CLASSES)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h, _ = self.lstm(self.emb(x))
        return self.head(h)


def _prepare(rows: list[dict]) -> list[tuple[str, list[int]]]:
    out = []
    for r in rows:
        text, labels = split_marks(r["text"])
        if len(text) >= 20:
            out.append((text, labels))
    return out


def _batches(data, vocab: Vocab, batch_size: int, shuffle: bool):
    import random
    idx = list(range(len(data)))
    if shuffle:
        random.shuffle(idx)
    for i in range(0, len(idx), batch_size):
        chunk = [data[j] for j in idx[i:i + batch_size]]
        x = pad_batch([vocab.encode(t) for t, _ in chunk])
        y = pad_batch([lab for _, lab in chunk], pad=-100)
        # only Arabic letters contribute to the loss
        for bi, (t, _) in enumerate(chunk):
            for ci, ch in enumerate(t):
                if not _ARABIC_LETTER.match(ch):
                    y[bi, ci] = -100
        yield x, y


@torch.no_grad()
def _evaluate(model, data, vocab, dev) -> dict:
    model.eval()
    total = errs = marked = marked_errs = 0
    for x, y in _batches(data, vocab, 128, shuffle=False):
        pred = model(x.to(dev)).argmax(-1).cpu()
        mask = y != -100
        total += int(mask.sum())
        errs += int((pred[mask] != y[mask]).sum())
        mmask = mask & (y > 0)
        marked += int(mmask.sum())
        marked_errs += int((pred[mmask] != y[mmask]).sum())
    return {"der_all": errs / max(total, 1),
            "der_marked": marked_errs / max(marked, 1),
            "chars": total}


def train(args) -> None:
    seed_all()
    dev = device()
    rows = read_jsonl(DATA, limit=args.limit)
    data = {s: [] for s in ("train", "dev", "test")}
    for r in rows:
        data[r["split"]].append(r)
    tr, dv = _prepare(data["train"]), _prepare(data["dev"])
    vocab = Vocab.build((t for t, _ in tr), max_size=400)
    model = TashkeelNet(len(vocab)).to(dev)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"device={dev} train={len(tr)} dev={len(dv)} vocab={len(vocab)} params={n_params:,}")

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    lossf = nn.CrossEntropyLoss(ignore_index=-100)
    best = 1e9
    for ep in range(1, args.epochs + 1):
        model.train()
        t0, tot_loss, nb = time.time(), 0.0, 0
        for x, y in _batches(tr, vocab, args.batch_size, shuffle=True):
            opt.zero_grad()
            out = model(x.to(dev))
            loss = lossf(out.reshape(-1, N_CLASSES), y.to(dev).reshape(-1))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 2.0)
            opt.step()
            tot_loss += float(loss)
            nb += 1
            if nb % 200 == 0:
                print(f"  ep{ep} batch {nb} loss {tot_loss/nb:.4f}", flush=True)
        m = _evaluate(model, dv, vocab, dev)
        print(f"epoch {ep}: loss {tot_loss/max(nb,1):.4f} "
              f"dev DER(all) {m['der_all']:.4f} DER(marked) {m['der_marked']:.4f} "
              f"({time.time()-t0:.0f}s)", flush=True)
        if m["der_all"] < best:
            best = m["der_all"]
            save_ckpt(CKPT, model, {"vocab": vocab.stoi, "metrics": m,
                                    "task": "tashkeel", "version": "0.1"})
            print(f"  saved -> {CKPT}")


def _load_model() -> tuple[TashkeelNet, Vocab, dict]:
    ck = load_ckpt(CKPT)
    vocab = Vocab(ck["vocab"])
    model = TashkeelNet(len(vocab))
    model.load_state_dict(ck["state_dict"])
    model.eval()
    return model, vocab, ck.get("metrics", {})


def evaluate(args) -> None:
    dev = device()
    rows = [r for r in read_jsonl(DATA, limit=args.limit) if r["split"] == "test"]
    data = _prepare(rows)
    model, vocab, _ = _load_model()
    model.to(dev)
    m = _evaluate(model, data, vocab, dev)
    print(f"test windows={len(data)} chars={m['chars']}")
    print(f"DER (all letters):    {m['der_all']:.4f}")
    print(f"DER (marked letters): {m['der_marked']:.4f}")


@torch.no_grad()
def infer(args) -> None:
    text = args.text or Path(args.file).read_text(encoding="utf-8")
    model, vocab, _ = _load_model()
    dev = device()
    model.to(dev)
    out_lines = []
    for line in text.splitlines() or [text]:
        bare = _MARK.sub("", line)
        if not bare.strip():
            out_lines.append(line)
            continue
        x = pad_batch([vocab.encode(bare)]).to(dev)
        labels = model(x).argmax(-1)[0][:len(bare)].tolist()
        out_lines.append(apply_marks(bare, labels))
    sys.stdout.buffer.write(("\n".join(out_lines) + "\n").encode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Neural tashkeel model (§12.9-B)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    tp = sub.add_parser("train")
    tp.add_argument("--epochs", type=int, default=3)
    tp.add_argument("--batch-size", type=int, default=64)
    tp.add_argument("--lr", type=float, default=2e-3)
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
