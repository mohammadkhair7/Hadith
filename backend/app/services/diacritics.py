"""Recover authentic tashkeel for sunna passages from the vocalized source
HTML (hadith.db stored plain text without marks but HTML with full marks).

The marks are transplanted letter-by-letter onto text_raw, so the base text
stays byte-identical — sanad/matn character offsets remain valid and Quran
quotes keep their original (source) vocalization untouched. If the letter
streams cannot be aligned confidently the function returns None (no marks is
better than wrong marks).
"""
import html as html_mod
import re

_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.I | re.S)
_MARK = re.compile(r"[\u064B-\u0652\u0670]")
_AR_LETTER = re.compile(r"[\u0621-\u064A]")

# folding for letter comparison only (sources differ in hamza/teh-marbuta forms)
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
                       "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه"})

_MAX_SKIP = 8          # letters the html stream may run ahead (extra content)
_MAX_FAILS = 0         # alignment must be exact once skips are allowed


def from_html(text_raw: str, html_src: str | None) -> str | None:
    if not html_src or not text_raw:
        return None
    ht = html_mod.unescape(_TAG.sub(" ", _SCRIPT.sub(" ", html_src)))
    # harvest the vocalized letter stream: (letter, trailing marks)
    pairs: list[tuple[str, str]] = []
    i, L = 0, len(ht)
    while i < L:
        ch = ht[i]
        if _AR_LETTER.match(ch):
            j = i + 1
            while j < L and _MARK.match(ht[j]):
                j += 1
            pairs.append((ch, ht[i + 1:j]))
            i = j
        else:
            i += 1
    if not pairs:
        return None

    folded = [p[0].translate(_FOLD) for p in pairs]
    raw_letter_pos = [i for i, c in enumerate(text_raw) if _AR_LETTER.match(c)]
    n = len(pairs)
    out: list[str] = []
    k = 0            # cursor in the html letter stream
    ri = 0           # index within raw_letter_pos
    for i, ch in enumerate(text_raw):
        out.append(ch)
        if not _AR_LETTER.match(ch):
            continue
        f = ch.translate(_FOLD)
        hit = -1
        for skip in range(_MAX_SKIP + 1):
            j = k + skip
            if j >= n:
                break
            if folded[j] != f:
                continue
            if skip == 0:
                hit = j
                break
            # a skip must be confirmed by the following letter to avoid
            # locking onto a coincidental match inside the extra content
            if ri + 1 < len(raw_letter_pos):
                nxt = text_raw[raw_letter_pos[ri + 1]].translate(_FOLD)
                if j + 1 < n and folded[j + 1] != nxt:
                    continue
            hit = j
            break
        if hit < 0:
            return None
        out.append(pairs[hit][1])
        k = hit + 1
        ri += 1
    return "".join(out)
