"""Load hadith_struct.db (structural-metadata reference archive) into the
unified schema. RETIRED from the app 2026-08-20 (the archive is reference
notes, not a book — see ops/remove_alifta_edition.py); kept for provenance.

The archive is a small set of rendered pages; it becomes one work with one
edition, one passage per page (HTML preserved for the legacy-content reader).
"""
import json
import sqlite3

from db import SOURCES, connect
from load_sunna import state_done, state_mark
from normalize import normalize_arabic


def main() -> None:
    sq = sqlite3.connect(SOURCES["hadith_struct"])
    with connect() as pg:
        if state_done(pg, "hadith_struct_pages"):
            print("[hadith_struct] already loaded")
            return
        title = "أرشيف الرئاسة العامة للبحوث العلمية والإفتاء"
        row = pg.execute(
            "SELECT edition_id FROM editions WHERE source='hadith_struct' AND source_book_id=0"
        ).fetchone()
        if row:
            edition_id = row[0]
        else:
            work_id = pg.execute(
                "INSERT INTO works (title_ar, title_norm, kind) VALUES (%s,%s,'service') RETURNING work_id",
                (title, normalize_arabic(title)),
            ).fetchone()[0]
            edition_id = pg.execute(
                "INSERT INTO editions (work_id, source, source_book_id, title_ar, book_type) "
                "VALUES (%s,'hadith_struct',0,%s,'page-archive') RETURNING edition_id",
                (work_id, title),
            ).fetchone()[0]

        pg.execute("DELETE FROM passages WHERE edition_id=%s", (edition_id,))
        n = 0
        with pg.cursor() as cur:
            with cur.copy(
                "COPY passages (edition_id, source, source_page_id, seq, kind, "
                "text_raw, text_norm, html, meta) FROM STDIN"
            ) as cp:
                for seq, (slug, url, section, ord_, ptitle, text_plain, text_norm, content_html) in enumerate(
                    sq.execute(
                        "SELECT slug, url, section, ord, title, text_plain, text_norm, content_html "
                        "FROM pages ORDER BY ord, slug"
                    )
                ):
                    text_raw = text_plain or ""
                    cp.write_row((
                        edition_id, "hadith_struct", seq, seq, "page",
                        text_raw, normalize_arabic(text_raw), content_html,
                        json.dumps({"slug": slug, "url": url, "section": section,
                                    "title": ptitle}, ensure_ascii=False),
                    ))
                    n += 1
        pg.execute("UPDATE editions SET passage_count=%s WHERE edition_id=%s", (n, edition_id))
        state_mark(pg, "hadith_struct_pages", detail={"passages": n})
        pg.commit()
        print(f"[hadith_struct] {n} pages loaded")


if __name__ == "__main__":
    main()
