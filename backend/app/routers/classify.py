"""Taxonomy endpoint for the multi-dimensional search facets: transmission
means (طرق التحمل) and hadith types (نوع الحديث), each with corpus counts."""
import time

from fastapi import APIRouter

from ..db import db, q
from ..services.classify import HADITH_TYPES, TRANSMISSION_CLASSES, transmission_class

router = APIRouter(tags=["classify"])

_cache: dict = {"at": 0.0, "data": None}
_TTL = 3600


@router.get("/classify/taxonomy")
def taxonomy():
    now = time.time()
    if _cache["data"] and now - _cache["at"] < _TTL:
        return _cache["data"]
    with db() as conn:
        verb_counts = {r["verb"]: r["n"] for r in q(conn, """
            SELECT verb, count(DISTINCT chain_id) AS n
            FROM isnad_links WHERE verb IS NOT NULL GROUP BY verb
        """)}
        type_counts = {r["type_norm"]: r["n"] for r in q(conn, """
            SELECT type_norm, count(*) AS n FROM hadith_types GROUP BY type_norm
        """)}

    tclasses = []
    for key, d in TRANSMISSION_CLASSES.items():
        n = sum(c for v, c in verb_counts.items() if transmission_class(v) == key)
        tclasses.append({"key": key, "ar": d["ar"], "verbs": d["verbs"], "chains": n})
    types = [{"key": k, "ar": ar, "passages": type_counts.get(k, 0)}
             for k, ar in HADITH_TYPES.items()]

    data = {"transmission": tclasses, "hadith_types": types}
    _cache.update(at=now, data=data)
    return data
