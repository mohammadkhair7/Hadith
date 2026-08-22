from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import db, q, q1
from ..services.auth import admin_user

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/status")
def status(user: dict = Depends(admin_user)):
    with db() as conn:
        counts = {r["t"]: r["n"] for r in q(conn, """
            SELECT 'works' AS t, count(*) AS n FROM works
            UNION ALL SELECT 'editions', count(*) FROM editions
            UNION ALL SELECT 'passages', count(*) FROM passages
            UNION ALL SELECT 'toc_nodes', count(*) FROM toc_nodes
            UNION ALL SELECT 'subjects', count(*) FROM subjects
            UNION ALL SELECT 'subject_links', count(*) FROM subject_links
            UNION ALL SELECT 'narrators', count(*) FROM narrators
            UNION ALL SELECT 'translations', count(*) FROM translations
            UNION ALL SELECT 'users', count(*) FROM users
        """)}
        by_source = q(conn, """
            SELECT source, count(*) AS passages, count(DISTINCT edition_id) AS editions
            FROM passages GROUP BY source ORDER BY source
        """)
        etl = q(conn, "SELECT step, status, detail, updated_at FROM etl_state ORDER BY updated_at DESC LIMIT 25")
        emb = q1(conn, """
            SELECT count(*) FILTER (WHERE status='embedded') AS embedded,
                   count(*) AS total
            FROM embedding_jobs
        """)
        db_size = q1(conn, "SELECT pg_size_pretty(pg_database_size(current_database())) AS size")
    return {"counts": counts, "by_source": by_source, "etl_recent": etl,
            "embeddings": emb, "db_size": db_size["size"]}


# --- Narrator Management (merge / create / delete / relations) --------------

def _invalidate_narrator_caches() -> None:
    from .narrators import _DIR_CACHE, _FACETS_CACHE
    _DIR_CACHE.clear()
    _FACETS_CACHE.clear()


class MergeBody(BaseModel):
    target_id: int
    source_ids: list[int]


@router.post("/narrators/merge")
def merge_narrators(body: MergeBody, user: dict = Depends(admin_user)):
    from ..services.narrator_admin import merge_narrators as do_merge
    with db() as conn:
        try:
            result = do_merge(conn, body.target_id, body.source_ids, user["email"])
        except ValueError as e:
            raise HTTPException(400, str(e))
    _invalidate_narrator_caches()
    return result


class CreateNarratorBody(BaseModel):
    canonical_ar: str
    kunya: str | None = None
    laqab: str | None = None
    generation: str | None = None
    death_year_h: int | None = None
    bio_summary: str | None = None


@router.post("/narrators")
def create_narrator(body: CreateNarratorBody, user: dict = Depends(admin_user)):
    from ..services.narrator_admin import create_narrator as do_create
    with db() as conn:
        try:
            nid = do_create(conn, body.model_dump(), user["email"])
        except ValueError as e:
            raise HTTPException(400, str(e))
    _invalidate_narrator_caches()
    return {"narrator_id": nid}


@router.delete("/narrators/{narrator_id}")
def delete_narrator(narrator_id: int, user: dict = Depends(admin_user)):
    from ..services.narrator_admin import delete_narrator as do_delete
    with db() as conn:
        try:
            result = do_delete(conn, narrator_id, user["email"])
        except ValueError as e:
            raise HTTPException(404, str(e))
    _invalidate_narrator_caches()
    return result


class RelationBody(BaseModel):
    student_id: int
    teacher_id: int
    action: str                 # add | remove (override on the derived graph)
    weight: int = 1
    note: str | None = None


@router.get("/narrators/relations")
def list_relations(user: dict = Depends(admin_user)):
    from ..services.narrator_admin import ensure_tables
    with db() as conn:
        ensure_tables(conn)
        return q(conn, """
            SELECT m.edge_id, m.student_id, m.teacher_id, m.action, m.weight,
                   m.note, m.created_by, m.created_at,
                   sn.canonical_ar AS student_name, tn.canonical_ar AS teacher_name
            FROM narrator_edges_manual m
            JOIN narrators sn ON sn.narrator_id = m.student_id
            JOIN narrators tn ON tn.narrator_id = m.teacher_id
            ORDER BY m.created_at DESC LIMIT 200
        """)


