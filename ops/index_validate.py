"""§12.7 validation harness: run the rule indexing pipeline on Bukhari's FLAT
shamela pages and compare detected hadith numbers against the NATIVE sunna
per-hadith units. Reports number-detection precision/recall/F1.

    .venv\\Scripts\\python ops\\index_validate.py [shamela_edition_id sunna_edition_id]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Arabic-lib"))

from app.db import pool  # noqa: E402
from arabiclib.indexing import segment_units  # noqa: E402


def find_bukhari(conn) -> tuple[int, int]:
    row = conn.execute("""
        SELECT w.work_id,
               max(CASE WHEN e.source='shamela' THEN e.edition_id END) AS shamela_ed,
               max(CASE WHEN e.source='sunna'   THEN e.edition_id END) AS sunna_ed
        FROM works w JOIN editions e USING (work_id)
        WHERE w.title_norm LIKE '%صحيح البخاري%'
        GROUP BY w.work_id
        HAVING count(DISTINCT e.source) >= 2
        ORDER BY w.work_id LIMIT 1
    """).fetchone()
    if not row or not row["shamela_ed"] or not row["sunna_ed"]:
        raise SystemExit("no dual-source Bukhari found")
    return row["shamela_ed"], row["sunna_ed"]


def main() -> None:
    pool.open()
    with pool.connection() as conn:
        if len(sys.argv) >= 3:
            shamela_ed, sunna_ed = int(sys.argv[1]), int(sys.argv[2])
        else:
            shamela_ed, sunna_ed = find_bukhari(conn)
        print(f"shamela edition {shamela_ed} vs sunna edition {sunna_ed}")

        pages = conn.execute(
            "SELECT text_raw FROM passages WHERE edition_id=%s ORDER BY seq",
            (shamela_ed,)).fetchall()
        native = conn.execute("""
            SELECT hadith_num FROM passages
            WHERE edition_id=%s AND kind='unit' AND hadith_num IS NOT NULL
        """, (sunna_ed,)).fetchall()

    truth: set[int] = set()
    for r in native:
        h = r["hadith_num"].strip()
        if h.isdigit():
            truth.add(int(h))
    print(f"native units with numeric hadith_num: {len(truth)}")

    detected: set[int] = set()
    for r in pages:
        for u in segment_units(r["text_raw"]):
            if u.hadith_num:
                detected.add(u.hadith_num)
    print(f"detected numbers on flat pages: {len(detected)}")

    tp = len(detected & truth)
    precision = tp / len(detected) if detected else 0
    recall = tp / len(truth) if truth else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    print(f"precision={precision:.3f} recall={recall:.3f} F1={f1:.3f}")
    pool.close()


if __name__ == "__main__":
    main()
