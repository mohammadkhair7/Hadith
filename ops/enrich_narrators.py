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
# tolerate leading noise before the entry number: bracketed sigla («[ م ه ]»)
# and section markers («فصل " خ "»)
_ENTRY = re.compile(
    r"^\s*(?:\[[^\]]{1,25}\]\s*)?(?:فصل[^0-9]{0,12})?(\d+)\s*-\s*"
    r"(?:\[[^\]]{0,30}\]\s*)?(.+)$", re.S)

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


_ALT = re.compile(normalize_arabic("وقيل|قيل|أو ") + "|" + normalize_arabic("وله")
                  + "|" + normalize_arabic("وهو") + "|" + normalize_arabic("وقد"))


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


# «مات سنة», «ماتت سنة», «مات في آخر سنة», «مات في ذي الحجة سنة» — allow a few
# intervening words within the same clause before «سنة»
_DEATH = re.compile(normalize_arabic("(?:مات|توفي)") + r"ت?[^.،,؛]{0,28}?"
                    + normalize_arabic("سنه") + r"\s*([^.,،؛]{2,60})")
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
_TABAQA_RE = re.compile(
    normalize_arabic("من") + r"\s+(?:" + normalize_arabic("كبار") + r"\s+|"
    + normalize_arabic("صغار") + r"\s+|" + normalize_arabic("اوساط") + r"\s+)?"
    + normalize_arabic("ال") + r"(\S+(?:\s+" + normalize_arabic("عشره") + r")?)")
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

    # each grade word may carry the definite article («الصحابي الجليل»)
    grade = next(
        (g for g in _GRADES if re.search(
            r"(?:^|[ ،,])" + r"\s+".join(rf"(?:ال)?{re.escape(w)}" for w in g.split())
            + r"(?:[ ،,.]|$)", norm)),
        None)
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


# ---------------------------------------------------------------------------
# Curated identifications for the famous SHORT isnad names. Token matching
# cannot resolve these (single token, kunya form, or laqab), yet by the
# settled convention of hadith science each shorthand denotes one specific
# narrator. Values: (Taqrib entry name prefix, extra phrase the entry body
# must contain — "" when the prefix alone is unique). All facts still come
# from the Taqrib entry itself; only the identification is curated.
CURATED_IDENT: dict[str, tuple[str, str]] = {
    "ابي هريره":            ("ابو هريره", "الدوسي"),
    "عاءشه":                ("عاءشه بنت ابي بكر", ""),
    "ابن عباس":             ("عبد الله بن عباس بن عبد المطلب", ""),
    "انس":                  ("انس بن مالك بن النضر", ""),
    "انس بن مالك":          ("انس بن مالك بن النضر", ""),
    "شعبه":                 ("شعبه بن الحجاج", ""),
    "معمر":                 ("معمر بن راشد", ""),
    "عبد الرزاق":           ("عبد الرزاق بن همام", ""),
    "وكيع":                 ("وكيع بن الجراح", ""),
    "الزهري":               ("محمد بن مسلم بن عبيد الله", "الزهري"),
    "ابن شهاب":             ("محمد بن مسلم بن عبيد الله", "الزهري"),
    "الاعمش":               ("سليمان بن مهران", "الاعمش"),
    "قتاده":                ("قتاده بن دعامه", ""),
    "ابن جريج":             ("عبد الملك بن عبد العزيز بن جريج", ""),
    "نافع":                 ("نافع", "مولي ابن عمر"),
    "ابراهيم":              ("ابراهيم بن يزيد", "النخعي"),
    "ابي اسحاق":            ("عمرو بن عبد الله", "السبيعي"),
    "الحسن":                ("الحسن بن ابي الحسن", "البصري"),
    "عكرمه":                ("عكرمه", "مولي ابن عباس"),
    "ابن عمر":              ("عبد الله بن عمر بن الخطاب", ""),
    "مالك":                 ("مالك بن انس", ""),
    "الثوري":               ("سفيان بن سعيد بن مسروق", ""),
    "الليث":                ("الليث بن سعد", ""),
    "هشيم":                 ("هشيم", "القاسم بن دينار"),
    "مجاهد":                ("مجاهد بن جبر", ""),
    "الشعبي":               ("عامر بن شراحيل", "الشعبي"),
    "منصور":                ("منصور بن المعتمر", ""),
    "ابو معاويه":           ("محمد بن خازم", "الضرير"),
    "ابو اسامه":            ("حماد بن اسامه", ""),
    "عفان":                 ("عفان بن مسلم", "الصفار"),
    "اسراءيل":              ("اسراءيل بن يونس", ""),
    "محمد بن اسحاق":        ("محمد بن اسحاق بن يسار", ""),
    "ابو بكر بن ابي شيبه":  ("عبد الله بن محمد بن ابي شيبه", ""),
    "ابي سلمه":             ("ابو سلمه بن عبد الرحمن بن عوف", ""),
    "شريك":                 ("شريك بن عبد الله النخعي", ""),
    "محمد بن جعفر":         ("محمد بن جعفر", "غندر"),
    "عطاء":                 ("عطاء بن ابي رباح", ""),
}

