"""Book Embedding Management job runner (§7.4).

Manual, incremental, idempotent: embedding_jobs (Postgres) is the ledger keyed
(passage_id, chunk_no) with content_hash; the Redis key encodes the same
identity, so duplicates are structurally impossible. Jobs run in a background
thread; progress is polled from the registry + ledger."""
import hashlib
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from ..db import pool
from .embeddings import chunk_text, embed_texts
from .vector import ensure_index, write_vector

BATCH = 64
_jobs: dict[str, dict[str, Any]] = {}          # in-memory registry (single process)
_lock = threading.Lock()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def job_status(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def list_jobs() -> list[dict]:
    return sorted(_jobs.values(), key=lambda j: j["started_at"], reverse=True)


def cancel_job(job_id: str) -> bool:
    j = _jobs.get(job_id)
    if j and j["status"] == "running":
        j["cancel"] = True
        return True
    return False


def coverage(conn) -> list[dict]:
    """Per-edition coverage table for the management screen."""
    return conn.execute("""
        SELECT e.edition_id, e.source, e.title_ar, e.book_type, e.passage_count,
               w.title_ar AS work_title, w.kind AS work_kind,
               coalesce(j.chunks, 0)   AS chunks_embedded,
               coalesce(j.failed, 0)   AS chunks_failed,
               coalesce(j.passages, 0) AS passages_embedded,
               j.last_run,
               coalesce(t.chars, 0)    AS total_chars
        FROM editions e
        JOIN works w USING (work_id)
        LEFT JOIN LATERAL (
            SELECT count(*) FILTER (WHERE status='embedded') AS chunks,
                   count(*) FILTER (WHERE status='failed')   AS failed,
                   count(DISTINCT passage_id) FILTER (WHERE status='embedded') AS passages,
                   max(embedded_at) AS last_run
            FROM embedding_jobs je WHERE je.edition_id = e.edition_id
        ) j ON true
        LEFT JOIN LATERAL (
            SELECT sum(length(text_raw))::bigint AS chars
            FROM passages p WHERE p.edition_id = e.edition_id
        ) t ON true
        ORDER BY w.kind, e.edition_id
    """).fetchall()


def start_job(edition_ids: list[int], mode: str = "skip", started_by: str = "") -> str:
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "job_id": job_id, "edition_ids": edition_ids, "mode": mode,
        "status": "running", "done_chunks": 0, "total_chunks": None,
        "done_passages": 0, "errors": 0, "cancel": False,
        "started_by": started_by,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None, "error": None, "current_edition": None,
    }
    t = threading.Thread(target=_run, args=(job_id,), daemon=True)
    t.start()
    return job_id


def _run(job_id: str) -> None:
    j = _jobs[job_id]
    try:
        ensure_index()
        for edition_id in j["edition_ids"]:
            if j["cancel"]:
                break
            j["current_edition"] = edition_id
            _embed_edition(j, edition_id)
        j["status"] = "cancelled" if j["cancel"] else "done"
    except Exception as e:  # surfaced to the UI; ledger allows clean resume
        j["status"] = "failed"
        j["error"] = f"{type(e).__name__}: {e}"
    finally:
        j["finished_at"] = datetime.now(timezone.utc).isoformat()


def _embed_edition(j: dict, edition_id: int) -> None:
    overwrite = j["mode"] == "overwrite"
    with pool.connection() as conn:
        rows = conn.execute("""
            SELECT p.passage_id, p.text_raw, p.kind, p.hadith_num, p.source,
                   w.work_id
            FROM passages p
            JOIN editions e USING (edition_id)
            JOIN works w USING (work_id)
            WHERE p.edition_id=%s ORDER BY p.seq
        """, (edition_id,)).fetchall()
        ledger = {
            (r["passage_id"], r["chunk_no"]): r["content_hash"]
            for r in conn.execute(
                "SELECT passage_id, chunk_no, content_hash FROM embedding_jobs "
                "WHERE edition_id=%s AND status='embedded'", (edition_id,)).fetchall()
        }

    # build the work list: (passage_row, chunk_no, chunk_text, hash)
    todo = []
    for r in rows:
        for chunk_no, chunk in enumerate(chunk_text(r["text_raw"])):
            h = content_hash(chunk)
            if not overwrite and ledger.get((r["passage_id"], chunk_no)) == h:
                continue
            todo.append((r, chunk_no, chunk, h))
    if j["total_chunks"] is None:
        j["total_chunks"] = len(todo)
    else:
        j["total_chunks"] += len(todo)

    for i in range(0, len(todo), BATCH):
        if j["cancel"]:
            return
        batch = todo[i:i + BATCH]
        try:
            vecs = embed_texts([c for (_, _, c, _) in batch])
        except Exception:
            j["errors"] += len(batch)
            _mark(edition_id, batch, "failed")
            continue
        for (r, chunk_no, _chunk, h), vec in zip(batch, vecs):
            write_vector(edition_id, r["passage_id"], chunk_no, vec,
                         work_id=r["work_id"], kind=r["kind"], source=r["source"],
                         hadith_num=r["hadith_num"], content_hash=h)
        _mark(edition_id, batch, "embedded")
        j["done_chunks"] += len(batch)
        j["done_passages"] = len({b[0]["passage_id"] for b in todo[:i + BATCH]})
        time.sleep(0.2)          # gentle rate limiting


def _mark(edition_id: int, batch: list, status: str) -> None:
    with pool.connection() as conn:
        conn.cursor().executemany("""
            INSERT INTO embedding_jobs (passage_id, chunk_no, edition_id, content_hash,
                                        status, embedded_at)
            VALUES (%s,%s,%s,%s,%s, now())
            ON CONFLICT (passage_id, chunk_no)
            DO UPDATE SET content_hash=EXCLUDED.content_hash, status=EXCLUDED.status,
                          embedded_at=now()
        """, [(r["passage_id"], chunk_no, edition_id, h, status)
              for (r, chunk_no, _c, h) in batch])
        conn.commit()
