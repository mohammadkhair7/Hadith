"""Timeline analysis of hadith origination (§ docs/HADITH_TIMELINE_ANALYSIS.md).

Estimates WHEN each hadith unit originated, on the hijri axis (negative years =
before the hijra), from three rule-based signal tiers:

  1. dated events named in the text (غزوات, treaties, حجة الوداع, post-prophetic
     anchors for الموقوفات) -> a specific year;
  2. seasonal anchors (رمضان, مواسم الحج, العيد) -> a within-year season tag;
  3. the Companion nearest the Prophet in the sanad -> an origination WINDOW
     [companionship start, 11 AH] for marfu' hadiths (the Prophet's lifetime),
     or [start, companion's death] for mawquf reports.

Events mentioned that postdate 11 AH are ignored for marfu' hadiths (they are
prophecy narratives or narration context, not origination).

Writes timeline_events (dimension) and hadith_dates (one row per unit with at
least one signal). Idempotent per method version. DATABASE_URL-driven.
"""
import os
import re
import sys

import psycopg

sys.stdout.reconfigure(encoding="utf-8")
METHOD = "rule-0.1"

# ---------------------------------------------------------------- events ---
# (key, arabic title, year AH [negative = before hijra], era, regex on
#  normalized text, confidence). Patterns require an event CONTEXT word
# (يوم/غزوه/عام/شهد...) for ambiguous names (بدر, احد, حنين...).
EVENTS = [
    # Meccan period
    ("bitha", "البعثة وبدء الوحي", -13, "meccan",
     r"بدء الوحي|اول ما بدء به رسول الله|غار حراء", 0.65),
    ("habasha", "الهجرة إلى الحبشة", -8, "meccan",
     r"(هجره|هاجرنا|هاجروا|ارض) الحبشه", 0.7),
    ("isra", "الإسراء والمعراج", -2, "meccan",
     r"اسري (بي|به|برسول الله)|ليله اسري", 0.7),
    ("aqaba", "بيعة العقبة", -1, "meccan", r"(بيعه|ليله) العقبه", 0.7),
    # Prophetic Medinan decade
    ("hijra", "الهجرة إلى المدينة", 1, "prophetic",
     r"(لما|حين|منذ) هاجر|مقدم (النبي|رسول الله) المدينه", 0.6),
    ("qibla", "تحويل القبلة", 2, "prophetic",
     r"(حولت|تحويل|صرفت) القبله|قبل بيت المقدس سته عشر", 0.7),
    ("badr", "غزوة بدر", 2, "prophetic",
     r"(يوم|غزوه|عام|شهد|شهدت|شهدوا|اهل|قتلي|اساري) بدر|ببدر", 0.8),
    ("uhud", "غزوة أحد", 3, "prophetic",
     r"(يوم|غزوه|عام|شهداء|قتلي) احد(\s|$)", 0.8),
    ("nadir", "إجلاء بني النضير", 4, "prophetic", r"بني النضير", 0.7),
    ("khandaq", "غزوة الخندق (الأحزاب)", 5, "prophetic",
     r"(يوم|غزوه|عام) (الخندق|الاحزاب)|حفر الخندق|يحفر الخندق", 0.8),
    ("qurayza", "غزوة بني قريظة", 5, "prophetic", r"بني قريظه", 0.7),
    ("mustaliq", "غزوة بني المصطلق (المريسيع)", 6, "prophetic",
     r"بني المصطلق|المريسيع", 0.75),
    ("ifk", "حادثة الإفك", 6, "prophetic", r"(حديث|اهل|قصه) الافك", 0.75),
    ("hudaybiya", "صلح الحديبية", 6, "prophetic", r"الحديبيه", 0.75),
    ("ridwan", "بيعة الرضوان", 6, "prophetic",
     r"بيعه الرضوان|بايعنا تحت الشجره", 0.7),
    ("khaybar", "غزوة خيبر", 7, "prophetic",
     r"(يوم|غزوه|عام|فتح|زمن) خيبر|بخيبر|الي خيبر", 0.75),
    ("umrat_qada", "عمرة القضاء", 7, "prophetic",
     r"عمره القضاء|عمره القضيه", 0.75),
    ("muta", "غزوة مؤتة", 8, "prophetic", r"مءته", 0.7),
    ("fath", "فتح مكة", 8, "prophetic",
     r"عام الفتح|يوم الفتح|فتح مكه|زمن الفتح", 0.8),
    ("hunayn", "غزوة حنين", 8, "prophetic",
     r"(يوم|غزوه|عام) حنين|الي حنين|بحنين", 0.8),
    ("taif", "حصار الطائف", 8, "prophetic", r"(غزوه|حصار|يوم) الطاءف", 0.7),
    ("tabuk", "غزوة تبوك", 9, "prophetic", r"تبوك|جيش العسره", 0.8),
    ("baraa_hajj", "حجة أبي بكر بالناس", 9, "prophetic", r"حجه ابي بكر", 0.7),
    ("wufud", "عام الوفود", 9, "prophetic", r"عام الوفود", 0.7),
    ("hajj_wada", "حجة الوداع", 10, "prophetic", r"حجه الوداع", 0.85),
    ("wafat", "مرض النبي ﷺ ووفاته", 11, "prophetic",
     r"مرضه الذي (مات|توفي|قبض) فيه|لما (توفي|قبض) (النبي|رسول الله)", 0.65),
    # post-prophetic anchors (date موقوف/مقطوع reports)
    ("ridda", "حروب الردة", 11, "rashidun", r"(اهل|حروب) الرده", 0.65),
    ("yarmuk", "معركة اليرموك", 15, "rashidun", r"اليرموك", 0.7),
    ("qadisiyya", "معركة القادسية", 15, "rashidun", r"القادسيه", 0.7),
    ("amwas", "طاعون عمواس", 18, "rashidun", r"طاعون عمواس", 0.75),
    ("ramada", "عام الرمادة", 18, "rashidun", r"عام الرماده", 0.75),
    ("maqtal_umar", "مقتل عمر بن الخطاب", 23, "rashidun",
     r"(قتل|طعن|اصيب) عمر", 0.55),
    ("dar", "حصار عثمان (يوم الدار)", 35, "rashidun",
     r"(قتل|حصر) عثمان|يوم الدار", 0.55),
    ("jamal", "موقعة الجمل", 36, "rashidun", r"(يوم|وقعه|موقعه) الجمل", 0.7),
    ("siffin", "صفين", 37, "rashidun", r"صفين", 0.75),
    ("nahrawan", "النهروان", 38, "rashidun", r"النهروان", 0.7),
    ("karbala", "مقتل الحسين (كربلاء)", 61, "umayyad",
     r"قتل الحسين|كربلاء", 0.7),
    ("harra", "وقعة الحرة", 63, "umayyad", r"(يوم|وقعه) الحره", 0.7),
]

