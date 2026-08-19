"""Parity checks: unified Postgres counts vs the SQLite sources (ARCH §16 Phase 1)."""
import sqlite3

from db import SOURCES, connect


def main() -> None:
    ok = True
    with connect() as pg:
        sq = sqlite3.connect(SOURCES["hadith"])
        checks = [
            ("sunna editions", sq.execute("SELECT COUNT(*) FROM books").fetchone()[0],
             pg.execute("SELECT COUNT(*) FROM editions WHERE source='sunna'").fetchone()[0]),
            ("sunna passages", sq.execute("SELECT COUNT(*) FROM matn WHERE main_id IS NOT NULL").fetchone()[0],
             pg.execute("SELECT COUNT(*) FROM passages WHERE source='sunna'").fetchone()[0]),
            ("sunna toc", sq.execute("SELECT COUNT(*) FROM toc").fetchone()[0],
             pg.execute("SELECT COUNT(t.*) FROM toc_nodes t JOIN editions e USING (edition_id) WHERE e.source='sunna'").fetchone()[0]),
            ("subjects", sq.execute("SELECT COUNT(*) FROM subjects").fetchone()[0],
             pg.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]),
        ]
        sq2 = sqlite3.connect(SOURCES["alshamela"])
        checks += [
            ("shamela editions", sq2.execute("SELECT COUNT(*) FROM books").fetchone()[0],
             pg.execute("SELECT COUNT(*) FROM editions WHERE source='shamela'").fetchone()[0]),
            ("shamela passages", sq2.execute("SELECT COUNT(*) FROM pages").fetchone()[0],
             pg.execute("SELECT COUNT(*) FROM passages WHERE source='shamela'").fetchone()[0]),
        ]
        sq3 = sqlite3.connect(SOURCES["alifta"])
        checks += [
            ("alifta passages", sq3.execute("SELECT COUNT(*) FROM pages").fetchone()[0],
             pg.execute("SELECT COUNT(*) FROM passages WHERE source='alifta'").fetchone()[0]),
        ]
        links = pg.execute("SELECT COUNT(*) FROM subject_links").fetchone()[0]
        src_links = sq.execute("SELECT COUNT(DISTINCT subject_id || ':' || book_id || ':' || main_id) FROM subject_hits").fetchone()[0]

    print(f"{'check':22} {'source':>10} {'postgres':>10}")
    for name, a, b in checks:
        flag = "OK " if a == b else "DIFF"
        if a != b:
            ok = False
        print(f"{name:22} {a:>10} {b:>10}  {flag}")
    print(f"{'subject_links':22} {src_links:>10} {links:>10}  {'OK ' if links <= src_links else 'DIFF'} (deduped)")
    print("parity:", "PASS" if ok else "CHECK DIFFS ABOVE")


if __name__ == "__main__":
    main()
