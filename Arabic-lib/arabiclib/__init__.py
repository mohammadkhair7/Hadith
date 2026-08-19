"""Arabic-lib: unified Arabic linguistic annotation over Farasa, CAMeL Tools
and AlKhalil2 engines (architecture §12.2).

    from arabiclib import annotate
    ann = annotate("حدثنا عبد الله بن يوسف قال أخبرنا مالك",
                   layers=["segments", "pos", "ner", "roots"])
"""
from .schema import Annotation, DepArc, Entity, Segment, Token
from .engines.registry import annotate, available_engines, registry

__version__ = "0.1.0"
__all__ = ["annotate", "available_engines", "registry",
           "Annotation", "Token", "Segment", "Entity", "DepArc"]