SEASONS = [
    ("ramadan", "رمضان", r"رمضان|ليله القدر"),
    ("hajj", "موسم الحج", r"يوم عرفه|يوم النحر|يوم الترويه|ايام التشريق|حجه الوداع"),
    ("eid", "العيد", r"يوم الفطر|يوم الاضحي|صلاه العيد|يوم عيد"),
]

# (key, arabic, normalized name alternates, companionship start AH, death AH)
# start: year the narrator entered the Prophet's company (approx, classical
# sources); -13 = Meccan-era Muslim from the beginning of the mission.
COMPANIONS = [
    ("abu_hurayra", "أبو هريرة", ["ابو هريره", "ابي هريره", "ابا هريره"], 7, 59),
    ("aisha", "عائشة أم المؤمنين", ["عاءشه"], 2, 58),
    ("ibn_abbas", "عبد الله بن عباس", ["ابن عباس", "عبد الله بن عباس"], 8, 68),
    ("ibn_umar", "عبد الله بن عمر", ["ابن عمر", "عبد الله بن عمر"], 1, 74),
    ("anas", "أنس بن مالك", ["انس بن مالك", "انس"], 1, 93),
    ("jabir", "جابر بن عبد الله", ["جابر بن عبد الله", "جابر"], 1, 78),
    ("abu_said", "أبو سعيد الخدري", ["ابو سعيد الخدري", "ابي سعيد الخدري", "ابا سعيد الخدري"], 3, 74),
    ("ibn_masud", "عبد الله بن مسعود", ["ابن مسعود", "عبد الله بن مسعود"], -13, 32),
    ("ali", "علي بن أبي طالب", ["علي بن ابي طالب"], -13, 40),
    ("umar", "عمر بن الخطاب", ["عمر بن الخطاب"], -7, 23),
    ("abu_bakr", "أبو بكر الصديق", ["ابو بكر الصديق", "ابي بكر الصديق"], -13, 13),
    ("uthman", "عثمان بن عفان", ["عثمان بن عفان"], -13, 35),
    ("abu_musa", "أبو موسى الأشعري", ["ابو موسي الاشعري", "ابي موسي الاشعري", "ابا موسي الاشعري"], 7, 44),
    ("muawiya", "معاوية بن أبي سفيان", ["معاويه بن ابي سفيان", "معاويه"], 8, 60),
    ("abu_dharr", "أبو ذر الغفاري", ["ابو ذر", "ابي ذر", "ابا ذر"], -10, 32),
    ("ubayy", "أبي بن كعب", ["ابي بن كعب"], 1, 30),
    ("zayd_thabit", "زيد بن ثابت", ["زيد بن ثابت"], 1, 45),
    ("saad", "سعد بن أبي وقاص", ["سعد بن ابي وقاص"], -13, 55),
    ("bara", "البراء بن عازب", ["البراء بن عازب", "البراء"], 1, 72),
    ("abu_darda", "أبو الدرداء", ["ابو الدرداء", "ابي الدرداء", "ابا الدرداء"], 2, 32),
    ("muadh", "معاذ بن جبل", ["معاذ بن جبل"], 1, 18),
    ("bilal", "بلال بن رباح", ["بلال بن رباح", "بلال"], -13, 20),
    ("salman", "سلمان الفارسي", ["سلمان الفارسي"], 1, 34),
    ("ubada", "عبادة بن الصامت", ["عباده بن الصامت"], 1, 34),
    ("abu_ayyub", "أبو أيوب الأنصاري", ["ابو ايوب الانصاري", "ابي ايوب الانصاري"], 1, 52),
    ("sahl_saad", "سهل بن سعد الساعدي", ["سهل بن سعد"], 1, 88),
    ("imran", "عمران بن حصين", ["عمران بن حصين"], 7, 52),
    ("abu_umama", "أبو أمامة الباهلي", ["ابو امامه", "ابي امامه"], 1, 86),
    ("ibn_amr_as", "عبد الله بن عمرو بن العاص", ["عبد الله بن عمرو"], 7, 65),
    ("mughira", "المغيرة بن شعبة", ["المغيره بن شعبه", "المغيره"], 5, 50),
    ("umm_salama", "أم سلمة", ["ام سلمه"], 4, 62),
    ("hafsa", "حفصة أم المؤمنين", ["حفصه"], 3, 45),
    ("maymuna", "ميمونة أم المؤمنين", ["ميمونه"], 7, 51),
    ("abu_qatada", "أبو قتادة", ["ابو قتاده", "ابي قتاده"], 1, 54),
    ("hudhayfa", "حذيفة بن اليمان", ["حذيفه بن اليمان", "حذيفه"], 1, 36),
    ("numan_bashir", "النعمان بن بشير", ["النعمان بن بشير"], 1, 64),
    ("abu_bakra", "أبو بكرة الثقفي", ["ابو بكره", "ابي بكره"], 8, 51),
    ("aql_zubayr", "الزبير بن العوام", ["الزبير بن العوام"], -13, 36),
    ("talha", "طلحة بن عبيد الله", ["طلحه بن عبيد الله"], -13, 36),
    ("saeed_zayd", "سعيد بن زيد", ["سعيد بن زيد"], -13, 51),
]

