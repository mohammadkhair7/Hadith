import sqlite3

for name, path in [
    ("alifta", r"E:\Quran Computing Institute\Hadith.chat\Alifta.chat\data\alifta.db"),
    ("alshamela", r"E:\Quran Computing Institute\Hadith.chat\Al-Shamela\alshamela.db"),
]:
    db = sqlite3.connect(path)
    print(f"== {name} ==")
    for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        cols = ", ".join(c[1] for c in db.execute(f"PRAGMA table_info({t})"))
        n = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t} ({n}): {cols}")
    db.close()
