"""Engine protocol (§12.2): every engine declares which layers it produces,
whether it is currently available on this machine, and annotates in batches.
Engines are warmed once (persistent JVM / loaded lexicons) and reused."""
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Engine(Protocol):
    name: str
    version: str
    layers: tuple[str, ...]         # subset of: segments,pos,ner,roots,diacritized,dependency,constituency,morphology

    def available(self) -> bool:
        """True when the engine's runtime prerequisites exist (JAR built,
        lexicon present, model downloaded). Must be cheap after first call."""
        ...

    def warm(self) -> None:
        """Load models / start JVM. Called once before the first batch."""
        ...

    def annotate_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        """Return one dict per text: {layer_name: payload} for the layers this
        engine produces. Token indices refer to whitespace master tokens."""
        ...
