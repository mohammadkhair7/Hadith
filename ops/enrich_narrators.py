"""Narrator bio enrichment (رجال الحديث): match resolved narrators to their
entries in Taqrib al-Tahdhib (تقريب التهذيب, ibn Hajar) — the most structured
rijal book in the corpus — and extract death year (H), tabaqa (generation),
rijal grade (ثقة/صدوق/…), places (from nisba adjectives) and a bio snippet.

Results land on the `narrators` row: death_year_h, generation, bio_summary,
meta jsonb {tabaqa, tabaqa_label, rijal_grade, places, school, src_passage,
src_book, rijal_candidates}.

    .venv\\Scripts\\python ops\\enrich_narrators.py            # dry-run stats
    .venv\\Scripts\\python ops\\enrich_narrators.py --write
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import pool  # noqa: E402
from app.services.normalize import normalize_arabic  # noqa: E402

TAQRIB_TITLE = "تقريب التهذيب"

_JUNK = re.compile(r"AddHistory\([^)]*\)[^;]*;?|\[\d+/\d+\]")
_ENTRY = re.compile(r"^\s*(\d+)\s*-\s*(?:\[[^\]]{0,30}\]\s*)?(.+)$", re.S)

# -- Arabic word-number parsing (on normalized text) --------------------------
_UNITS = {normalize_arabic(k): v for k, v in {
    "واحد": 1, "واحدة": 1, "إحدى": 1, "اثنتين": 2, "اثنين": 2, "ثنتين": 2,
    "ثلاث": 3, "ثلاثة": 3, "أربع": 4, "أربعة": 4, "خمس": 5, "خمسة": 5,
    "ست": 6, "ستة": 6, "سبع": 7, "سبعة": 7, "ثمان": 8, "ثماني": 8,
    "ثمانية": 8, "تسع": 9, "تسعة": 9, "عشر": 10, "عشرة": 10,
}.items()}
_TENS = {normalize_arabic(k): v for k, v in {
    "عشرين": 20, "ثلاثين": 30, "أربعين": 40, "خمسين": 50, "ستين": 60,
    "سبعين": 70, "ثمانين": 80, "تسعين": 90,
}.items()}
_HUNDREDS = {normalize_arabic(k): v for k, v in {
    "مائة": 100, "المائة": 100, "مئة": 100, "ومائة": 100,
    "مائتين": 200, "المائتين": 200, "ومائتين": 200,
    "ثلاثمائة": 300, "وثلاثمائة": 300, "أربعمائة": 400, "خمسمائة": 500,
}.items()}


_ALT = re.compile(normalize_arabic("وقيل|قيل|أو ") + "|" + normalize_arabic("وله"))


def parse_year_words(txt_norm: str) -> tuple[int | None, bool]:
    """'خمس وثلاثين ومائة' -> (135, True). Second flag = century present.
    Alternate readings ('وقيل ...') are cut off before summing."""
    txt_norm = _ALT.split(txt_norm)[0]
    total, has_hundred = 0, False
    for w in txt_norm.replace("و", " و").split():
        w = w.strip().lstrip("و") or "و"
        if w in _HUNDREDS:
            total += _HUNDREDS[w]
            has_hundred = True
        elif w in _TENS:
            total += _TENS[w]
        elif w in _UNITS:
            total += _UNITS[w]
    m = re.search(r"\d{2,3}", txt_norm)
    if m and not total:
        return int(m.group()), True
    return (total if total else None), has_hundred


# Plausible death-year ranges (AH) per ibn Hajar tabaqa, used to recover the
# century Taqrib routinely omits ("مات سنة أربعين" in tabaqa 10 = 240).
_TABAQA_DEATH = {1: (1, 110), 2: (40, 105), 3: (60, 115), 4: (75, 125),
                 5: (95, 140), 6: (105, 155), 7: (120, 170), 8: (135, 190),
                 9: (160, 210), 10: (180, 230), 11: (195, 260), 12: (220, 290)}


def infer_century(year: int, tabaqa: int | None) -> int | None:
    if tabaqa not in _TABAQA_DEATH:
        return None
    lo, hi = _TABAQA_DEATH[tabaqa]
    fits = [year + c for c in (0, 100, 200) if lo <= year + c <= hi]
    return fits[0] if len(fits) == 1 else None


_DEATH = re.compile(normalize_arabic("(?:مات|توفي)") + r"\s+(?:في\s+)?"
                    + r"(?:علي\s+راس\s+)?" + normalize_arabic("سنة")
                    + r"?\s*([^.,،؛]{2,60})")
_RAS = re.compile(normalize_arabic("علي راس") + r"\s+(\S+)")

_GRADES = [normalize_arabic(g) for g in [
    "ثقة ثبت", "ثقة حافظ", "ثقة فقيه", "ثقة عابد", "ثقة", "صدوق يهم",
    "صدوق له أوهام", "صدوق ربما وهم", "صدوق", "مقبول", "لا بأس به",
    "لين الحديث", "ضعيف جدا", "ضعيف", "متروك", "مجهول الحال", "مجهول",
    "كذاب", "صحابي جليل", "صحابية", "صحابي",
]]
_TABAQA = {normalize_arabic(k): v for k, v in {
    "الأولى": 1, "الثانية عشرة": 12, "الحادية عشرة": 11, "العاشرة": 10,
    "التاسعة": 9, "الثامنة": 8, "السابعة": 7, "السادسة": 6, "الخامسة": 5,
    "الرابعة": 4, "الثالثة": 3, "الثانية": 2,
}.items()}
_TABAQA_RE = re.compile(normalize_arabic("من ال") + r"(\S+(?:\s+عشره)?)")
TABAQA_LABEL = {
    1: "صحابي", 2: "كبار التابعين", 3: "أوساط التابعين", 4: "أوساط التابعين",
    5: "صغار التابعين", 6: "عاصروا صغار التابعين", 7: "كبار أتباع التابعين",
    8: "أوساط أتباع التابعين", 9: "صغار أتباع التابعين",
    10: "كبار الآخذين عن تبع الأتباع", 11: "أوساط الآخذين عن تبع الأتباع",
    12: "صغار الآخذين عن تبع الأتباع",
}


def generation_of(tabaqa: int) -> str:
    if tabaqa == 1:
        return "صحابي"
    if tabaqa <= 5:
        return "تابعي"
    if tabaqa <= 9:
        return "من أتباع التابعين"
    return "من تبع الأتباع"


_NISBA_CITY = {normalize_arabic(k): v for k, v in {
    "المدني": "المدينة المنورة", "المكي": "مكة المكرمة", "الكوفي": "الكوفة",
    "البصري": "البصرة", "الشامي": "الشام", "الدمشقي": "دمشق", "الحمصي": "حمص",
    "المصري": "مصر", "البغدادي": "بغداد", "الواسطي": "واسط",
    "الصنعاني": "صنعاء", "اليماني": "اليمن", "المروزي": "مرو",
    "النيسابوري": "نيسابور", "الرازي": "الري", "الهروي": "هراة",
    "البلخي": "بلخ", "الخراساني": "خراسان", "البخاري": "بخارى",
    "الترمذي": "ترمذ", "الأصبهاني": "أصبهان", "الطائفي": "الطائف",
    "السجستاني": "سجستان", "الأيلي": "أيلة", "الحراني": "حران",
    "الرقي": "الرقة", "الموصلي": "الموصل", "الطبري": "طبرستان",
    "القزويني": "قزوين", "الهمذاني": "همذان", "الأزدي": "",
}.items() if v}
_SCHOOL = {normalize_arabic(k): v for k, v in {
    "الحنفي": "حنفي", "المالكي": "مالكي", "الحنبلي": "حنبلي",
}.items()}


def parse_entry(text_raw: str) -> dict | None:
    t = _JUNK.sub(" ", text_raw)
    m = _ENTRY.match(t.strip())
    if not m:
        return None
    body = re.sub(r"\s+", " ", m.group(2)).strip(" .")
    norm = normalize_arabic(body)
    out = {"body": body[:400], "norm": norm}

    grade = next((g for g in _GRADES if re.search(rf"(?:^|[ ،,]){g}(?:[ ،,.]|$)", norm)), None)
    out["grade"] = grade

    tm = _TABAQA_RE.search(norm)
    if tm:
        key = normalize_arabic("ال") + tm.group(1)
        out["tabaqa"] = _TABAQA.get(key)
    else:
        out["tabaqa"] = None
    if out["tabaqa"] is None and grade and "صحاب" in grade:
        out["tabaqa"] = 1

    dm = _DEATH.search(norm)
    year, inferred = None, False
    if dm:
        y, has_century = parse_year_words(dm.group(1))
        if y is not None and has_century:
            year = y
        elif y is not None and y < 100:
            year = infer_century(y, out["tabaqa"])
            inferred = year is not None
    if year is None:
        rm = _RAS.search(norm)
        if rm:
            year = _HUNDREDS.get(rm.group(1))
    out["death_year_h"] = year if year and 1 <= year <= 1400 else None
    out["death_inferred"] = inferred

    # name = tokens before the first descriptor comma that contains a grade/tabaqa
    name_part = re.split(normalize_arabic("، ثقة|، صدوق|، مقبول|، ضعيف|، متروك|, ثقة")
                         .replace("، ", "[،,] ?"), body)[0]
    name_part = name_part.split("،")[0] if "،" in name_part[:80] else name_part[:80]
    out["name_norm"] = normalize_arabic(name_part)
    tokens = norm.split()
    out["places"] = sorted({_NISBA_CITY[w] for w in tokens if w in _NISBA_CITY})
    out["school"] = next((_SCHOOL[w] for w in tokens[1:] if w in _SCHOOL), None)
    return out


def _canon_tokens(canonical_norm: str) -> list[str]:
    toks = canonical_norm.split()
    if toks and toks[0] in ("ابا", "ابي"):
        toks[0] = "ابو"
    return ["بن" if t == "ابن" else t for t in toks]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="only top-N narrators by mentions")
    args = ap.parse_args()

    pool.open()
    with pool.connection() as conn:
        ed = conn.execute("""
            SELECT e.edition_id FROM editions e JOIN works w USING (work_id)
            WHERE w.title_ar LIKE %s ORDER BY
              (SELECT count(*) FROM passages p WHERE p.edition_id=e.edition_id) DESC LIMIT 1
        """, (f"%{TAQRIB_TITLE}%",)).fetchone()
        if not ed:
            sys.exit("Taqrib edition not found")
        pages = conn.execute(
            "SELECT passage_id, text_raw FROM passages WHERE edition_id=%s AND length(text_raw)>40 ORDER BY seq",
            (ed["edition_id"],)).fetchall()

    entries = []
    for p in pages:
        e = parse_entry(p["text_raw"])
        if e and len(e["name_norm"].split()) >= 2:
            e["passage_id"] = p["passage_id"]
            entries.append(e)
    print(f"taqrib entries parsed: {len(entries)} "
          f"(graded {sum(1 for e in entries if e['grade'])}, "
          f"tabaqa {sum(1 for e in entries if e['tabaqa'])}, "
          f"death {sum(1 for e in entries if e['death_year_h'])})")

    # index: first two name tokens -> entries
    idx: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in entries:
        toks = _canon_tokens(e["name_norm"])
        if len(toks) >= 2:
            idx[(toks[0], toks[1])].append(e)

    with pool.connection() as conn:
        narrs = conn.execute("""
            SELECT n.narrator_id, n.canonical_norm,
                   (SELECT count(*) FROM isnad_links l WHERE l.narrator_id=n.narrator_id) AS mentions
            FROM narrators n ORDER BY mentions DESC
        """ + (f" LIMIT {int(args.limit)}" if args.limit else "")).fetchall()

    matched = ambiguous = 0
    updates = []
    for n in narrs:
        toks = _canon_tokens(n["canonical_norm"])
        if len(toks) < 2:
            continue
        cands = [e for e in idx.get((toks[0], toks[1]), [])
                 if _canon_tokens(e["name_norm"])[:len(toks)] == toks
                 or toks[:4] == _canon_tokens(e["name_norm"])[:min(4, len(toks))]]
        if not cands:
            continue
        # prefer entries whose name extends the narrator's exact token prefix
        exact = [e for e in cands if _canon_tokens(e["name_norm"])[:len(toks)] == toks]
        pick_from = exact or cands
        if len(pick_from) > 1:
            ambiguous += 1
            updates.append((n["narrator_id"], None, len(pick_from)))
            continue
        matched += 1
        updates.append((n["narrator_id"], pick_from[0], 1))

    print(f"narrators: {len(narrs)}  matched uniquely: {matched}  ambiguous: {ambiguous}")

    if not args.write:
        for nid, e, c in updates[:15]:
            if e:
                print(nid, "->", e["name_norm"][:50], "|", e["grade"], "| tabaqa", e["tabaqa"],
                      "| d.", e["death_year_h"], "|", e["places"])
        return

    with pool.connection() as conn:
        cur = conn.cursor()
        for nid, e, c in updates:
            if e is None:
                cur.execute("""
                    UPDATE narrators SET meta = meta || %s::jsonb WHERE narrator_id=%s
                """, (json.dumps({"rijal_candidates": c}), nid))
                continue
            meta = {"tabaqa": e["tabaqa"], "rijal_grade": e["grade"],
                    "places": e["places"], "school": e["school"],
                    "src_passage": e["passage_id"], "src_book": TAQRIB_TITLE,
                    "death_inferred": e["death_inferred"],
                    "rijal_candidates": 1}
            if e["tabaqa"]:
                meta["tabaqa_label"] = TABAQA_LABEL.get(e["tabaqa"])
            cur.execute("""
                UPDATE narrators SET
                    bio_summary = COALESCE(bio_summary, %s),
                    death_year_h = COALESCE(death_year_h, %s),
                    generation = COALESCE(generation, %s),
                    meta = meta || %s::jsonb
                WHERE narrator_id=%s
            """, (e["body"] + " — " + TAQRIB_TITLE,
                  e["death_year_h"],
                  generation_of(e["tabaqa"]) if e["tabaqa"] else None,
                  json.dumps(meta, ensure_ascii=False), nid))
        conn.commit()
    print("written.")


if __name__ == "__main__":
    main()