@router.post("/narrators/relations")
def add_relation(body: RelationBody, user: dict = Depends(admin_user)):
    from ..services.narrator_admin import audit, ensure_tables
    if body.action not in ("add", "remove"):
        raise HTTPException(400, "action must be add or remove")
    if body.student_id == body.teacher_id:
        raise HTTPException(400, "student and teacher must differ")
    with db() as conn:
        ensure_tables(conn)
        for nid in (body.student_id, body.teacher_id):
            if not q1(conn, "SELECT 1 AS x FROM narrators WHERE narrator_id=%s", (nid,)):
                raise HTTPException(404, f"narrator {nid} not found")
        row = conn.execute("""
            INSERT INTO narrator_edges_manual
                (student_id, teacher_id, action, weight, note, created_by)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (student_id, teacher_id, action)
            DO UPDATE SET weight=EXCLUDED.weight, note=EXCLUDED.note
            RETURNING edge_id
        """, (body.student_id, body.teacher_id, body.action,
              max(body.weight, 1), body.note, user["email"])).fetchone()
        audit(conn, "relation_" + body.action,
              {"student_id": body.student_id, "teacher_id": body.teacher_id,
               "note": body.note}, user["email"])
        conn.commit()
    return {"edge_id": row["edge_id"]}


@router.delete("/narrators/relations/{edge_id}")
def delete_relation(edge_id: int, user: dict = Depends(admin_user)):
    from ..services.narrator_admin import audit, ensure_tables
    with db() as conn:
        ensure_tables(conn)
        row = conn.execute("""
            DELETE FROM narrator_edges_manual WHERE edge_id=%s
            RETURNING student_id, teacher_id, action
        """, (edge_id,)).fetchone()
        if not row:
            raise HTTPException(404, "override not found")
        audit(conn, "relation_override_undo",
              {"edge_id": edge_id, "student_id": row["student_id"],
               "teacher_id": row["teacher_id"], "was": row["action"]}, user["email"])
        conn.commit()
    return {"deleted": edge_id}


@router.get("/narrators/audit")
def narrator_audit(limit: int = 50, user: dict = Depends(admin_user)):
    from ..services.narrator_admin import ensure_tables
    with db() as conn:
        ensure_tables(conn)
        return q(conn, """
            SELECT audit_id, action, payload, admin_email, created_at
            FROM admin_audit ORDER BY audit_id DESC LIMIT %s
        """, (min(limit, 200),))


# --- Book Embedding Management (§7.4) ---------------------------------------

class EmbJobBody(BaseModel):
    edition_ids: list[int]
    mode: str = "skip"          # skip | overwrite


# gemini-embedding-001 paid tier, standard (non-batch) API, USD per 1M input
# tokens (https://ai.google.dev/gemini-api/docs/pricing, checked 2026-08-21).
# Output dimensionality (768-d here) does not affect the price.
EMBED_USD_PER_MTOK = 0.15


@router.get("/embeddings/coverage")
def embeddings_coverage(user: dict = Depends(admin_user)):
    from ..services.embed_jobs import coverage, list_jobs, staged_count
    with db() as conn:
        rows = coverage(conn)
        staged = staged_count(conn)
    # rough cost estimate: Arabic ≈ 2.5 chars/token
    for r in rows:
        r["est_tokens_total"] = int((r["total_chars"] or 0) / 2.5)
        r["est_cost_usd"] = round(r["est_tokens_total"] / 1e6 * EMBED_USD_PER_MTOK, 4)
    return {"editions": rows, "jobs": list_jobs(), "staged": staged,
            "price_usd_per_mtok": EMBED_USD_PER_MTOK}


@router.post("/embeddings/jobs")
def start_embedding_job(body: EmbJobBody, user: dict = Depends(admin_user)):
    from ..services.embed_jobs import start_job, list_jobs
    if body.mode not in ("skip", "overwrite"):
        raise HTTPException(400, "mode must be skip or overwrite")
    if not body.edition_ids:
        raise HTTPException(400, "edition_ids required")
    if any(j["status"] == "running" for j in list_jobs()):
        raise HTTPException(409, "another embedding job is already running")
    job_id = start_job(body.edition_ids, body.mode, started_by=user["email"])
    return {"job_id": job_id}


