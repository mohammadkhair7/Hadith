"""Query-side Arabic normalization — MUST stay in sync with etl/normalize.py."""
import re

_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED\u0640]")
_ALEF_FORMS = re.compile(r"[\u0622\u0623\u0625\u0671]")
_TA_MARBUTA = "\u0629"
_ALEF_MAQSURA = "\u0649"
_HAMZA_FORMS = re.compile(r"[\u0624\u0626]")
_WS = re.compile(r"\s+")


def normalize_arabic(text: str) -> str:
    if not text:
        return ""
    t = _DIACRITICS.sub("", text)
    t = _ALEF_FORMS.sub("\u0627", t)
    t = t.replace(_TA_MARBUTA, "\u0647")
    t = t.replace(_ALEF_MAQSURA, "\u064A")
    t = _HAMZA_FORMS.sub("\u0621", t)
    t = _WS.sub(" ", t)
    return t.strip()


_HAS_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670]")


def has_tashkeel(text: str) -> bool:
    return bool(_HAS_DIACRITICS.search(text or ""))
