"""Hadith-number extraction & reconciliation (§12.7): leading numerals
(Arabic-Indic or European) that number hadith units, with sequence-based
filtering to reject page numbers and dates."""
import re
from dataclasses import dataclass

_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
# leading "123 -" / "123-" / "(123)" / "[123]" unit numbers
_NUM_HEAD = re.compile(r"^\s*[\(\[]?([0-9٠-٩]{1,5})[\)\]]?\s*[-–—.:]\s*")


@dataclass
class NumberedSpan:
    start_char: int
    number: int
    raw: str


def extract_hadith_numbers(text: str) -> list[NumberedSpan]:
    """All plausible unit-number heads in a text, in document order."""
    spans: list[NumberedSpan] = []
    offset = 0
    for raw_line in text.split("\n"):
        m = _NUM_HEAD.match(raw_line)
        if m:
            n = int(m.group(1).translate(_ARABIC_INDIC))
            if 0 < n < 100_000:
                spans.append(NumberedSpan(start_char=offset + m.start(1),
                                          number=n, raw=m.group(0).strip()))
        offset += len(raw_line) + 1
    return reconcile(spans)


def reconcile(spans: list[NumberedSpan], max_gap: int = 50) -> list[NumberedSpan]:
    """Keep the longest roughly-monotonic subsequence: hadith numbers increase
    (with small gaps/repeats); page numbers and years break monotonicity."""
    if len(spans) < 3:
        return spans
    kept: list[NumberedSpan] = []
    for s in spans:
        if not kept:
            kept.append(s)
            continue
        prev = kept[-1].number
        if prev <= s.number <= prev + max_gap or s.number == prev:
            kept.append(s)
        elif s.number < prev and kept and len(kept) >= 2 and \
                kept[-2].number <= s.number <= kept[-2].number + max_gap:
            kept[-1] = s                      # previous was the outlier
    return kept
