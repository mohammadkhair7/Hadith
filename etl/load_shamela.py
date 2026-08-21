"""Load alshamela.db (Al-Maktaba Al-Shamela) into the unified schema.

Each Shamela book becomes an edition attached to the *same work* as its
hadith.db counterpart (via books.hadith_book_id), so the reader can offer an
edition switcher and the compare view can diff the two.
"""
import json
import sqlite3

from db import SOURCES, connect
from load_sunna import state_done, state_mark
from normalize import normalize_arabic


def main() -> None:
    sq = sqlite3.connect(SOURCES["alshamela"])
    with connect() as pg:
        books = sq.execute(
            "SELECT hadith_book_id, archive, bkid, name, auth, category, "
            "pages_expected, pages_loaded FROM books"
        ).fetchall()
        for hbid, archive, bkid, name, auth, category, expected, loaded in books:
            step = f"shamela_book_{bkid}"
            if state_done(pg, step):
                continue
            # find (or create) the work
            work_id = None
            if hbid is not None:
                row = pg.execute(
                    "SELECT work_id FROM editions WHERE source='sunna' AND source_book_id=%s",
                    (hbid,),
                ).fetchone()
                work_id = row[0] if row else None
            if work_id is None:
                work_id = pg.execute(
                    "INSERT INTO works (title_ar, title_norm, author_ar, author_norm, kind) "
                    "VALUES (%s,%s,%s,%s,'other') RETURNING work_id",
                    (name, normalize_arabic(name), auth, normalize_arabic(auth or "")),
                ).fetchone()[0]
            else:
                pg.execute(
                    "UPDATE works SET author_ar=COALESCE(author_ar,%s), "
                    "author_norm=COALESCE(author_norm,%s) WHERE work_id=%s",
                    (auth, normalize_arabic(auth or ""), work_id),
                )
            row = pg.execute(
                "SELECT edition_id FROM editions WHERE source='shamela' AND source_book_id=%s",
                (bkid,),
            ).fetchone()
            if row:
                edition_id = row[0]
            else:
                edition_id = pg.execute(
                    "INSERT INTO editions (work_id, source, source_book_id, title_ar, book_type, meta) "
                    "VALUES (%s,'shamela',%s,%s,'page-archive',%s) RETURNING edition_id",
                    (work_id, bkid, name,
                     json.dumps({"archive": archive, "author": auth, "category": category,
                                 "pages_expected": expected, "pages_loaded": loaded},
                                ensure_ascii=False)),
                ).fetchone()[0]

            pg.execute("DELETE FROM passages WHERE edition_id=%s", (edition_id,))
            n = 0
            with pg.cursor() as cur:
                with cur.copy(
                    "COPY passages (edition_id, source, source_page_id, seq, kind, hadith_num, "
                    "part, page, text_raw, text_norm, meta) FROM STDIN"
                ) as cp:
                    for seq, (page_id, part, page, hno, sora, aya, nass) in enumerate(
                        sq.execute(
                            "SELECT page_id, part, page, hno, sora, aya, nass "
                            "FROM pages WHERE bkid=? ORDER BY page_id",
                            (bkid,),
                        )
                    ):
                        # shamela uses bare \r as line separator; use real newlines
                        nass = (nass or "").replace("\r", "\n")
                        meta = {}
                        if hno:
                            meta["hno"] = hno
                        if sora:
                            meta["sora"] = sora
                        if aya:
                            meta["aya"] = aya
                        cp.write_row((
                            edition_id, "shamela", page_id, seq, "page",
                            str(hno) if hno else None, part, page,
                            nass, normalize_arabic(nass),
                            json.dumps(meta, ensure_ascii=False),
                        ))
                        n += 1
            pg.execute("UPDATE editions SET passage_count=%s WHERE edition_id=%s", (n, edition_id))
            state_mark(pg, step, detail={"passages": n})
            pg.commit()
            print(f"[shamela] bkid {bkid} ({name[:30]}): {n} pages")
    print("[shamela] done")


if __name__ == "__main__":
    main()
