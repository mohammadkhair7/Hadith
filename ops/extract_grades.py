"""Extract hadith grades (درجات) stated in the text itself — the classical
in-book judgements (الترمذي: «هذا حديث حسن صحيح», الحاكم: «صحيح على شرط
الشيخين» / «صحيح الإسناد ولم يخرجاه», «إسناده حسن/ضعيف»...) — into
hadith_grades with source='matn-text'. Existing rows (loaded from hadith.db)
are authoritative and never overwritten. Idempotent; DATABASE_URL-driven."""
import os
import re
import sys
from collections import Counter

import psycopg

sys.stdout.reconfigure(encoding="utf-8")

# priority order: first match wins (most specific first)
RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"حديث حسن صحيح غريب"), "حسن صحيح غريب", "hasan_sahih"),
    (re.compile(r"هذا حديث حسن صحيح|حديث حسن صحيح"), "حسن صحيح", "hasan_sahih"),
    (re.compile(r"صحيح علي شرط الشيخين"), "صحيح على شرط الشيخين", "sahih"),
    (re.compile(r"صحيح علي شرط (البخاري|مسلم)"), "صحيح على شرط أحدهما", "sahih"),
    (re.compile(r"صحيح الاسناد ولم يخرجاه"), "صحيح الإسناد", "sahih"),
    (re.compile(r"هذا حديث صحيح|اسناده صحيح"), "صحيح", "sahih"),
    (re.compile(r"هذا حديث حسن غريب"), "حسن غريب", "hasan"),
    (re.compile(r"هذا حديث حسن|اسناده حسن"), "حسن", "hasan"),
    (re.compile(r"هذا حديث ضعيف|اسناده ضعيف"), "ضعيف", "daif"),
    (re.compile(r"هذا حديث منكر"), "منكر", "daif"),
    (re.compile(r"هذا حديث غريب"), "غريب", "gharib"),
]


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    with psycopg.connect(url) as conn:
        conn.execute("DELETE FROM hadith_grades WHERE source='matn-text'")
        rows = conn.execute("""
            SELECT passage_id, text_norm FROM passages
            WHERE kind='unit' AND (
                text_norm LIKE '%هذا حديث %' OR text_norm LIKE '%اسناده %'
                OR text_norm LIKE '%صحيح علي شرط%' OR text_norm LIKE '%ولم يخرجاه%')
        """).fetchall()
        print(f"candidate passages: {len(rows)}")
        dist: Counter = Counter()
        buf = []
        for pid, tn in rows:
            for rx, ar, norm in RULES:
                if rx.search(tn):
                    buf.append((pid, ar, norm))
                    dist[norm] += 1
                    break
        with conn.cursor() as cur:
            cur.executemany("""
                INSERT INTO hadith_grades (passage_id, grade_ar, grade_norm, source)
                VALUES (%s, %s, %s, 'matn-text')
                ON CONFLICT (passage_id) DO NOTHING
            """, buf)
        conn.execute("ANALYZE hadith_grades")
        conn.commit()
        total = conn.execute("SELECT count(*) FROM hadith_grades").fetchone()[0]
    print("extracted:", dict(dist))
    print("hadith_grades total now:", total)


if __name__ == "__main__":
    main()
