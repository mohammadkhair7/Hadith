"""One-shot curation: merge duplicate عائشة أم المؤمنين narrator nodes into the
canonical node (the bare «عاءشه», id resolved by highest mentions).

Only names of the form «عاءشه + honorifics/punctuation/trailing-verb artifacts»
are merged (رضي الله عنها، ام المءمنين، زوج النبي، انها/قالت/تقول/مثله…).
Anything with nasab or other tokens (بنت طلحه، بنت سعد، وابن عباس، عروه ان…)
is left untouched — those are other people or compound extraction errors.

Run with DATABASE_URL pointing at the target database.
Uses backend/app/services/narrator_admin.merge_narrators (audited).
"""
import os
import re
import sys

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.services.narrator_admin import ensure_tables, merge_narrators  # noqa: E402

AISHA = "عاءشه"
ALLOW = {
    "رضي", "الله", "عنها", "تعالي",
    "ام", "المءمنين", "زوج", "النبي", "صلي", "عليه", "وسلم",
    "انها", "قالت", "تقول", "قال", "مثله", "بمثله", "نحوه", "بنحوه",
    "سءلت", "سالت", "و", "ها",
}
_PUNCT = re.compile(r"[^\u0600-\u06ff]+")   # strip everything non-Arabic


def is_umm_almuminin_variant(norm: str) -> bool:
    toks = [t for t in (_PUNCT.sub(" ", norm)).split() if t]
    if not toks or toks[0] != AISHA:
        return False
    return all(t in ALLOW for t in toks[1:])


def main() -> None:
    conn = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
    ensure_tables(conn)
    rows = conn.execute("""
        SELECT n.narrator_id, n.canonical_ar, n.canonical_norm,
               (SELECT count(*) FROM isnad_links l
                WHERE l.narrator_id = n.narrator_id) AS mentions
        FROM narrators n
        WHERE n.canonical_norm LIKE %s
        ORDER BY mentions DESC
    """, (AISHA + "%",)).fetchall()
    variants = [r for r in rows if is_umm_almuminin_variant(r["canonical_norm"])]
    if not variants:
        print("nothing to merge")
        return
    target = variants[0]
    sources = variants[1:]
    print(f"target: #{target['narrator_id']} «{target['canonical_ar']}» "
          f"({target['mentions']} mentions)")
    print(f"merging {len(sources)} duplicates "
          f"(+{sum(s['mentions'] for s in sources)} mentions):")
    for s in sources:
        print(f"  #{s['narrator_id']:>6} {s['mentions']:>5}  {s['canonical_ar']}")
    skipped = [r for r in rows if not is_umm_almuminin_variant(r["canonical_norm"])]
    print(f"left untouched (other people / compounds): {len(skipped)}")

    r = merge_narrators(conn, target["narrator_id"],
                        [s["narrator_id"] for s in sources], "ops/merge_aisha")
    print("merge result:", r)
    after = conn.execute(
        "SELECT count(*) AS n FROM isnad_links WHERE narrator_id=%s",
        (target["narrator_id"],)).fetchone()["n"]
    print(f"target now has {after} mentions")
    conn.close()


if __name__ == "__main__":
    main()
