"""Isnad-specific heuristics on top of the annotation layers (§9.2, §12.4):
locate the sanad/matn boundary and parse the transmission chain into
(verb, name-mention) hops. Consumed by the Phase 6 KG pipeline."""
import re
from dataclasses import dataclass, field

from .normalize import normalize_arabic

TRANSMISSION_VERBS = [
    "حدثنا", "حدثني", "اخبرنا", "اخبرني", "انبانا", "انبأنا", "سمعت", "سمع",
    "قال", "عن", "ان",
]
_VERB_RX = re.compile(
    r"\b(حدثنا|حدثني|اخبرنا|اخبرني|انبانا|سمعت|سمع|عن)\b")
# matn openers: the Prophet's speech markers
_MATN_START = re.compile(
    r"(قال\s+رسول\s+الله|قال\s+النبي|ان\s+رسول\s+الله|ان\s+النبي|"
    r"عن\s+النبي\s*صلي|يقول\s*:|قال\s*:\s*\")")


@dataclass
class Hop:
    verb: str
    mention: str                          # raw name span (normalized)
    pos: int                              # 0 = collector side


@dataclass
class IsnadParse:
    sanad_end: int                        # char offset where the matn starts (normalized text)
    hops: list[Hop] = field(default_factory=list)
    confidence: float = 0.0


def parse_isnad(text: str, ner_entities: list[dict] | None = None) -> IsnadParse:
    """Rule-based isnad parse of a hadith unit. If NER person spans are
    provided (Arabic-lib annotate), mentions snap to them; otherwise the
    span between transmission verbs is used."""
    norm = normalize_arabic(text)
    m = _MATN_START.search(norm)
    sanad_end = m.start() if m else min(len(norm), 300)
    sanad = norm[:sanad_end]

    hops: list[Hop] = []
    matches = list(_VERB_RX.finditer(sanad))
    for i, vm in enumerate(matches):
        start = vm.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(sanad)
        mention = sanad[start:end].strip(" ،:.")
        mention = re.sub(r"^(قال|قالا|قالوا)\s+", "", mention).strip()
        mention = re.sub(r"\s+(قال|قالا|قالوا)$", "", mention).strip()
        if 2 <= len(mention) <= 60:
            hops.append(Hop(verb=vm.group(1), mention=mention, pos=i))

    conf = 0.0
    if hops:
        conf = 0.5
        if matches and matches[0].start() < 15:
            conf += 0.2                    # unit starts with a transmission verb
        if m:
            conf += 0.3                    # explicit matn opener found
    return IsnadParse(sanad_end=sanad_end, hops=hops, confidence=round(conf, 2))
