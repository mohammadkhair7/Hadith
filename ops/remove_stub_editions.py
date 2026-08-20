"""Remove truncated sunna 'stub' editions whose hadith.db source only has 1-2
matn units (verified: فتح المغيث book 83 = 1 unit, الجرح والتعديل book 61 = 2
units). The complete Shamela editions of the same works remain. Runs against
DATABASE_URL (local or Railway). Also clears any local Redis vectors."""
import os
import sys

import psycopg

sys.stdout.reconfigure(encoding="utf-8")

EDITION_IDS = [48, 55]  # sunna الجرح والتعديل (book 61), sunna فتح المغيث (book 83)


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    with psycopg.connect(url) as conn:
        for eid in EDITION_IDS:
            row = conn.execute(
                "SELECT source, title_ar, passage_count FROM editions WHERE edition_id=%s",
                (eid,),
            ).fetchone()
            if not row:
                print(f"edition {eid}: already gone")
                continue
            source, title, count = row
            if source != "sunna" or count > 2:
                sys.exit(f"edition {eid} unexpected: source={source} passages={count}")
            stats = {}
            for label, sql in [
                ("translations",
                 "DELETE FROM translations t USING passages p "
                 "WHERE t.obj_type='passage' AND t.obj_id=p.passage_id AND p.edition_id=%s"),
                ("grades",
                 "DELETE FROM hadith_grades g USING passages p "
                 "WHERE g.passage_id=p.passage_id AND p.edition_id=%s"),
                ("subject_links",
                 "DELETE FROM subject_links s USING passages p "
                 "WHERE s.passage_id=p.passage_id AND p.edition_id=%s"),
                ("annotations",
                 "DELETE FROM passage_annotations a USING passages p "
                 "WHERE a.passage_id=p.passage_id AND p.edition_id=%s"),
                ("embedding_jobs", "DELETE FROM embedding_jobs WHERE edition_id=%s"),
                ("isnad_links",
                 "DELETE FROM isnad_links l USING isnad_chains c, passages p "
                 "WHERE l.chain_id=c.chain_id AND c.passage_id=p.passage_id "
                 "AND p.edition_id=%s"),
                ("isnad_chains",
                 "DELETE FROM isnad_chains c USING passages p "
                 "WHERE c.passage_id=p.passage_id AND p.edition_id=%s"),
                ("toc_nodes", "DELETE FROM toc_nodes WHERE edition_id=%s"),
                ("passages", "DELETE FROM passages WHERE edition_id=%s"),
                ("editions", "DELETE FROM editions WHERE edition_id=%s"),
            ]:
                cur = conn.execute(sql, (eid,))
                stats[label] = cur.rowcount
            conn.commit()
            deleted = {k: v for k, v in stats.items() if v}
            print(f"edition {eid} ({title}): removed {deleted}")

    # local Redis vector cleanup (best effort; remote joins drop missing rows)
    try:
        import redis
        r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        for eid in EDITION_IDS:
            keys = list(r.scan_iter(f"ah:emb:{eid}:*", count=1000))
            if keys:
                r.delete(*keys)
            print(f"redis: edition {eid} -> {len(keys)} vector keys removed")
    except Exception as exc:  # redis optional
        print(f"redis cleanup skipped: {exc}")


if __name__ == "__main__":
    main()
