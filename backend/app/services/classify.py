"""Classification taxonomies for multi-dimensional hadith search (§ classification):

1. Means of transmission (طرق التحمل) — canonical classes over the verbs the
   isnad extractor already stores per link (including copyists' abbreviations).
2. Hadith type (نوع الحديث) — rule classifier v0.1 assigning
   قدسي / مرفوع (قولي|فعلي) / موقوف / مقطوع from the matn opening,
   with narrator generation as a secondary signal.
"""
import re

# --- 1. transmission means -------------------------------------------------

TRANSMISSION_CLASSES: dict[str, dict] = {
    "sama":   {"ar": "سماع (حدثنا/سمعت)",
               "verbs": ["حدثنا", "حدثني", "ثنا", "نا", "سمعت", "سمع"]},
    "ikhbar": {"ar": "إخبار (أخبرنا)",
               "verbs": ["اخبرنا", "اخبرني", "انا", "ابنا"]},
    "inba":   {"ar": "إنباء (أنبأنا)",
               "verbs": ["انبانا", "انباني", "انبا"]},
    "ananah": {"ar": "عنعنة (عن)",
               "verbs": ["عن"]},
}

_VERB_TO_CLASS = {v: k for k, d in TRANSMISSION_CLASSES.items() for v in d["verbs"]}


def transmission_class(verb: str | None) -> str | None:
    return _VERB_TO_CLASS.get((verb or "").strip())


def transmission_verbs(key: str) -> list[str]:
    """Verbs for a class key; a raw verb form is accepted as its own filter."""
    if key in TRANSMISSION_CLASSES:
        return TRANSMISSION_CLASSES[key]["verbs"]
    return [key]


# --- 2. hadith type (نوع الحديث) — rule classifier v0.1 ---------------------

HADITH_TYPES: dict[str, str] = {
    "qudsi":        "حديث قدسي",
    "marfu_qawli":  "مرفوع — سنة قولية",
    "marfu_fili":   "مرفوع — سنة فعلية",
    "marfu":        "مرفوع",
    "mawquf":       "موقوف — قول صحابي",
    "maqtu":        "مقطوع — قول تابعي",
}

_MARKS = re.compile(r"[\u064B-\u0652\u0670\u0640]")
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
                       "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه"})

# «قال الله : ﴿...﴾» is a Quran citation, not قدسي — hence the bracket guard
_QUDSI = re.compile(
    r"(قال|يقول)\s+الله(?!\s*:?\s*[{﴿])|فيما يرويه عن ربه|فيما يروي عن ربه|"
    r"قال ربكم|عن ربه (عز وجل|تبارك)")
_PROPHET = r"(رسول\s+الله|النبي)"
_MARFU_QAWLI = re.compile(
    rf"(قال|يقول|فقال|سمعت)\s+{_PROPHET}|"
    rf"(عن|ان)\s+{_PROPHET}[^.]{{0,60}}?(قال|يقول|فقال|انه قال)|"
    rf"قال\s*:\s*قال\s+{_PROPHET}")
_MARFU_FILI = re.compile(
    rf"(كان|فكان)\s+{_PROPHET}|"
    rf"(رايت|رأيت)\s+{_PROPHET}|"
    rf"(ان|عن)\s+{_PROPHET}[^.]{{0,50}}?"
    r"(نهي|امر|صلي|صام|توضا|اغتسل|احتجم|خرج|دخل|فعل|صنع|قضي|كتب|بعث|مسح)")
_MARFU_ANY = re.compile(rf"{_PROPHET}|صلي الله عليه وسلم")


def _norm(s: str) -> str:
    return _MARKS.sub("", s or "").translate(_FOLD)


def classify_hadith_type(text_raw: str, sanad_end_raw: int | None,
                         last_generation: str | None) -> tuple[str, float] | None:
    """Returns (type_key, confidence) or None when no rule fires."""
    # sanad_end_raw indexes the RAW string, so slice raw first, then normalize.
    # The attribution to the Prophet often sits at the END of the sanad
    # («... عن أبي هريرة عن النبي ﷺ قال :») so the scan window must include
    # the sanad tail, not just the matn head.
    if sanad_end_raw and 0 < sanad_end_raw < len(text_raw or ""):
        matn = _norm(text_raw[sanad_end_raw:])
        tail = _norm(text_raw[max(0, sanad_end_raw - 130):sanad_end_raw])
    else:
        matn = _norm(text_raw)
        tail = ""
    head = tail + " " + matn[:600]

    if _QUDSI.search(head):
        return "qudsi", 0.85
    if _MARFU_QAWLI.search(head):
        return "marfu_qawli", 0.85
    if _MARFU_FILI.search(head):
        return "marfu_fili", 0.75
    if _MARFU_ANY.search(head[:250 + len(tail)]):
        return "marfu", 0.6
    if last_generation == "صحابي":
        return "mawquf", 0.55
    if last_generation == "تابعي":
        return "maqtu", 0.55
    return None