# Field-level corrections applied on top of the matched Taqrib entry when its
# phrasing defeats the parser («مات سنة سبع أو ثمان وأربعين ومائة», «بضع
# عشرة ومائة»…). Values are the standard readings of the same Taqrib entries.
CURATED_OVERRIDES: dict[str, dict] = {
    "ابي هريره":    {"death_year_h": 57},
    "عاءشه":        {"death_year_h": 57, "tabaqa": 1, "grade": "صحابية، أم المؤمنين"},
    "ابن عباس":     {"death_year_h": 68, "tabaqa": 1, "grade": "صحابي جليل"},
    "ابن عمر":      {"death_year_h": 73, "tabaqa": 1, "grade": "صحابي جليل"},
    "انس":          {"death_year_h": 92},
    "انس بن مالك":  {"death_year_h": 92},
    "الزهري":       {"death_year_h": 125, "tabaqa": 4,
                     "grade": "متفق على جلالته وإتقانه"},
    "ابن شهاب":     {"death_year_h": 125, "tabaqa": 4,
                     "grade": "متفق على جلالته وإتقانه"},
    "الاعمش":       {"death_year_h": 148},
    "قتاده":        {"death_year_h": 117, "tabaqa": 4},
    "وكيع":         {"death_year_h": 197},
    "عبد الرزاق":   {"death_year_h": 211},
    "ابراهيم":      {"death_year_h": 96, "tabaqa": 5},
    "الشعبي":       {"death_year_h": 103},
    "منصور":        {"tabaqa": 5},
    "مالك":         {"death_year_h": 179, "grade": "إمام دار الهجرة، رأس المتقنين"},
    "الثوري":       {"death_year_h": 161, "tabaqa": 7},
    "الليث":        {"death_year_h": 175, "tabaqa": 7},
    "عفان":         {"death_year_h": 220, "tabaqa": 10},
    "شريك":         {"death_year_h": 177},
    "هشيم":         {"death_year_h": 183},
}

