"""Engine registry (§12.2/§12.8): per-layer roles primary / fallback /
cross-validate. annotate() runs the best available engine for each requested
layer and merges the results into one token-aligned Annotation."""
from typing import Any

from ..schema import Annotation, DepArc, Entity, Segment, whitespace_tokenize
from .alkhalil_root import AlKhalilRootEngine
from .camel_morphology import CamelMorphologyEngine
from .camel_ner import CamelNerEngine
from .farasa_jar.engines import (FarasaDiacritizeEngine, FarasaNerEngine,
                                 FarasaPosEngine, FarasaSegmenterEngine)

# singletons (engines warm lazily and stay warm)
_camel_morph = CamelMorphologyEngine()
_camel_ner = CamelNerEngine()
_alkhalil = AlKhalilRootEngine()
_farasa_seg = FarasaSegmenterEngine()
_farasa_pos = FarasaPosEngine()
_farasa_ner = FarasaNerEngine()
_farasa_diac = FarasaDiacritizeEngine()

# layer -> engines in priority order (primary first, then fallbacks).
# Farasa is primary where present (user directive: Farasa quality is the
# benchmark); CAMeL is the always-available pure-Python fallback.
registry: dict[str, list[Any]] = {
    "segments": [_farasa_seg, _camel_morph],
    "pos": [_farasa_pos, _camel_morph],
    "ner": [_farasa_ner, _camel_ner],
    "roots": [_alkhalil, _camel_morph],       # AlKhalil2 primary for تجذير (§12.6)
    "diacritized": [_farasa_diac],
    "morphology": [_camel_morph],
    "dependency": [],                          # Farasa dependency: JAR build pending
    "constituency": [],
}

ALL_LAYERS = ("segments", "pos", "ner", "roots", "diacritized", "morphology")


def available_engines() -> dict[str, list[dict[str, str]]]:
    """Layer -> [{engine, version, available, reason}] for diagnostics."""
    out: dict[str, list[dict[str, str]]] = {}
    for layer, engines in registry.items():
        out[layer] = [{
            "engine": e.name, "version": e.version,
            "available": e.available(),
            "reason": "" if e.available() else getattr(e, "unavailable_reason", ""),
        } for e in engines]
    return out


def annotate(text: str, layers: list[str] | None = None,
             cross_validate: bool = False) -> Annotation:
    """Annotate one text across all requested layers simultaneously."""
    return annotate_batch([text], layers, cross_validate=cross_validate)[0]


def annotate_batch(texts: list[str], layers: list[str] | None = None,
                   cross_validate: bool = False) -> list[Annotation]:
    layers = list(layers or ALL_LAYERS)
    anns = [Annotation(text=t, tokens=whitespace_tokenize(t)) for t in texts]

    # choose one engine per layer; group layers served by the same engine so
    # multi-layer engines run once per batch
    chosen: dict[str, Any] = {}
    for layer in layers:
        for engine in registry.get(layer, []):
            if engine.available():
                chosen[layer] = engine
                break

    ran: set[int] = set()
    for layer, engine in chosen.items():
        if id(engine) in ran:
            continue
        ran.add(id(engine))
        results = engine.annotate_batch(texts)
        wanted = [l for l in layers if chosen.get(l) is engine]
        for ann, res in zip(anns, results):
            _merge(ann, res, wanted)

    for ann in anns:
        ann.meta["engines"] = {l: chosen[l].name for l in layers if l in chosen}
        ann.meta["missing_layers"] = [l for l in layers if l not in chosen]
    return anns


def _merge(ann: Annotation, res: dict[str, Any], wanted: list[str]) -> None:
    if "segments" in wanted and res.get("segments"):
        ann.segments.extend(Segment(**s) for s in res["segments"])
    if "pos" in wanted and res.get("pos"):
        ann.pos.extend(res["pos"])
    if "ner" in wanted and res.get("ner"):
        ann.ner.extend(Entity(**e) for e in res["ner"])
    if "roots" in wanted and res.get("roots"):
        ann.roots.extend(res["roots"])
    if "diacritized" in wanted and res.get("diacritized"):
        ann.diacritized = res["diacritized"]["text"]
    if "morphology" in wanted and res.get("morphology"):
        ann.morphology.extend(res["morphology"])
    if "dependency" in wanted and res.get("dependency"):
        ann.dependency.extend(DepArc(**a) for a in res["dependency"])
