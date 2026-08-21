"""Taxonomy endpoint for the multi-dimensional search facets: transmission
means (طرق التحمل) and hadith types (نوع الحديث), each with corpus counts."""
import time

from fastapi import APIRouter

from ..db import db, q
from ..services.classify import HADITH_TYPES, TRANSMISSION_CLASSES, transmission_class

router = APIRouter(tags=["classify"])

_cache: dict = {"at": 0.0, "data": None}
_TTL = 3600


GRADE_LABELS = {
    "sahih": "صحيح", "hasan_sahih": "حسن صحيح", "hasan": "حسن",
    "gharib": "غريب", "daif": "ضعيف", "maqbul": "مقبول",
    "mawdu": "موضوع", "other": "أخرى",
}


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
        grade_counts = {r["grade_norm"]: r["n"] for r in q(conn, """
            SELECT grade_norm, count(*) AS n FROM hadith_grades GROUP BY grade_norm
        """)}

    tclasses = []
    for key, d in TRANSMISSION_CLASSES.items():
        verbs = [{"verb": v, "chains": verb_counts.get(v, 0)} for v in d["verbs"]]
        tclasses.append({"key": key, "ar": d["ar"],
                         "verbs": verbs,
                         "chains": sum(v["chains"] for v in verbs)})
    types = [{"key": k, "ar": ar, "passages": type_counts.get(k, 0)}
             for k, ar in HADITH_TYPES.items()]
    grades = [{"key": k, "ar": GRADE_LABELS.get(k, k), "passages": n}
              for k, n in sorted(grade_counts.items(), key=lambda kv: -kv[1])]

    data = {"transmission": tclasses, "hadith_types": types, "grades": grades}
    _cache.update(at=now, data=data)
    return data
