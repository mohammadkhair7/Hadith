# Hadith Origination Timeline — Analysis Report

**Version:** rule-0.1 · **Run date:** 2026-08-20 · **Pipeline:** `ops/analyze_timeline.py` ·
**UI:** الخط الزمني tab (`/timeline`) · **API:** `GET /api/v1/analytics/timeline`,
`GET /api/v1/analytics/timeline/hadiths`

---

## 1. Objective

Most hadiths carry no explicit date: the classical corpus records *who* transmitted a
report, rarely *when* it originated. Yet three families of textual and prosopographic
clues allow an **estimated origination time** on the hijri axis:

1. **Dated events named in the text** — a hadith opening «لما كان يوم بدر…» or «قال في
   حجة الوداع…» anchors itself to a year known from the sīra/history literature.
2. **Seasonal anchors** — رمضان, mawāsim of the Ḥajj (يوم عرفة, يوم النحر, أيام
   التشريق), and العيد place a report within a season of the year (without fixing the
   year itself).
3. **The Companion nearest the Prophet ﷺ in the sanad** — a marfūʿ hadith narrated
   directly by أبو هريرة cannot have originated before his arrival in 7 AH, nor after
   the Prophet's death in 11 AH: his companionship interval bounds the origination
   window. For mawqūf reports the window extends to the Companion's death year.

This analysis applies all three tiers to the full hadith-unit corpus (276,356 units
across 41 Jamiʿ collections), stores the results in the `hadith_dates` table, and
serves them through the **الخط الزمني (Timeline)** tab.

The year axis is hijri; **negative years denote years before the hijra**
(البعثة = −13, الإسراء = −2). The Prophet's ﷺ Medinan decade is 1–11 AH.

---

## 2. Method

### 2.1 Tier 1 — dated-event lexicon (specific year)

