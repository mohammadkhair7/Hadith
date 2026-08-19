"""Phase 7 waterfall smoke test: translate 3 Bukhari hadiths — expect Kalimat
hits (authenticated) for famous hadiths, Gemini fallback otherwise. Verifies
skip-idempotency on re-run."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import pool
from app.services.translate import kalimat_lookup, translate_passage

pool.open()
with pool.connection() as conn:
    rows = conn.execute("""
        SELECT passage_id, hadith_num, left(text_raw, 60) AS head, text_raw
        FROM passages WHERE edition_id=1 AND kind='unit' ORDER BY seq LIMIT 3
    """).fetchall()

# direct kalimat check on hadith #1
k = kalimat_lookup(rows[0]["text_raw"])
print("kalimat direct:", "HIT" if k else "MISS",
      (k["meta"] if k else ""))
if k:
    print("  en:", k["en_text"][:180])

for r in rows:
    with pool.connection() as conn:
        res = translate_passage(conn, r["passage_id"], "en")
    print(f"passage {r['passage_id']} (#{r['hadith_num']}): {res['source']} / {res['status']}")

# idempotency: re-run must skip
with pool.connection() as conn:
    res = translate_passage(conn, rows[0]["passage_id"], "en")
print("re-run:", res)

with pool.connection() as conn:
    stored = conn.execute("""
        SELECT obj_id, source, status, left(text, 150) AS text_head, meta
        FROM translations WHERE obj_type='passage' AND lang='en'
        ORDER BY obj_id LIMIT 5
    """).fetchall()
for s in stored:
    print(f"stored {s['obj_id']}: [{s['source']}/{s['status']}] {s['text_head']}")
pool.close()