@router.post("/embeddings/import-staged")
def import_staged_vectors(user: dict = Depends(admin_user)):
    """Move vectors staged in Postgres (vector_stage) into this environment's
    Redis. Used to publish locally computed embeddings to production."""
    from ..services.embed_jobs import list_jobs, staged_count, start_import_staged
    if any(j["status"] == "running" for j in list_jobs()):
        raise HTTPException(409, "another embedding job is already running")
    with db() as conn:
        if not staged_count(conn):
            raise HTTPException(400, "no staged vectors — run ops/railway_push_vectors.py first")
    return {"job_id": start_import_staged(started_by=user["email"])}


@router.get("/embeddings/jobs/{job_id}")
def embedding_job_status(job_id: str, user: dict = Depends(admin_user)):
    from ..services.embed_jobs import job_status
    j = job_status(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j


@router.post("/embeddings/jobs/{job_id}/cancel")
def cancel_embedding_job(job_id: str, user: dict = Depends(admin_user)):
    from ..services.embed_jobs import cancel_job
    if not cancel_job(job_id):
        raise HTTPException(404, "no running job with this id")
    return {"cancelled": job_id}


# --- Translation Management (§11.3/§11.6) ------------------------------------

class TransJobBody(BaseModel):
    edition_ids: list[int]
    lang: str = "en"
    mode: str = "skip"          # skip | overwrite
    limit: int | None = None    # pilot cap per run


@router.get("/translations/coverage")
def translations_coverage(lang: str = "en", user: dict = Depends(admin_user)):
    from ..services.translate import coverage, list_jobs
    with db() as conn:
        rows = coverage(conn, lang)
    return {"editions": rows, "jobs": list_jobs(), "lang": lang}


@router.post("/translations/jobs")
def start_translation_job(body: TransJobBody, user: dict = Depends(admin_user)):
    from ..services.translate import list_jobs, start_job
    if body.mode not in ("skip", "overwrite"):
        raise HTTPException(400, "mode must be skip or overwrite")
    if not body.edition_ids:
        raise HTTPException(400, "edition_ids required")
    if any(j["status"] == "running" for j in list_jobs()):
        raise HTTPException(409, "another translation job is already running")
    job_id = start_job(body.edition_ids, body.lang, body.mode,
                       limit=body.limit, started_by=user["email"])
    return {"job_id": job_id}


@router.get("/translations/jobs/{job_id}")
def translation_job_status(job_id: str, user: dict = Depends(admin_user)):
    from ..services.translate import job_status
    j = job_status(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j


@router.post("/translations/jobs/{job_id}/cancel")
def cancel_translation_job(job_id: str, user: dict = Depends(admin_user)):
    from ..services.translate import cancel_job
    if not cancel_job(job_id):
        raise HTTPException(404, "no running job with this id")
    return {"cancelled": job_id}


class ReviewBody(BaseModel):
    obj_id: int
    lang: str = "en"
    action: str                 # approve | edit | reject
    text: str | None = None


@router.post("/translations/review")
def review_translation(body: ReviewBody, user: dict = Depends(admin_user)):
    with db() as conn:
        if body.action == "approve":
            row = conn.execute("""
                UPDATE translations SET status='approved', reviewed_by=%s, updated_at=now()
                WHERE obj_type='passage' AND obj_id=%s AND field='text' AND lang=%s
                RETURNING obj_id
            """, (user["email"], body.obj_id, body.lang)).fetchone()
        elif body.action == "edit":
            if not body.text:
                raise HTTPException(400, "text required for edit")
            row = conn.execute("""
                UPDATE translations SET text=%s, status='reviewed', source='human',
                       reviewed_by=%s, updated_at=now()
                WHERE obj_type='passage' AND obj_id=%s AND field='text' AND lang=%s
                RETURNING obj_id
            """, (body.text, user["email"], body.obj_id, body.lang)).fetchone()
        elif body.action == "reject":
            row = conn.execute("""
                DELETE FROM translations
                WHERE obj_type='passage' AND obj_id=%s AND field='text' AND lang=%s
                RETURNING obj_id
            """, (body.obj_id, body.lang)).fetchone()
        else:
            raise HTTPException(400, "action must be approve|edit|reject")
        conn.commit()
    if not row:
        raise HTTPException(404, "translation not found")
    return {"ok": True, "action": body.action, "obj_id": body.obj_id}
