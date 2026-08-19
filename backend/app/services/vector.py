"""Redis vector layer (§7.2): HNSW FLOAT16 768-d index over hash keys
{prefix}:emb:{edition_id}:{passage_id}:{chunk_no}. Redis holds vectors +
minimal filter metadata only; Postgres remains the canonical text store."""
from typing import Any

import numpy as np
import redis

from ..config import settings
from .embeddings import embed_query
from .search import keyword_search

_r: redis.Redis | None = None

EMB_PREFIX = f"{settings.redis_prefix}:emb:"
INDEX_NAME = f"{settings.redis_prefix}:idx:passages"


def rconn() -> redis.Redis:
    global _r
    if _r is None:
        _r = redis.from_url(settings.redis_url, decode_responses=False)
    return _r


def ensure_index() -> None:
    r = rconn()
    try:
        r.execute_command("FT.INFO", INDEX_NAME)
        return
    except redis.ResponseError:
        pass
    r.execute_command(
        "FT.CREATE", INDEX_NAME, "ON", "HASH", "PREFIX", "1", EMB_PREFIX,
        "SCHEMA",
        "vec", "VECTOR", "HNSW", "6", "TYPE", "FLOAT16",
        "DIM", str(settings.embedding_dimensions), "DISTANCE_METRIC", "COSINE",
        "work_id", "NUMERIC",
        "edition_id", "NUMERIC",
        "kind", "TAG",
        "source", "TAG",
    )


def emb_key(edition_id: int, passage_id: int, chunk_no: int) -> str:
    return f"{EMB_PREFIX}{edition_id}:{passage_id}:{chunk_no}"


def write_vector(edition_id: int, passage_id: int, chunk_no: int,
                 vec: list[float], *, work_id: int, kind: str, source: str,
                 hadith_num: str | None, content_hash: str) -> None:
    r = rconn()
    r.hset(emb_key(edition_id, passage_id, chunk_no), mapping={
        "vec": np.asarray(vec, dtype=np.float16).tobytes(),
        "passage_id": passage_id,
        "edition_id": edition_id,
        "work_id": work_id,
        "chunk_no": chunk_no,
        "kind": kind,
        "source": source,
        "hadith_num": hadith_num or "",
        "content_hash": content_hash,
    })


def knn(query: str, *, source: str | None = None, edition_id: int | None = None,
        kind: str | None = None, k: int = 50) -> list[dict[str, Any]]:
    """KNN with pre-filtering; returns [{passage_id, score, ...}] best-first,
    deduplicated by passage (best chunk wins)."""
    ensure_index()
    qvec = np.asarray(embed_query(query), dtype=np.float16).tobytes()
    filters = []
    if source:
        filters.append(f"@source:{{{source}}}")
    if kind:
        filters.append(f"@kind:{{{kind}}}")
    if edition_id:
        filters.append(f"@edition_id:[{edition_id} {edition_id}]")
    prefilter = " ".join(filters) if filters else "*"
    query_str = f"({prefilter})=>[KNN {k} @vec $BLOB AS score]" if filters \
        else f"*=>[KNN {k} @vec $BLOB AS score]"
    res = rconn().execute_command(
        "FT.SEARCH", INDEX_NAME, query_str,
        "PARAMS", "2", "BLOB", qvec,
        "RETURN", "4", "passage_id", "edition_id", "chunk_no", "score",
        "SORTBY", "score", "ASC",
        "LIMIT", "0", str(k),
        "DIALECT", "2",
    )
    hits: dict[int, dict[str, Any]] = {}
    for d in _parse_ft_search(res):
        pid = int(d["passage_id"])
        score = 1.0 - float(d["score"])          # cosine distance -> similarity
        if pid not in hits or score > hits[pid]["score"]:
            hits[pid] = {"passage_id": pid,
                         "edition_id": int(d.get("edition_id", 0)),
                         "chunk_no": int(d.get("chunk_no", 0)),
                         "score": round(score, 4)}
    return sorted(hits.values(), key=lambda h: -h["score"])


