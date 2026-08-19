"""Re-test the waterfall with matn extraction on real Bukhari hadith units."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import pool
from app.services.translate import translate_passage

pool.open()
with pool.connection() as conn:
    rows = conn.execute("""
        SELECT passage_id, hadith_num FROM passages
        WHERE edition_id=1 AND kind='unit' AND hadith_num IS NOT NULL
        ORDER BY seq LIMIT 6
    """).fetchall()

kal = gem = 0
for r in rows:
    with pool.connection() as conn:
        res = translate_passage(conn, r["passage_id"], "en", overwrite=True)
    if res["source"] == "kalimat":
        kal += 1
    else:
        gem += 1
    print(f"#{r['hadith_num']}: {res['source']}")
print(f"\nkalimat {kal} / gemini {gem}")
pool.close()
