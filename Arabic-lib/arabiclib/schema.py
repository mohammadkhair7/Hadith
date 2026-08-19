"""Token-aligned annotation dataclasses (§12.2). All layers are indexed
against one master token sequence."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Token:
    idx: int
    text: str                       # surface form as in the source text
    start: int                      # char offset in the original text
    end: int


@dataclass
class Segment:
    token_idx: int
    parts: list[str]                # clitic-segmented parts, e.g. ["و", "قال"]
    engine: str = ""


@dataclass
class Entity:
    start_token: int
    end_token: int                  # inclusive
    label: str                      # PERS | LOC | ORG | ...
    text: str = ""
    engine: str = ""
    confidence: float = 0.0


@dataclass
class DepArc:
    dependent: int                  # token idx
    head: int                       # token idx (-1 = root)
    relation: str
    engine: str = ""


@dataclass
class Annotation:
    """Result of annotate(): master tokens + requested layers."""
    text: str
    tokens: list[Token] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    pos: list[dict[str, Any]] = field(default_factory=list)        # {token_idx, tag, engine}
    ner: list[Entity] = field(default_factory=list)
    roots: list[dict[str, Any]] = field(default_factory=list)      # {token_idx, root, pattern, lemma, engine}
    diacritized: str | None = None
    dependency: list[DepArc] = field(default_factory=list)
    morphology: list[dict[str, Any]] = field(default_factory=list) # full CAMeL analyses
    meta: dict[str, Any] = field(default_factory=dict)             # engine versions, timings

    def to_payloads(self) -> dict[str, Any]:
        """Layer -> JSON-serializable payload for passage_annotations."""
        out: dict[str, Any] = {}
        if self.segments:
            out["segments"] = [vars(s) for s in self.segments]
        if self.pos:
            out["pos"] = self.pos
        if self.ner:
            out["ner"] = [vars(e) for e in self.ner]
        if self.roots:
            out["roots"] = self.roots
        if self.diacritized:
            out["diacritized"] = {"text": self.diacritized}
        if self.dependency:
            out["dependency"] = [vars(a) for a in self.dependency]
        if self.morphology:
            out["morphology"] = self.morphology
        return out


def whitespace_tokenize(text: str) -> list[Token]:
    """Master tokenization: simple whitespace+punct spans; engine-specific
    tokenizations are aligned back onto these via character offsets."""
    tokens: list[Token] = []
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        j = i
        while j < n and not text[j].isspace():
            j += 1
        tokens.append(Token(idx=len(tokens), text=text[i:j], start=i, end=j))
        i = j
    return tokens
