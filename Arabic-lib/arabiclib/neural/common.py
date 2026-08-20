"""Shared utilities for the §12.9 neural CLIs (tashkeel / pos / indexing):
vocabulary, padding, checkpoint IO, seeding. Local-only accessories — the
deployed application never imports this package."""
import json
import random
from pathlib import Path

import numpy as np
import torch

PAD, UNK = 0, 1
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
DATA_DIR = Path(__file__).resolve().parents[2] / "training" / "data"


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def seed_all(seed: int = 13) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


class Vocab:
    """Item→id map with <pad>=0 and <unk>=1."""

    def __init__(self, items: dict[str, int] | None = None):
        self.stoi: dict[str, int] = items or {"<pad>": PAD, "<unk>": UNK}

    @classmethod
    def build(cls, iterables, max_size: int = 20000) -> "Vocab":
        from collections import Counter
        c: Counter = Counter()
        for seq in iterables:
            c.update(seq)
        v = cls()
        for item, _ in c.most_common(max_size):
            v.stoi.setdefault(item, len(v.stoi))
        return v

    def __len__(self) -> int:
        return len(self.stoi)

    def encode(self, seq) -> list[int]:
        return [self.stoi.get(x, UNK) for x in seq]


def pad_batch(seqs: list[list[int]], pad: int = PAD) -> torch.Tensor:
    n = max(len(s) for s in seqs)
    out = torch.full((len(seqs), n), pad, dtype=torch.long)
    for i, s in enumerate(seqs):
        out[i, :len(s)] = torch.tensor(s, dtype=torch.long)
    return out


def save_ckpt(path: Path, model: torch.nn.Module, extra: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), **extra}, path)


def load_ckpt(path: Path) -> dict:
    return torch.load(path, map_location="cpu", weights_only=False)


def read_jsonl(path: Path, limit: int | None = None) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
            if limit and len(rows) >= limit:
                break
    return rows


class WordTagger(torch.nn.Module):
    """Word-level sequence tagger with a character-BiLSTM word encoder
    (OOV-robust for Arabic morphology). Used by the POS and indexing models."""

    def __init__(self, n_chars: int, n_tags: int, char_emb: int = 64,
                 char_hid: int = 128, word_hid: int = 256):
        super().__init__()
        self.char_emb = torch.nn.Embedding(n_chars, char_emb, padding_idx=PAD)
        self.char_lstm = torch.nn.LSTM(char_emb, char_hid, batch_first=True,
                                       bidirectional=True)
        self.word_lstm = torch.nn.LSTM(char_hid * 2, word_hid, num_layers=2,
                                       batch_first=True, bidirectional=True,
                                       dropout=0.2)
        self.head = torch.nn.Linear(word_hid * 2, n_tags)

    def forward(self, chars: torch.Tensor) -> torch.Tensor:
        """chars: (batch, words, max_word_len) -> logits (batch, words, tags)."""
        b, w, c = chars.shape
        flat = chars.reshape(b * w, c)
        emb = self.char_emb(flat)
        _, (h, _) = self.char_lstm(emb)
        word_vecs = torch.cat([h[0], h[1]], dim=-1).reshape(b, w, -1)
        out, _ = self.word_lstm(word_vecs)
        return self.head(out)


def encode_words(words: list[str], vocab: "Vocab", max_len: int = 18) -> list[list[int]]:
    return [vocab.encode(list(w[:max_len])) or [UNK] for w in words]


def pad_words(batch: list[list[list[int]]]) -> torch.Tensor:
    """(batch of sentences of char-id lists) -> (b, max_words, max_chars)."""
    max_w = max(len(s) for s in batch)
    max_c = max((len(w) for s in batch for w in s), default=1)
    out = torch.full((len(batch), max_w, max_c), PAD, dtype=torch.long)
    for i, s in enumerate(batch):
        for j, w in enumerate(s):
            out[i, j, :len(w)] = torch.tensor(w, dtype=torch.long)
    return out


def split_of(key: str) -> str:
    """Deterministic 90/5/5 split by content hash."""
    import hashlib
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % 100
    return "train" if h < 90 else ("dev" if h < 95 else "test")
