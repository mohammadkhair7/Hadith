"""One-shot inventory of the three source databases for the architecture doc."""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

print("== hadith.db ==")
h = sqlite3.connect(ROOT / "data" / "hadith.db")
for row in h.execute(
    "SELECT COALESCE(book_type,'matn'), COUNT(*) FROM books GROUP BY 1"
):
    print("  books", row)
print("  matn rows:", h.execute("SELECT COUNT(*) FROM matn").fetchone()[0])
print("  matn with html:", h.execute("SELECT COUNT(*) FROM matn WHERE html IS NOT NULL").fetchone()[0])
print("  total text chars:", h.execute("SELECT SUM(LENGTH(text_plain)) FROM matn").fetchone()[0])
print("  toc rows:", h.execute("SELECT COUNT(*) FROM toc").fetchone()[0])
for t in ("subjects", "subject_hits"):
    try:
        print(f"  {t}:", h.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    except sqlite3.OperationalError as e:
        print(f"  {t}: n/a ({e})")
print("  tables:", [r[0] for r in h.execute("SELECT name FROM sqlite_master WHERE type='table'")])

print("\n== alifta.db ==")
a = sqlite3.connect(ROOT / "Alifta.chat" / "data" / "alifta.db")
print("  tables:", [r[0] for r in a.execute("SELECT name FROM sqlite_master WHERE type='table'")])
print("  pages:", a.execute("SELECT COUNT(*) FROM pages").fetchone()[0])
print("  total html chars:", a.execute("SELECT SUM(LENGTH(content_html)) FROM pages").fetchone()[0])

print("\n== alshamela.db ==")
s = sqlite3.connect(ROOT / "Al-Shamela" / "alshamela.db")
print("  books:", s.execute("SELECT COUNT(*) FROM books").fetchone()[0])
print("  pages:", s.execute("SELECT COUNT(*) FROM pages").fetchone()[0])
print("  total text chars:", s.execute("SELECT SUM(LENGTH(nass)) FROM pages").fetchone()[0])
print("  gap_candidates:", s.execute("SELECT COUNT(*) FROM gap_candidates").fetchone()[0])

print("\n== file sizes ==")
for p in (ROOT / "data" / "hadith.db", ROOT / "Alifta.chat" / "data" / "alifta.db",
          ROOT / "Al-Shamela" / "alshamela.db"):
    print(f"  {p.name}: {p.stat().st_size/1e6:.0f} MB")
