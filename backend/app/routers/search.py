from fastapi import APIRouter, Query

from ..db import db
from ..services.search import keyword_search

router = APIRouter(tags=["search"])


@router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    mode: str = "keyword",          # keyword | exact | hybrid | semantic (3+ added in Phase 3)
    source: str | None = None,
    edition_id: int | None = None,
    kind: str | None = None,
    subject_id: int | None = None,
    limit: int = 20,
    offset: int = 0,
):
    limit = max(1, min(limit, 100))
    with db() as conn:
        if mode in ("keyword", "exact"):
            result = keyword_search(
                conn, q,
                exact=(mode == "exact"),
                source=source, edition_id=edition_id, work_kind=kind,
                subject_id=subject_id, limit=limit, offset=offset,
            )
            result["mode"] = mode
            return result
        if mode in ("semantic", "hybrid"):
            from ..services.vector import vector_search, hybrid_search
            if mode == "semantic":
                return vector_search(conn, q, source=source, edition_id=edition_id,
                                     limit=limit)
            return hybrid_search(conn, q, source=source, edition_id=edition_id,
                                 limit=limit)
    return {"total": 0, "items": [], "mode": mode}
