"""CAMeL Tools transformer NER (CAMeLBERT) — pure Python. The pretrained model
(~500 MB) is downloaded once via `camel_data -i ner-arabert`."""
from typing import Any

from ..schema import whitespace_tokenize


class CamelNerEngine:
    name = "camel"
    version = ""
    layers = ("ner",)

    def __init__(self) -> None:
        self._ner = None
        self._available: bool | None = None
        self.unavailable_reason = ""

    def available(self) -> bool:
        if self._available is None:
            try:
                import camel_tools
                self.version = camel_tools.__version__
                from camel_tools.ner import NERecognizer
                NERecognizer.pretrained()          # raises if model not downloaded
                self._available = True
            except Exception as e:
                self.unavailable_reason = (
                    f"{type(e).__name__}: {e} — run `camel_data -i ner-arabert`")
                self._available = False
        return self._available

    def warm(self) -> None:
        if self._ner is None:
            from camel_tools.ner import NERecognizer
            self._ner = NERecognizer.pretrained()

    def annotate_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        self.warm()
        out = []
        for text in texts:
            master = whitespace_tokenize(text)
            words = [t.text for t in master]
            labels = self._ner.predict_sentence(words)
            entities, cur = [], None
            for i, lab in enumerate(labels):
                if lab.startswith("B-"):
                    if cur:
                        entities.append(cur)
                    cur = {"start_token": i, "end_token": i, "label": lab[2:],
                           "text": words[i], "engine": self.name, "confidence": 0.0}
                elif lab.startswith("I-") and cur and lab[2:] == cur["label"]:
                    cur["end_token"] = i
                    cur["text"] += " " + words[i]
                else:
                    if cur:
                        entities.append(cur)
                    cur = None
            if cur:
                entities.append(cur)
            out.append({"ner": entities})
        return out
