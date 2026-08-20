"""Replace the Shamela Sahih al-Bukhari edition (bkid 32027, 12,530 crawled
pages, no tashkeel) with the clean Dar al-Sha'b export (7,636 pages, fully
vocalized, Fath al-Bari numbering 1..7563 validated complete by
ops/format_bukhari_csv.py).

The edition has no dependent rows (chains/annotations/embeddings/TOC), so this
is a pure passages swap keeping the same edition_id. Runs against DATABASE_URL,
so the same script serves local and Railway.
"""
import csv
import json
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "etl"))
sys.stdout.reconfigure(encoding="utf-8")
from normalize import normalize_arabic  # noqa: E402

CSV_PATH = Path(r"E:\Quran Computing Institute\Hadith.chat\40343-al-bukhari-formatted.csv")
SHAMELA_BKID = 32027


def main() -> None:
    import os
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")

    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"csv rows: {len(rows)}")

    with psycopg.connect(url) as conn:
        ed = conn.execute(
            "SELECT edition_id, passage_count FROM editions "
            "WHERE source='shamela' AND source_book_id=%s", (SHAMELA_BKID,),
        ).fetchone()
        if not ed:
            sys.exit("shamela bukhari edition not found")
        edition_id, old_count = ed
        print(f"edition_id={edition_id} old passages={old_count}")

        # safety: refuse if dependents exist (they don't locally/remotely today)
        dep = conn.execute(
            "SELECT count(*) FROM isnad_chains c JOIN passages p USING (passage_id) "
            "WHERE p.edition_id=%s", (edition_id,)).fetchone()[0]
        dep += conn.execute(
            "SELECT count(*) FROM passage_annotations a JOIN passages p USING (passage_id) "
            "WHERE p.edition_id=%s", (edition_id,)).fetchone()[0]
        if dep:
            sys.exit(f"edition {edition_id} has {dep} dependent rows; aborting")

        conn.execute("DELETE FROM passages WHERE edition_id=%s", (edition_id,))
        n = 0
        with conn.cursor() as cur:
            with cur.copy(
                "COPY passages (edition_id, source, source_page_id, seq, kind, "
                "hadith_num, part, page, text_raw, text_norm, meta) FROM STDIN"
            ) as cp:
                for seq, r in enumerate(rows):
                    text = r["nass"]
                    hno = r["hno"].strip() or None
                    meta = {}
                    if hno:
                        meta["hno_list"] = [int(x) for x in hno.split(",")]
                    cp.write_row((
                        edition_id, "shamela", int(r["id"]), seq, "page",
                        hno, r["part"], r["page"],
                        text, normalize_arabic(text),
                        json.dumps(meta, ensure_ascii=False),
                    ))
                    n += 1
        conn.execute(
            "UPDATE editions SET passage_count=%s, "
            "meta = meta || %s::jsonb WHERE edition_id=%s",
            (n, json.dumps({
                "replaced": "dar-alshaab-1987",
                "replaced_from": "40343-al-bukhari-formatted.csv",
                "numbering": "fath-albari-1-7563",
                "pages_expected": n, "pages_loaded": n,
            }), edition_id),
        )
        conn.execute(
            "UPDATE etl_state SET detail = detail || %s::jsonb "
            "WHERE step=%s",
            (json.dumps({"replaced_by": "ops/replace_shamela_bukhari.py", "passages": n}),
             f"shamela_book_{SHAMELA_BKID}"),
        )
        conn.commit()
        print(f"inserted {n} passages")

        got = conn.execute(
            "SELECT count(*), count(hadith_num) FROM passages WHERE edition_id=%s",
            (edition_id,)).fetchone()
        print(f"verify: passages={got[0]} with hadith_num={got[1]}")
        sample = conn.execute(
            "SELECT seq, hadith_num, page, part, left(text_raw, 90) "
            "FROM passages WHERE edition_id=%s AND hadith_num='1' ", (edition_id,)
        ).fetchall()
        for s in sample:
            print("  ", s)


if __name__ == "__main__":
    main()