def _parse_ft_search(res) -> list[dict[str, str]]:
    """Normalize FT.SEARCH replies: Redis 8 dict format {b'results': [...]},
    or the classic flat array [total, key, [f, v, ...], ...]."""
    def dec(v):
        return v.decode() if isinstance(v, bytes) else v

    if isinstance(res, dict):
        out = []
        for item in res.get(b"results", res.get("results", [])):
            attrs = item.get(b"extra_attributes", item.get("extra_attributes", {}))
            out.append({dec(k): dec(v) for k, v in attrs.items()})
        return out
    out = []
    for i in range(1, len(res), 2):
        fields = res[i + 1]
        out.append({dec(fields[j]): dec(fields[j + 1]) for j in range(0, len(fields), 2)})
    return out


def coverage_notice(conn, *, source: str | None, edition_id: int | None) -> dict:
    """Report how much of the current filter scope is embedded (§7.2)."""
    where, params = ["1=1"], []
    if source:
        where.append("e.source = %s")
        params.append(source)
    if edition_id:
        where.append("e.edition_id = %s")
        params.append(edition_id)
    row = conn.execute(f"""
        SELECT count(*) AS editions,
               count(*) FILTER (WHERE EXISTS (
                   SELECT 1 FROM embedding_jobs j
                   WHERE j.edition_id = e.edition_id AND j.status='embedded')) AS embedded
        FROM editions e WHERE {' AND '.join(where)}
    """, params).fetchone()
    return {"editions_in_scope": row["editions"], "editions_with_embeddings": row["embedded"]}


def _hydrate(conn, hits: list[dict], extra: dict[int, dict] | None = None) -> list[dict]:
    if not hits:
        return []
    ids = [h["passage_id"] for h in hits]
    rows = conn.execute("""
        SELECT p.passage_id, p.edition_id, p.seq, p.kind, p.hadith_num, p.part, p.page,
               p.source, left(p.text_raw, 400) AS snippet,
               e.title_ar AS edition_title, w.work_id, w.title_ar AS work_title
        FROM passages p
        JOIN editions e USING (edition_id)
        JOIN works w USING (work_id)
        WHERE p.passage_id = ANY(%s)
    """, (ids,)).fetchall()
    by_id = {r["passage_id"]: r for r in rows}
    out = []
    for h in hits:
        r = by_id.get(h["passage_id"])
        if not r:
            continue
        item = dict(r)
        item["score"] = h.get("score")
        if extra and h["passage_id"] in extra:
            item.update(extra[h["passage_id"]])
        out.append(item)
    return out


def vector_search(conn, query: str, *, source: str | None = None,
                  edition_id: int | None = None, limit: int = 20) -> dict:
    hits = knn(query, source=source, edition_id=edition_id, k=max(limit, 20))[:limit]
    items = _hydrate(conn, hits)
    return {"total": len(items), "items": items, "mode": "semantic",
            "coverage": coverage_notice(conn, source=source, edition_id=edition_id)}


def hybrid_search(conn, query: str, *, source: str | None = None,
                  edition_id: int | None = None, limit: int = 20) -> dict:
    """Reciprocal Rank Fusion of the keyword and vector paths (§8.1)."""
    K = 60
    kw = keyword_search(conn, query, source=source, edition_id=edition_id,
                        limit=50, offset=0)
    vec_hits = knn(query, source=source, edition_id=edition_id, k=50)

    scores: dict[int, float] = {}
    kw_items = {it["passage_id"]: it for it in kw["items"]}
    for rank, it in enumerate(kw["items"]):
        scores[it["passage_id"]] = scores.get(it["passage_id"], 0) + 1 / (K + rank + 1)
    for rank, h in enumerate(vec_hits):
        scores[h["passage_id"]] = scores.get(h["passage_id"], 0) + 1 / (K + rank + 1)

    fused = sorted(scores.items(), key=lambda kv: -kv[1])[:limit]
    hits = [{"passage_id": pid, "score": round(s, 5)} for pid, s in fused]
    # keyword items already carry highlighted snippets — keep them
    extra = {pid: {"snippet": kw_items[pid]["snippet"]} for pid, _ in fused if pid in kw_items}
    items = _hydrate(conn, hits, extra)
    return {"total": len(items), "items": items, "mode": "hybrid",
            "keyword_total": kw["total"],
            "coverage": coverage_notice(conn, source=source, edition_id=edition_id)}