38 events with well-attested dates, each with a **context-guarded regex** over the
normalized text (`text_norm`: diacritics stripped, hamza/alef/tāʾ marbūṭa folded).
Ambiguous names require an event-context word: bare «أحد» (= "anyone") never matches —
only «يوم أحد», «غزوة أحد», «شهداء أحد»; bare «بدر» (also a person's name) requires
«يوم/غزوة/عام/شهد/أهل/قتلى/أسارى بدر» or «ببدر». Unique place-events (الحديبية, تبوك)
match on the name alone.

| Era | Events (year AH) |
|---|---|
| العهد المكي | البعثة (−13), هجرة الحبشة (−8), الإسراء (−2), بيعة العقبة (−1) |
| العهد النبوي المدني | الهجرة (1), تحويل القبلة (2), بدر (2), أحد (3), بنو النضير (4), الخندق (5), بنو قريظة (5), بنو المصطلق (6), الإفك (6), الحديبية (6), بيعة الرضوان (6), خيبر (7), عمرة القضاء (7), مؤتة (8), فتح مكة (8), حنين (8), الطائف (8), تبوك (9), حجة أبي بكر (9), عام الوفود (9), حجة الوداع (10), مرض النبي ﷺ ووفاته (11) |
| عهد الخلفاء الراشدين | الردة (11), اليرموك (15), القادسية (15), طاعون عمواس (18), عام الرمادة (18), مقتل عمر (23), يوم الدار (35), الجمل (36), صفين (37), النهروان (38) |
| العهد الأموي | كربلاء (61), الحرة (63) |

**Prophecy guard:** for hadiths classified marfūʿ (or unclassified), events later than
11 AH are *ignored* — a marfūʿ hadith mentioning صفين is a prophecy narrative or
narration context, not evidence of post-prophetic origination. Post-11 events date only
mawqūf/maqṭūʿ reports (āthār).

### 2.2 Tier 2 — seasonal anchors (within-year season)

| Season | Patterns |
|---|---|
| رمضان | رمضان, ليلة القدر |
| موسم الحج | يوم عرفة, يوم النحر, يوم التروية, أيام التشريق, حجة الوداع |
| العيد | يوم الفطر, يوم الأضحى, صلاة العيد |

A season alone gives no year; it is stored as a `season` tag (also alongside an
event/companion signal when both are present).

### 2.3 Tier 3 — Companion narration windows

The narrator **nearest the Prophet** (last link of the primary isnād chain, `ord = 0`)
is matched against a curated list of **40 prolific Companions** with classically
attested companionship-start and death years (أبو هريرة 7→59, عائشة 2→58, ابن عباس
8→68, ابن عمر 1→74, أنس 1→93, ابن مسعود −13→32, …). Matching is
boundary-guarded: single-word alternates (جابر, معاوية, حفصة) must terminate the
narrator string so that معاوية بن قرة (tābiʿī) or حفصة بنت سيرين never match; «عبد الله
بن عمر» never swallows «عبد الله بن عمرو».

Window semantics:

- **marfūʿ / qudsī / unclassified** → `[companionship_start, 11]` (Prophet's lifetime);
- **mawqūf** → `[companionship_start, companion_death]`;
- **maqṭūʿ** → companion tier skipped (the speaker is a tābiʿī).

The DB's own `narrators.death_year_h` column has thin coverage (1,628 narrators, only
84 marked Companions), which is why the curated list drives this tier; the column is a
future enrichment path.

### 2.4 Combination & confidence

| Basis | Rule | Confidence |
|---|---|---|
| `event+companion` | event year falls **inside** the companion window | event conf + 0.1 (≤ 0.95) |
| `event` | dated event matched, no (consistent) companion | 0.55–0.85 per event |
| `companion` | window only | 0.40 |
| `season` | season only | 0.30 |

One row per hadith unit in `hadith_dates(passage_id, year_min, year_max, year_best,
basis, event_key, season, companion_key, companion_ar, confidence, method)`.

---

## 3. Results (run of 2026-08-20)

### 3.1 Coverage

| Metric | Count | % of units |
|---|---|---|
| Hadith units scanned | 276,356 | 100% |
| **Dated (any signal)** | **105,395** | **38.1%** |
| Specific year (event / event+companion) | 8,974 | 3.2% |
| Companion window only | 92,658 | 33.5% |
| Season tag (incl. combined) | 6,858 | 2.5% |
| Season only | 3,763 | 1.4% |

### 3.2 Year distribution (specific-year hadiths)

```
 year AH   hadiths      dominant events
 −13            18      البعثة وبدء الوحي
  −8           136      الهجرة إلى الحبشة
  −2           222      الإسراء والمعراج
  −1            26      بيعة العقبة
   1            42      الهجرة إلى المدينة
   2         1,741      بدر (1,718)، تحويل القبلة
   3           916      أحد
   4           143      بنو النضير
   5           442      الخندق (333)، بنو قريظة
   6           790      الحديبية (620)، بنو المصطلق، الإفك، بيعة الرضوان
   7         1,086      خيبر (1,058)، عمرة القضاء
   8         1,642      فتح مكة (1,091)، حنين (422)، مؤتة، الطائف
   9           581      تبوك (579)
  10           713      حجة الوداع
  11           381      مرض النبي ﷺ ووفاته، الردة
 15–63         95      آثار: اليرموك، القادسية، مقتل عمر، الجمل، صفين، كربلاء، الحرة
```

The shape is historically coherent: بدر is by far the most-cited dated event in the
corpus (1,718 hadiths), followed by فتح مكة, خيبر, أحد and حجة الوداع — exactly the
events with the richest narrative coverage in the collections.

### 3.3 Top companion windows

| Companion | Window (marfūʿ) | Hadiths |
|---|---|---|
| أبو هريرة | 7 → 11 AH | 19,418 |
| عبد الله بن عباس | 8 → 11 AH | 13,918 |
| أنس بن مالك | 1 → 11 AH | 11,561 |
| عبد الله بن عمر | 1 → 11 AH | 10,488 |
| عائشة أم المؤمنين | 2 → 11 AH | 8,086 |
| جابر بن عبد الله | 1 → 11 AH | 7,167 |
| أبو سعيد الخدري | 3 → 11 AH | 2,781 |
| عبد الله بن عمرو بن العاص | 7 → 11 AH | 2,479 |
| عبد الله بن مسعود | −13 → 11 AH | 2,350 |
| أم سلمة | 4 → 11 AH | 1,412 |

Notably, **the two most prolific narrators (أبو هريرة, ابن عباس) have the narrowest
direct-audition windows** (4 and 3 years) — the classical observation that much of
their corpus is mediated through other Companions, made quantitative.

### 3.4 Seasonal anchors

رمضان 3,885 · موسم الحج 2,324 · العيد 649.

### 3.5 Coverage by collection (top 12)

| Collection | Units | Dated | % |
|---|---|---|---|
| مصنف ابن أبي شيبة | 39,098 | 6,025 | 15% |
| مسند أحمد | 28,245 | 13,542 | 48% |
| المعجم الكبير | 23,377 | 8,455 | 36% |
| سنن البيهقي الكبرى | 21,891 | 7,535 | 34% |
| مصنف عبد الرزاق | 21,109 | 3,352 | 16% |
| السنن الكبرى | 11,982 | 5,639 | 47% |
| مسند البزار | 10,417 | 5,516 | 53% |
| المعجم الأوسط | 9,499 | 5,782 | 61% |
| المستدرك | 8,920 | 3,700 | 41% |
| صحيح مسلم | 7,666 | 3,548 | 46% |
| مسند أبي يعلى | 7,561 | 3,924 | 52% |
| صحيح ابن حبان | 7,499 | 4,573 | 61% |

The muṣannafāt (ابن أبي شيبة, عبد الرزاق) date poorly (15–16%) because they are
dominated by mawqūf/maqṭūʿ āthār of tābiʿīn outside the curated Companion list — an
expected and structurally informative result. Musnad-type collections (organized by
Companion) date best.

### 3.6 Validation examples

- **بدر (2 AH):** صحيح البخاري #3008 — «…سمع جابر بن عبد الله قال: لما كان يوم بدر أُتي
  بأسارى…» → event+companion (جابر window 1–11 ∋ 2), confidence 0.9.
- **حجة الوداع (10 AH):** صحيح البخاري #83 — عبد الله بن عمرو: «وقف النبي ﷺ في حجة
  الوداع…» → 10 AH, confidence 0.95.
- **تبوك (9 AH):** صحيح البخاري #3378 — ابن عمر: «أن رسول الله ﷺ لما نزل الحِجر في
  غزوة تبوك…» → 9 AH.

### 3.7 Confidence profile

92,658 rows at 0.40 (companion windows), 3,763 at 0.30 (season only), 8,974 event-based
rows between 0.55 and 0.95 (median 0.80).

---

## 4. Limitations & caveats

1. **These are indicative machine estimates, not scholarly dating.** An event mention
   can be narration *context* rather than origination time («سمعت هذا بعد يوم الجمل»),
   and the strongest available signal is chosen mechanically.
2. **61.9% of units carry no signal at all** — most hadiths simply contain no temporal
   clue; absence of a date is the honest default.
3. Companion windows use **direct-audition assumptions**; Companions also transmitted
   from each other (مراسيل الصحابة), so a report can predate the narrator's own
   companionship (e.g. أبو هريرة narrating events of بدر).
4. Companionship-start years are approximations from classical sources; death years of
   several Companions are disputed (±1–3 years).
5. The event lexicon is precision-first: rare or ambiguous events (بئر معونة, ذات
   الرقاع, الحديبية-as-place) are either omitted or context-guarded, trading recall for
   accuracy.
6. Only **hadith units** (Jamiʿ collections) are analyzed; Shamela commentary pages are
   excluded on purpose (their event mentions are overwhelmingly exegetical).

## 5. Future work

- **LLM extraction pass** (gemini-flash) over the ~9k event-matched hadiths to verify
  the event is the *setting* of the report and to catch phrasings the regexes miss.
- Enrich `narrators.death_year_h` from the rijāl corpus (تقريب التهذيب is already
  loaded as a Shamela edition) to extend tier 3 beyond the curated 40 Companions and
  to date mawqūf/maqṭūʿ reports by tābiʿī lifespans.
- Chain-depth chronology: estimate narration (not origination) time per link using
  average generation spans, giving each hadith a transmission time-path.
- Cross-check event vs. companion inconsistencies (event year outside the narrator's
  window) as an isnād-criticism signal.

## 6. Reproduction

```powershell
# local (writes timeline_events + hadith_dates, prints the report statistics)
python ops/analyze_timeline.py

# Railway
$env:DATABASE_URL = $env:RAILWAY_PG_URL; python ops/analyze_timeline.py
```

UI: **الخط الزمني** tab → year chart (click a year), event list by era, season chips,
companion windows (click any bucket for the hadith drill-down list).
