"""Structural heading detection (§12.7): كتاب / باب / فصل / أبواب lines in
flat page dumps. Rule engine — the neural indexer (§12.9) is distilled from
this + dual-source alignment."""
import re
from dataclasses import dataclass

from ..normalize import normalize_arabic

# heading starters with their hierarchy level
_HEADING_LEVELS = [
    (re.compile(r"^(?:كتاب|كتب)\s"), 1),
    (re.compile(r"^(?:أبواب|ابواب)\s"), 2),
    (re.compile(r"^(?:باب)\b"), 3),
    (re.compile(r"^(?:فصل|مسأله|مساله|مسألة)\b"), 4),
]
_BASMALA = re.compile(r"^بسم الله الرحمن الرحيم")
_MAX_HEADING_WORDS = 25


@dataclass
class Heading:
    line_no: int
    level: int
    title: str
    start_char: int


def detect_headings(text: str) -> list[Heading]:
    """Find structural headings in a flat page text (line-oriented)."""
    headings: list[Heading] = []
    offset = 0
    for line_no, raw in enumerate(text.split("\n")):
        line = raw.strip()
        norm = normalize_arabic(line)
        if norm and not _BASMALA.match(norm):
            n_words = len(norm.split())
            if n_words <= _MAX_HEADING_WORDS:
                for rx, level in _HEADING_LEVELS:
                    if rx.match(norm):
                        headings.append(Heading(line_no=line_no, level=level,
                                                title=line, start_char=offset))
                        break
        offset += len(raw) + 1
    return headings
