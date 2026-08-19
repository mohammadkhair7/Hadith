"""Farasa JVM-backed engines (interim primaries + permanent validation
oracles, §12.8 stage P1). Each wraps one persistent JAR process."""
from typing import Any

from ...schema import whitespace_tokenize
from .process import JarProcess, find_jar


class _FarasaBase:
    project = ""                    # Grammar/<project>
    name = "farasa"
    version = "jar"
    layers: tuple[str, ...] = ()

    def __init__(self) -> None:
        self._proc: JarProcess | None = None
        self._available: bool | None = None
        self.unavailable_reason = ""

    def available(self) -> bool:
        if self._available is None:
            jar = find_jar(self.project)
            if jar is None:
                self.unavailable_reason = (
                    f"no dist JAR for {self.project} — build with "
                    f"`cd Grammar/{self.project} && ant jar`")
                self._available = False
            else:
                self._available = True
        return self._available

    def warm(self) -> None:
        if self._proc is None:
            jar = find_jar(self.project)
            assert jar is not None
            self._proc = JarProcess(jar)
            self._proc.start()

    def _run(self, text: str) -> str:
        self.warm()
        assert self._proc is not None
        return self._proc.process_line(text)


class FarasaSegmenterEngine(_FarasaBase):
    project = "Farasa-Segmenter-Jar"
    layers = ("segments",)

    def annotate_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        out = []
        for text in texts:
            master = whitespace_tokenize(text)
            seg_line = self._run(text)            # e.g. "و+قال ال+حمد ..."
            seg_tokens = seg_line.split()
            segments = []
            for i, tok in enumerate(master):
                if i < len(seg_tokens) and "+" in seg_tokens[i]:
                    segments.append({"token_idx": tok.idx,
                                     "parts": seg_tokens[i].split("+"),
                                     "engine": self.name})
            out.append({"segments": segments})
        return out


class FarasaPosEngine(_FarasaBase):
    project = "Farasa-Parts-of-Speech-Jar"
    layers = ("pos",)

    def annotate_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        out = []
        for text in texts:
            master = whitespace_tokenize(text)
            tagged = self._run(text).split()      # "word/TAG word/TAG ..."
            pos = []
            for i, tok in enumerate(master):
                if i < len(tagged) and "/" in tagged[i]:
                    pos.append({"token_idx": tok.idx,
                                "tag": tagged[i].rsplit("/", 1)[1],
                                "engine": self.name})
            out.append({"pos": pos})
        return out


class FarasaNerEngine(_FarasaBase):
    project = "Farasa-Named-Entity-Recognizer-Jar"
    layers = ("ner",)

    def annotate_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        out = []
        for text in texts:
            master = whitespace_tokenize(text)
            tagged = self._run(text).split()      # "word/B-PERS word/I-PERS word/O"
            entities, cur = [], None
            for i, tok in enumerate(master):
                lab = tagged[i].rsplit("/", 1)[1] if i < len(tagged) and "/" in tagged[i] else "O"
                if lab.startswith("B-"):
                    if cur:
                        entities.append(cur)
                    cur = {"start_token": i, "end_token": i, "label": lab[2:],
                           "text": tok.text, "engine": self.name, "confidence": 0.0}
                elif lab.startswith("I-") and cur:
                    cur["end_token"] = i
                    cur["text"] += " " + tok.text
                else:
                    if cur:
                        entities.append(cur)
                    cur = None
            if cur:
                entities.append(cur)
            out.append({"ner": entities})
        return out


class FarasaDiacritizeEngine(_FarasaBase):
    project = "Farasa-Diacritize-Jar"
    layers = ("diacritized",)

    def annotate_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        return [{"diacritized": {"text": self._run(t)}} for t in texts]