PROPHET_DEATH = 11         # Rabi' I, 11 AH
MISSION_START = -13        # بعثة, 13 years before hijra

_EVENTS = [(k, ar, y, era, re.compile(rx), c) for k, ar, y, era, rx, c in EVENTS]
_SEASONS = [(k, ar, re.compile(rx)) for k, ar, rx in SEASONS]
def _alt_rx(a: str) -> re.Pattern:
    # single-word alternates (جابر, معاويه, حفصه...) must be the END of the
    # narrator string — otherwise they'd swallow other narrators sharing the
    # first name (معاويه بن قره, حفصه بنت سيرين, جابر بن سمره...)
    if " " not in a:
        return re.compile(rf"(?:^|\s){re.escape(a)}\s*[،.]?\s*$")
    return re.compile(rf"(?:^|\s){re.escape(a)}(?:\s|$|،)")


_COMP = [(k, ar, [_alt_rx(a) for a in alts], start, death)
         for k, ar, alts, start, death in COMPANIONS]

DDL = """
CREATE TABLE IF NOT EXISTS timeline_events (
    event_key text PRIMARY KEY,
    title_ar  text NOT NULL,
    year_ah   smallint NOT NULL,
    era       text NOT NULL
);
CREATE TABLE IF NOT EXISTS hadith_dates (
    passage_id    bigint PRIMARY KEY REFERENCES passages(passage_id) ON DELETE CASCADE,
    year_min      smallint,
    year_max      smallint,
    year_best     smallint,
    basis         text NOT NULL,
    event_key     text REFERENCES timeline_events(event_key),
    season        text,
    companion_key text,
    companion_ar  text,
    confidence    real NOT NULL,
    method        text NOT NULL DEFAULT 'rule-0.1'
);
CREATE INDEX IF NOT EXISTS hadith_dates_year ON hadith_dates(year_best);
CREATE INDEX IF NOT EXISTS hadith_dates_event ON hadith_dates(event_key);
CREATE INDEX IF NOT EXISTS hadith_dates_season ON hadith_dates(season);
CREATE INDEX IF NOT EXISTS hadith_dates_companion ON hadith_dates(companion_key);
"""


