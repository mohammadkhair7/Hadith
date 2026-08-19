"""AlKhalil2 root-allocation engine (§12.6). Wraps the pure-Python conversion
in Grammar/alkhalil_nlp. Requires its lexicon (`resources/Data.root` etc.),
which is NOT bundled in the repo — obtain it from the AlKhalil Morpho Sys 2
distribution (Oujda NLP team) and place it under Grammar/alkhalil_nlp/resources."""
import sys
from pathlib import Path
from typing import Any

from ..schema import whitespace_tokenize

_ALKHALIL_DIR = Path(__file__).resolve().parents[3] / "Grammar" / "alkhalil_nlp"


class AlKhalilRootEngine:
    name = "alkhalil"
    version = "2.0-py"
    layers = ("roots",)

    def __init__(self) -> None:
        self._analyzer = None
        self._available: bool | None = None
        self.unavailable_reason = ""

    def available(self) -> bool:
        if self._available is None:
            resources = _ALKHALIL_DIR / "resources" / "Data.root"
            if not _ALKHALIL_DIR.exists():
                self.unavailable_reason = f"{_ALKHALIL_DIR} not found"
                self._available = False
            elif not resources.exists():
                self.unavailable_reason = (
                    f"lexicon missing: {resources} — obtain the AlKhalil Morpho Sys 2 "
                    "resources (Data.root and companions) and place them there")
                self._available = False
            else:
                self._available = True
        return self._available

    def warm(self) -> None:
        if self._analyzer is None:
            if str(_ALKHALIL_DIR) not in sys.path:
                sys.path.insert(0, str(_ALKHALIL_DIR))
            import os
            cwd = os.getcwd()
            os.chdir(_ALKHALIL_DIR)               # AlKhalil resolves resources/ from CWD
            try:
                from AlKhalil2Analyzer import AlKhalil2Analyzer  # type: ignore
                self._analyzer = AlKhalil2Analyzer()
            finally:
                os.chdir(cwd)

    def annotate_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        self.warm()
        out = []
        for text in texts:
            master = whitespace_tokenize(text)
            roots = []
            for tok in master:
                try:
                    analyses = self._analyzer.analyze(tok.text)
                except Exception:
                    continue
                if not analyses:
                    continue
                a = analyses[0] if isinstance(analyses, list) else analyses
                root = (a.get("root") if isinstance(a, dict)
                        else getattr(a, "root", "")) or ""
                pattern = (a.get("pattern") if isinstance(a, dict)
                           else getattr(a, "pattern", "")) or ""
                if root:
                    roots.append({"token_idx": tok.idx, "root": root,
                                  "pattern": pattern, "lemma": "",
                                  "engine": self.name})
            out.append({"roots": roots})
        return out