# Names genuinely ambiguous between two+ famous narrators: no facts are
# assigned, but a short identity note gives the reader the standard picture.
AMBIGUOUS_NOTES: dict[str, str] = {
    "سفيان": "يُطلق «سفيان» في الأسانيد على سفيان الثوري (ت 161هـ) أو "
             "سفيان بن عيينة (ت 198هـ)، ويُميَّز بينهما بالراوي عنه وبالشيخ.",
    "حماد": "يُطلق «حماد» في الأسانيد على حماد بن زيد (ت 179هـ) أو "
            "حماد بن سلمة (ت 167هـ)، ويُميَّز بينهما بالراوي عنه.",
    "يحيي بن سعيد": "قد يراد به يحيى بن سعيد القطان (ت 198هـ) أو "
                    "يحيى بن سعيد الأنصاري (ت 144هـ) بحسب السياق.",
    "هشام": "قد يراد به هشام بن عروة أو هشام الدستوائي أو هشام بن حسان "
            "بحسب الراوي عنه.",
    "يونس": "قد يراد به يونس بن يزيد الأيلي (عن الزهري غالبًا، ت 159هـ) أو "
            "يونس بن عبيد البصري (ت 139هـ).",
    "سعيد": "قد يراد به سعيد بن المسيب أو سعيد بن جبير أو غيرهما بحسب السند.",
    "جابر": "الغالب أنه الصحابي جابر بن عبد الله (ت 78هـ)؛ وفي بعض الأسانيد "
            "الكوفية جابر الجعفي (ت 128هـ).",
    "عبد الله": "قد يراد به عبد الله بن مسعود أو ابن عمر أو ابن عمرو أو ابن "
                "عباس بحسب السند والبلد.",
    "جرير": "الغالب في المتأخرين جرير بن عبد الحميد (ت 188هـ)، وقد يراد "
            "جرير بن حازم (ت 170هـ).",
    "يحيي": "قد يراد به يحيى بن سعيد القطان أو يحيى بن معين أو يحيى بن يحيى "
            "النيسابوري بحسب الطبقة.",
    "علي": "الغالب في أسانيد المرفوعات أنه علي بن أبي طالب رضي الله عنه "
           "(ت 40هـ).",
    "ابي": "قد يراد به الصحابي أبي بن كعب سيد القراء (ت نحو 30هـ)، وقد يكون "
           "من قول الراوي «عن أبي» بمعنى الوالد.",
    "ابو داود": "في أسانيد المتقدمين الغالب أبو داود الطيالسي (ت 204هـ)، "
                "وفي المتأخرين أبو داود السجستاني صاحب السنن (ت 275هـ).",
}

# Well-known transmitters of the later sources (post-Taqrib era, so no rijal
# entry exists in the corpus). Standard biographical facts, marked as curated.
CURATED_FACTS: dict[str, dict] = {
    "ابو العباس محمد بن يعقوب": {
        "bio": "أبو العباس محمد بن يعقوب الأصم النيسابوري (247–346هـ)، محدّث "
               "نيسابور ومُسنِد عصره؛ عنه يروي الحاكم والبيهقي كثيرًا من "
               "الأسانيد العالية.",
        "death_year_h": 346, "places": ["نيسابور"],
    },
    ") ابو عبد الله الحافظ": {
        "bio": "أبو عبد الله الحاكم النيسابوري (321–405هـ)، صاحب «المستدرك "
               "على الصحيحين» و«معرفة علوم الحديث»؛ شيخ البيهقي، وأكثر "
               "البيهقي الرواية عنه في السنن الكبرى.",
        "death_year_h": 405, "places": ["نيسابور"],
    },
    "علي بن عبد العزيز": {
        "bio": "الغالب أنه علي بن عبد العزيز البغوي المكي (ت 286هـ)، راوي "
               "مسند علي بن الجعد وشيخ الطبراني في كثير من معاجمه.",
        "death_year_h": 286, "places": ["مكة المكرمة"],
    },
}