def match_companion(name_norm: str, cache: dict):
    if name_norm in cache:
        return cache[name_norm]
    hit = None
    for k, ar, regs, start, death in _COMP:
        if any(r.search(name_norm) for r in regs):
            hit = (k, ar, start, death)
            break
    cache[name_norm] = hit
    return hit


def analyze(text_norm: str, type_norm: str | None, narr_norm: str | None,
            comp_cache: dict):
    """Return row dict or None."""
    marfu = type_norm is None or type_norm.startswith("marfu") or type_norm == "qudsi"

    best_event = None                     # (key, ar, year, conf)
    for k, ar, y, era, rx, conf in _EVENTS:
        if not rx.search(text_norm):
            continue
        if marfu and y > PROPHET_DEATH:   # prophecy/context, not origination
            continue
        if type_norm is not None and not marfu and era == "meccan":
            pass                          # mawquf can still cite Meccan events
        if best_event is None or conf > best_event[3]:
            best_event = (k, ar, y, conf)

    season = None
    for k, ar, rx in _SEASONS:
        if rx.search(text_norm):
            season = k
            break

    comp = match_companion(narr_norm, comp_cache) if narr_norm else None

    row = {"basis": None, "year_min": None, "year_max": None, "year_best": None,
           "event_key": None, "season": season, "companion_key": None,
           "companion_ar": None, "confidence": 0.0}

    if comp:
        ck, car, start, death = comp
        row["companion_key"], row["companion_ar"] = ck, car
        if marfu:
            row["year_min"], row["year_max"] = start, PROPHET_DEATH
        elif type_norm == "mawquf":
            row["year_min"], row["year_max"] = start, death
        else:                              # maqtu etc: companion not the speaker
            comp = None
            row["companion_key"] = row["companion_ar"] = None
        if comp:
            row["basis"], row["confidence"] = "companion", 0.4

    if best_event:
        k, ar, y, conf = best_event
        row["event_key"], row["year_best"] = k, y
        if comp and row["year_min"] is not None \
                and row["year_min"] <= y <= row["year_max"]:
            row["basis"], row["confidence"] = "event+companion", min(conf + 0.1, 0.95)
        else:
            row["basis"], row["confidence"] = "event", conf
        row["year_min"] = row["year_max"] = y

    if row["basis"] is None and season:
        row["basis"], row["confidence"] = "season", 0.3

    return row if row["basis"] else None


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    with psycopg.connect(url) as conn:
        conn.execute(DDL)
        for k, ar, y, era, _, _ in _EVENTS:
            conn.execute("""
                INSERT INTO timeline_events (event_key, title_ar, year_ah, era)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (event_key) DO UPDATE
                SET title_ar=EXCLUDED.title_ar, year_ah=EXCLUDED.year_ah,
                    era=EXCLUDED.era
            """, (k, ar, y, era))
        conn.execute("DELETE FROM hadith_dates WHERE method=%s", (METHOD,))
        conn.commit()

        cur = conn.cursor(name="tl_scan")
        cur.itersize = 4000
        cur.execute("""
            SELECT p.passage_id, p.text_norm, ht.type_norm, last.canonical_norm
            FROM passages p
            LEFT JOIN hadith_types ht ON ht.passage_id = p.passage_id
            LEFT JOIN LATERAL (
                SELECT n.canonical_norm
                FROM isnad_chains c
                JOIN isnad_links l ON l.chain_id = c.chain_id
                JOIN narrators n ON n.narrator_id = l.narrator_id
                WHERE c.passage_id = p.passage_id AND c.ord = 0
                ORDER BY l.pos DESC LIMIT 1
            ) last ON true
            WHERE p.kind = 'unit'
        """)

        comp_cache: dict = {}
        out: list[tuple] = []
        n_scan = n_hit = 0
        with conn.cursor() as ins:
            def flush():
                if not out:
                    return
                with ins.copy("""
                    COPY hadith_dates (passage_id, year_min, year_max, year_best,
                        basis, event_key, season, companion_key, companion_ar,
                        confidence, method) FROM STDIN
                """) as cp:
                    for r in out:
                        cp.write_row(r)
                out.clear()

            for pid, tnorm, htype, narr in cur:
                n_scan += 1
                row = analyze(tnorm or "", htype, narr, comp_cache)
                if row:
                    n_hit += 1
                    out.append((pid, row["year_min"], row["year_max"],
                                row["year_best"], row["basis"], row["event_key"],
                                row["season"], row["companion_key"],
                                row["companion_ar"], row["confidence"], METHOD))
                if len(out) >= 4000:
                    flush()
                if n_scan % 40000 == 0:
                    print(f"  scanned {n_scan} (dated {n_hit})")
            flush()
        conn.commit()
        conn.execute("ANALYZE hadith_dates")
        conn.commit()

        print(f"\nscanned {n_scan} units, dated {n_hit} "
              f"({100 * n_hit / max(n_scan, 1):.1f}%)\n")
        for label, sql in [
            ("basis", "SELECT basis, count(*) FROM hadith_dates GROUP BY 1 ORDER BY 2 DESC"),
            ("year_best", """SELECT year_best, count(*) FROM hadith_dates
                             WHERE year_best IS NOT NULL GROUP BY 1 ORDER BY 1"""),
            ("events", """SELECT d.event_key, e.title_ar, e.year_ah, count(*)
                          FROM hadith_dates d JOIN timeline_events e USING (event_key)
                          GROUP BY 1,2,3 ORDER BY count(*) DESC"""),
            ("seasons", """SELECT season, count(*) FROM hadith_dates
                           WHERE season IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"""),
            ("companions", """SELECT companion_ar, count(*) FROM hadith_dates
                              WHERE companion_ar IS NOT NULL
                              GROUP BY 1 ORDER BY 2 DESC LIMIT 25"""),
        ]:
            print(f"--- {label} ---")
            for r in conn.execute(sql).fetchall():
                print("  ", r)
    print("done")


if __name__ == "__main__":
    main()
