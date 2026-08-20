"""Seed hadith_grades:
1. book-convention: every unit in the Sahihain (صحيح البخاري / صحيح مسلم) plus
   the explicitly-sahih compilations (صحيح ابن خزيمة is NOT auto-graded — only
   the two Sahihs carry scholarly consensus) -> sahih.
2. kalimat: harvest grade_en stored in translations.meta for passages that
   matched an authenticated English translation.
Idempotent: re-running upserts. Kalimat never overwrites book-convention.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import pool

SAHIH_BOOKS = ["صحيح البخاري", "صحيح مسلم"]

GRADE_MAP = {
    "sahih": ("صحيح", "sahih"),
    "hasan": ("حسن", "hasan"),
    "daif": ("ضعيف", "daif"),
    "da'if": ("ضعيف", "daif"),
    "maqbul": ("مقبول", "maqbul"),
    "mawdu": ("موضوع", "mawdu"),
    "maudu": ("موضوع", "mawdu"),
}


def norm_grade_en(grade_en: str) -> tuple[str, str] | None:
    key = (grade_en or "").split("-")[0].split("(")[0].strip().lower()
    for prefix, mapped in GRADE_MAP.items():
        if key.startswith(prefix):
            return mapped
    return ("", "other") if key else None


def main() -> None:
    pool.open()
    with pool.connection() as conn:
        n = conn.execute("""
            INSERT INTO hadith_grades (passage_id, grade_ar, grade_norm, source)
            SELECT p.passage_id, 'صحيح', 'sahih', 'book-convention'
            FROM passages p
            JOIN editions e USING (edition_id)
            JOIN works w USING (work_id)
            WHERE w.kind='matn' AND w.title_ar = ANY(%s) AND p.kind='unit'
            ON CONFLICT (passage_id) DO NOTHING
        """, (SAHIH_BOOKS,)).rowcount
        print(f"book-convention sahih: {n}")

        rows = conn.execute("""
            SELECT obj_id AS passage_id, meta FROM translations
            WHERE obj_type='passage' AND source='kalimat' AND meta ? 'grade_en'
        """).fetchall()
        harvested = 0
        for r in rows:
            meta = r["meta"] if isinstance(r["meta"], dict) else json.loads(r["meta"])
            mapped = norm_grade_en(meta.get("grade_en", ""))
            if not mapped:
                continue
            conn.execute("""
                INSERT INTO hadith_grades (passage_id, grade_ar, grade_norm, source, meta)
                VALUES (%s, %s, %s, 'kalimat', %s)
                ON CONFLICT (passage_id) DO UPDATE
                    SET grade_ar=EXCLUDED.grade_ar, grade_norm=EXCLUDED.grade_norm,
                        meta=EXCLUDED.meta, updated_at=now()
                    WHERE hadith_grades.source NOT IN ('book-convention', 'manual')
            """, (r["passage_id"], mapped[0], mapped[1],
                  json.dumps({"grade_en": meta.get("grade_en"),
                              "kalimat_id": meta.get("kalimat_id")})))
            harvested += 1
        conn.commit()
        print(f"kalimat harvested: {harvested}")
        dist = conn.execute(
            "SELECT grade_norm, count(*) AS n FROM hadith_grades GROUP BY 1 ORDER BY n DESC"
        ).fetchall()
        print("distribution:", [(d["grade_norm"], d["n"]) for d in dist])
    pool.close()


if __name__ == "__main__":
    main()