def curated_match(entries: list[dict], prefix: str, contains: str) -> dict | None:
    """Unique Taqrib entry whose name starts with the curated prefix (and whose
    body mentions the extra phrase when given)."""
    pn, cn = normalize_arabic(prefix), normalize_arabic(contains)
    cands = [e for e in entries
             if e["name_norm"].startswith(pn) and (not cn or cn in e["norm"])]
    if not cands:
        # fall back: prefix anywhere at the start of the entry body
        cands = [e for e in entries
                 if e["norm"].startswith(pn) and (not cn or cn in e["norm"])]
    return cands[0] if cands else None


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
        # single-token names (e.g. «عكرمة ، أبو عبد الله ، مولى ابن عباس») are
        # kept for curated matching; the token index below still requires >= 2
        if e and len(e["name_norm"].split()) >= 1:
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
    curated_ids: set[int] = set()
    notes = []
    curated_facts: list[tuple[int, dict]] = []
    for n in narrs:
        # curated identifications first (famous short names, kunyas, laqabs)
        cur = CURATED_IDENT.get(n["canonical_norm"])
        if cur:
            e = curated_match(entries, *cur)
            if e:
                ov = CURATED_OVERRIDES.get(n["canonical_norm"])
                if ov:
                    e = {**e}
                    if ov.get("death_year_h"):
                        e["death_year_h"] = ov["death_year_h"]
                        e["death_inferred"] = False
                    if ov.get("tabaqa"):
                        e["tabaqa"] = ov["tabaqa"]
                    if ov.get("grade"):
                        e["grade"] = normalize_arabic(ov["grade"])
                matched += 1
                curated_ids.add(n["narrator_id"])
                updates.append((n["narrator_id"], e, 1))
                continue
            print(f"  curated ident NOT found in Taqrib: {n['canonical_norm']} -> {cur[0]}")
        note = AMBIGUOUS_NOTES.get(n["canonical_norm"])
        if note:
            notes.append((n["narrator_id"], note))
            continue
        facts = CURATED_FACTS.get(n["canonical_norm"])
        if facts:
            curated_facts.append((n["narrator_id"], facts))
            continue
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

    print(f"narrators: {len(narrs)}  matched uniquely: {matched} "
          f"(curated {len(curated_ids)})  ambiguous: {ambiguous}  "
          f"identity notes: {len(notes)}  curated facts: {len(curated_facts)}")

    if not args.write:
        for nid, e, c in updates[:15]:
            if e:
                print(nid, "->", e["name_norm"][:50], "|", e["grade"], "| tabaqa", e["tabaqa"],
                      "| d.", e["death_year_h"], "|", e["places"])
        print("-- curated matches --")
        for nid, e, c in updates:
            if e and nid in curated_ids:
                print(nid, "->", e["name_norm"][:55], "|", e["grade"], "| tabaqa", e["tabaqa"],
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
            if nid in curated_ids:
                meta["curated_ident"] = True
            if e["tabaqa"]:
                meta["tabaqa_label"] = TABAQA_LABEL.get(e["tabaqa"])
            # curated rows overwrite: their previous facts (if any) came from a
            # weaker match, and the Taqrib entry is the authoritative record
            force = nid in curated_ids
            cur.execute(f"""
                UPDATE narrators SET
                    bio_summary = {"%s" if force else "COALESCE(bio_summary, %s)"},
                    death_year_h = {"COALESCE(%s, death_year_h)" if force
                                    else "COALESCE(death_year_h, %s)"},
                    generation = {"COALESCE(%s, generation)" if force
                                  else "COALESCE(generation, %s)"},
                    meta = meta || %s::jsonb
                WHERE narrator_id=%s
            """, (e["body"] + " — " + TAQRIB_TITLE,
                  e["death_year_h"],
                  generation_of(e["tabaqa"]) if e["tabaqa"] else None,
                  json.dumps(meta, ensure_ascii=False), nid))
        for nid, note in notes:
            cur.execute("""
                UPDATE narrators SET
                    bio_summary = COALESCE(bio_summary, %s),
                    meta = meta || %s::jsonb
                WHERE narrator_id=%s
            """, (note, json.dumps({"identity_note": note}, ensure_ascii=False), nid))
        for nid, facts in curated_facts:
            cur.execute("""
                UPDATE narrators SET
                    bio_summary = %s,
                    death_year_h = COALESCE(%s, death_year_h),
                    meta = meta || %s::jsonb
                WHERE narrator_id=%s
            """, (facts["bio"], facts.get("death_year_h"),
                  json.dumps({"places": facts.get("places", []),
                              "src_book": "معلومة محررة", "curated_ident": True},
                             ensure_ascii=False), nid))
        conn.commit()
    print("written.")


if __name__ == "__main__":
    main()
