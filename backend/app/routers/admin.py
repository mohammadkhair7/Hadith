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


# --- Book Embedding Management (§7.4) ---------------------------------------

class EmbJobBody(BaseModel):
    edition_ids: list[int]
    mode: str = "skip"          # skip | overwrite


@router.get("/embeddings/coverage")
def embeddings_coverage(user: dict = Depends(admin_user)):
    from ..services.embed_jobs import coverage, list_jobs
    with db() as conn:
        rows = coverage(conn)
    # rough cost estimate: Arabic ≈ 2.5 chars/token
    for r in rows:
        r["est_tokens_total"] = int((r["total_chars"] or 0) / 2.5)
    return {"editions": rows, "jobs": list_jobs()}


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
