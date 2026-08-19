"""Hadith-unit segmentation (§12.7): split flat page text into hadith units
using number heads, isnad-start markers, and headings as boundaries."""
import re
from dataclasses import dataclass, field

from ..normalize import normalize_arabic
from .headings import Heading, detect_headings
from .numbering import NumberedSpan, extract_hadith_numbers

# isnad openers — strong signals that a new hadith unit starts
_ISNAD_START = re.compile(
    r"^(?:حدثنا|حدثني|اخبرنا|اخبرني|انبانا|انبأنا|سمعت|عن\s|قال\s+رسول|"
    r"وحدثنا|وحدثني|واخبرنا|واخبرني)\b")


@dataclass
class Unit:
    start_char: int
    end_char: int
    hadith_num: int | None
    heading: str | None                    # nearest enclosing heading title
    text: str = ""
    signals: list[str] = field(default_factory=list)


def segment_units(text: str) -> list[Unit]:
    """Segment a flat text into hadith units. Boundary signals in priority:
    numbered head > heading line > isnad opener at line start."""
    headings = detect_headings(text)
    numbers = extract_hadith_numbers(text)
    boundaries: list[tuple[int, str, object]] = []
    for h in headings:
        boundaries.append((h.start_char, "heading", h))
    for n in numbers:
        boundaries.append((n.start_char, "number", n))

    # isnad-opener lines that are not already boundaries
    taken = {b[0] for b in boundaries}
    offset = 0
    for raw in text.split("\n"):
        norm = normalize_arabic(raw.strip())
        if norm and _ISNAD_START.match(norm) and offset not in taken:
            boundaries.append((offset, "isnad", None))
        offset += len(raw) + 1

    boundaries.sort(key=lambda b: b[0])
    units: list[Unit] = []
    current_heading: str | None = None
    for i, (pos, kind, obj) in enumerate(boundaries):
        if kind == "heading":
            current_heading = obj.title  # type: ignore[union-attr]
            continue
        end = next((b[0] for b in boundaries[i + 1:]), len(text))
        num = obj.number if kind == "number" else None  # type: ignore[union-attr]
        chunk = text[pos:end].strip()
        if len(normalize_arabic(chunk)) < 20:
            continue
        units.append(Unit(start_char=pos, end_char=end, hadith_num=num,
                          heading=current_heading, text=chunk, signals=[kind]))
    return units
