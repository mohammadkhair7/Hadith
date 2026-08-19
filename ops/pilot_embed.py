"""Phase 3 pilot (§7.3): embed the smallest matn book end-to-end and run a
semantic + hybrid search against it. Local CLI, run from AdvancedHadith/:

    .venv\\Scripts\\python ops\\pilot_embed.py [edition_id]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import pool  # noqa: E402
from app.services import embed_jobs  # noqa: E402
from app.services.vector import ensure_index, vector_search, hybrid_search  # noqa: E402


def main() -> None:
    pool.open()
    with pool.connection() as conn:
        if len(sys.argv) > 1:
            edition_id = int(sys.argv[1])
        else:
            row = conn.execute("""
                SELECT e.edition_id, e.title_ar, e.passage_count
                FROM editions e JOIN works w USING (work_id)
                WHERE e.source='sunna' AND w.kind='matn' AND e.passage_count > 0
                ORDER BY e.passage_count LIMIT 1
            """).fetchone()
            edition_id = row["edition_id"]
            print(f"pilot edition {edition_id}: {row['title_ar']} "
                  f"({row['passage_count']} passages)")

    ensure_index()
    job_id = embed_jobs.start_job([edition_id], "skip", started_by="pilot-cli")
    while True:
        j = embed_jobs.job_status(job_id)
        print(f"  {j['status']}: {j['done_chunks']}/{j['total_chunks']} chunks, "
              f"errors={j['errors']}")
        if j["status"] != "running":
            break
        time.sleep(3)
    if j["status"] != "done":
        print("job did not finish cleanly:", j.get("error"))
        sys.exit(1)

    query = "فضل الصدقة على الفقراء"
    with pool.connection() as conn:
        sem = vector_search(conn, query, edition_id=edition_id, limit=5)
        print(f"\nsemantic «{query}» -> {sem['total']} hits, coverage {sem['coverage']}")
        for it in sem["items"]:
            print(f"  [{it['score']}] #{it['hadith_num']} {it['snippet'][:80]}…")
        hyb = hybrid_search(conn, query, edition_id=edition_id, limit=5)
        print(f"\nhybrid -> {hyb['total']} hits (keyword_total={hyb['keyword_total']})")
        for it in hyb["items"]:
            print(f"  [{it['score']}] #{it['hadith_num']} {it['snippet'][:80]}…")
    pool.close()


if __name__ == "__main__":
    main()
