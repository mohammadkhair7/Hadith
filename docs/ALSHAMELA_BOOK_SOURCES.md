# Al-Shamela Book Sources — Mapping & Loading Plan

**Status: PLAN — awaiting approval. No book is loaded until the mappings below are reviewed and approved.**

Goal: every work in AdvancedHadith should have **two parallel editions** — the aljam3
(sunna crawl) edition and an Al-Maktaba Al-Shamela page edition — so the reader
can switch editions and the compare view can diff them. Today 40 works have a
shamela edition; **50 works are aljam3-only**. This plan identifies the exact
Shamela source (archive, bkid, author, CSV path) for each missing book and the
full preprocessing pipeline each one goes through.

---

## 1. Reference data on disk

| Source | Path | Notes |
|---|---|---|
| Shamela index (12,302 unique books) | `E:\Quran Computing Institute\Hadith.chat\- no duplicates فهرس الشاملة 3.xlsx` | sheet `Books`: archive, bkid, title, betaka, category, pages, author |
| 2017 CSV export (archives 1–28) | `E:\Al-Maktaba Al-Shamela 2017\CSV\<archive>\b<bkid>.csv` | one row per printed page; columns vary per book (`nass`, `id`, `part`, `page`, optional `hno`/`sora`/`aya`), parsed by header — **primary source, proven tooling** |
| 2023 download, archive 0 | `E:\Al-Maktaba Al-Shamela 2023\Download\shamela=12300\Books\0\<n>.mdb` | per-book MS-Access files; needed only for archive-0 editions (none of the recommendations below require it) |
| 2023 download, archives 1–28 | `E:\Al-Maktaba Al-Shamela 2023\Download\shamela=12300\Books\Archive\<archive>.mdb` | whole-archive Access files; fallback if a CSV turns out corrupt |

All recommended picks below were **verified to exist** as
`E:\Al-Maktaba Al-Shamela 2017\CSV\<archive>\b<bkid>.csv` (53/53 files present,
including alternates).

## 2. Tooling already built (used for the first 40 books)

Identification & staging — `E:\Quran Computing Institute\Hadith.chat\Al-Shamela\`:

| Script | Purpose |
|---|---|
| `shamela_index.py` | inspect the Excel index structure |
| `match_books.py` | fuzzy-match books needing content against the index (token cover/precision scoring) |
| `search_index.py` | targeted keyword lookup in the index |
| `book_map.py` | **the confirmed mapping** `hadith_book_id → (archive, bkid, note)` — the approval artifact |
| `build_alshamela.py` | build/refresh `alshamela.db` (SQLite staging DB) from the CSVs; header-driven parsing, `nass_norm`, resumable per book |
| `evaluate_matches.py` | text-overlap verification of mapped books vs aljam3 content (letters-only normalized comparison) |
| `extract_pdf_book86.py` | special case: extract a book absent from Shamela from an OCR PDF |

Load & postprocess — `AdvancedHadith\`:

| Script | Purpose |
|---|---|
| `etl/load_shamela.py` | load `alshamela.db` → Postgres `editions` + `passages` (attaches to the same work as the aljam3 edition via `books.hadith_book_id`; `\r`→`\n`; `normalize_arabic` → `text_norm`; COPY; resumable via `etl_state`) |
| `ops/build_shamela_toc.py` | generate the TOC from in-text headings (كتاب/أبواب/سورة → depth 1, باب → 2, فصل/مقدمة/bracketed/§ → 3), anchor pages to nodes |
| `ops/index_validate.py` | TOC sanity checks |
| `python -m arabiclib.neural.tashkeel bulk` | neural tashkeel for **fully-bare words only** over all shamela editions → `passage_annotations`; resumable per edition (`etl_state` step `tashkeel<v>_edition_<id>`) |
| `backend embed_jobs` (Admin → Embeddings, or `ops/pilot_embed.py` pattern) | chunk + embed passages into Redis for semantic/hybrid search |
| `ops/railway_push_annotations.py` | upsert locally computed `passage_annotations` to Railway |
| `ops/etl_progress.py` | progress ledger view |

## 3. Part A — books already loaded (40 works, 276k+ pages)

Format: aljam3 book id → (archive, bkid); CSV path is `E:\Al-Maktaba Al-Shamela 2017\CSV\<archive>\b<bkid>.csv`.

| aljam3 # | Shamela edition (note) | archive | bkid | pages loaded |
|---|---|---|---|---|
| 1 | صحيح البخاري | 20 | 32027 | 7,636 |
| 24 | المستدرك على الصحيحين للحاكم | 7 | 2266 | 9,702 |
| 25 | الأحاديث المختارة للمقدسي | 7 | 10480 | 4,749 |
| 34 | فتح الباري لابن حجر | 6 | 1673 | 7,807 |
| 36 | عون المعبود ط السلفية | 21 | 33531 | 8,717 |
| 37 | تحفة الأحوذي | 12 | 1163 | 4,874 |
| 38 | شرح ابن ماجه لمغلطاي | 2 | 8544 | 1,688 |
| 40 | حاشية السيوطي على سنن النسائي | 2 | 360 | 1,125 |
| 41 | التمهيد لابن عبد البر | 1 | 1719 | 8,345 |
| 42 | فتح الباري لابن رجب | 2 | 137 | 4,835 |
| 43 | عمدة القاري | 2 | 5756 | 7,603 |
| 44 | المفهم للقرطبي (مرقم آليا) | 21 | 35976 | 3,527 |
| 45 | الاستذكار ت قلعجي | 21 | 33530 | 9,246 |
| 46 | شرح الزرقاني على الموطأ | 21 | 33529 | 2,136 |
| 47 | الإصابة في تمييز الصحابة | 16 | 9767 | 4,406 |
| 56 | الثقات لابن حبان ط الفكر | 24 | 34650 | 17,279 |
| 57 | تاريخ الإسلام ت بشار | 8 | 223 | 34,544 |
| 60 | تحفة التحصيل | 15 | 5838 | 370 |
| 61 | الجرح والتعديل | 13 | 2170 | 4,229 |
| 63 | نصب الراية | 3 | 11428 | 2,019 |
| 64 | التلخيص الحبير ط العلمية | 3 | 1581 | 2,464 |
| 65 | البدر المنير | 3 | 5922 | 6,130 |
| 70 | مقدمة ابن الصلاح ت عتر | 6 | 125 | 405 |
| 71 | نخبة الفكر | 4 | 5940 | 18 |
| 74 | علل الحديث لابن أبي حاتم | 4 | 1350 | 4,011 |
| 75 | علل الدارقطني | 4 | 9082 | 6,688 |
| 76 | الطب النبوي لابن القيم | 7 | 23649 | 318 |
| 78 | النهاية في غريب الحديث والأثر | 18 | 23691 | 2,157 |
| 79 | لسان العرب | 13 | 1687 | 8,101 |
| 80 | معجم البلدان | 17 | 23735 | 3,522 |
| 81 | السيرة النبوية لابن هشام ت سعد | 24 | 34440 | 1,606 |
| 82 | تاريخ بغداد ت بشار | 11 | 736 | 8,668 |
| 83 | فتح المغيث | 4 | 5963 | 1,419 |
| 84 | تفسير الطبري ت شاكر | 1 | 43 | 14,577 |
| 87 | البدور الزاهرة | 5 | 57 | 363 |
| 88 | مجمع الزوائد | 12 | 1530 | 3,485 |
| 89 | حاشية السندي على سنن النسائي | 2 | 522 | 2,103 |
| 90 | إتحاف المهرة لابن حجر | 3 | 26324 | 31,913 |
| 93 | تحفة الأشراف للمزي | 3 | 11385 | 28,767 |
| 86 | الأزهار المتناثرة (السيوطي) — **not in Shamela**; extracted from OCR PDF, synthetic bkid | — | 900086 | 189 |

## 4. Part B — proposed new mappings (50 works) — **FOR APPROVAL**

Candidates were scored against the index with the same token-matching used for
Part A (`match_books.py` logic), then curated by hand: edition choice prefers
(1) the standard/scholarly edition, (2) page count closest to the aljam3
version, (3) archives 1–28 (CSV available). `p` = index page count; aljam3
page count shown for comparison.

### 4.1 Matn books (30)

| Work | aljam3 # (pages) | Recommended: archive / bkid / edition / author | p | CSV path (`…2017\CSV\`) |
|---|---|---|---|---|
| صحيح مسلم | 2 (7,666) | 12 / 1161 / ت محمد فؤاد عبد الباقي / مسلم | 8,941 | `12\b1161.csv` |
| سنن أبي داود | 3 (5,260) | 9 / 1160 / ط المكتبة العصرية / أبو داود السجستاني | 7,206 | `9\b1160.csv` |
| جامع الترمذي | 4 (4,412) | 7 / 1159 / سنن الترمذي ت شاكر (الترقيم القياسي) / الترمذي | 6,464 | `7\b1159.csv` |
| سنن النسائي (المجتبى) | 5 (5,780) | 13 / 829 / ت أبو غدة / النسائي | 8,349 | `13\b829.csv` |
| السنن الكبرى للنسائي | 22 (11,982) | 13 / 1240 / ط الرسالة / النسائي | 16,332 | `13\b1240.csv` |
| سنن ابن ماجه | 6 (4,467) | 5 / 1198 / ت عبد الباقي / ابن ماجه | 5,948 | `5\b1198.csv` |
| موطأ مالك | 7 (1,781) | 11 / 1143 / ت الأعظمي / مالك بن أنس | 5,303 | `11\b1143.csv` |
| مسند الطيالسي | 21 (2,897) | 5 / 1456 / ت التركي / أبو داود الطيالسي | 3,505 | `5\b1456.csv` |
| مصنف عبد الرزاق | 16 (21,109) | 9 / 31637 / ت الأعظمي / عبد الرزاق الصنعاني | 20,977 | `9\b31637.csv` |
| مسند الحميدي | 20 (1,335) | 5 / 8493 / ت الدارانية / الحميدي | 1,428 | `5\b8493.csv` |
| سنن سعيد بن منصور | 30 (4,155) | 5 / 13122 / ت الأعظمي / سعيد بن منصور | 3,074 | `5\b13122.csv` |
| مصنف ابن أبي شيبة | 15 (39,098) | 11 / 31642 / ت الحوت / ابن أبي شيبة | 42,755 | `11\b31642.csv` |
| مسند أحمد | 8 (28,245) | 5 / 13157 / مسند أحمد مخرجا / أحمد بن حنبل | 28,392 | `5\b13157.csv` |
| مسند عبد بن حميد | 29 (1,594) | 5 / 13170 / المنتخب ت السامرائي / عبد بن حميد | 1,751 | `5\b13170.csv` |
| مسند الدارمي | 9 (3,541) | 12 / 1223 / سنن الدارمي (نفس الكتاب) / الدارمي | 4,840 | `12\b1223.csv` |
| المراسيل لأبي داود | 32 (543) | 5 / 13063 / ط الرسالة / أبو داود | 628 | `5\b13063.csv` |
| الشمائل المحمدية | 33 (415) | 24 / 38142 / ط الصديق / الترمذي | 416 | `24\b38142.csv` |
| مسند البزار | 19 (10,417) | 6 / 12981 / البحر الزخار / البزار | 9,656 | `6\b12981.csv` |
| المنتقى لابن الجارود | 27 (1,154) | 6 / 13071 / — / ابن الجارود | 1,258 | `6\b13071.csv` |
| مسند أبي يعلى | 23 (7,561) | 9 / 31634 / ت حسين أسد / أبو يعلى الموصلي | 7,644 | `9\b31634.csv` |
| صحيح ابن خزيمة | 11 (3,413) | 6 / 1446 / ت الأعظمي / ابن خزيمة | 5,117 | `6\b1446.csv` |
| شرح معاني الآثار | 28 (7,051) | 6 / 21108 / عالم الكتب / الطحاوي | 5,323 | `6\b21108.csv` |
| شرح مشكل الآثار | 31 (7,274) | 6 / 22547 / ت الأرنؤوط / الطحاوي | 6,453 | `6\b22547.csv` |
| صحيح ابن حبان | 10 (7,499) | 6 / 1729 / محققا ط الرسالة / ابن حبان | 11,225 | `6\b1729.csv` |
| المعجم الكبير | 12 (23,377) | 6 / 1733 / ت السلفي / الطبراني | 26,616 | `6\b1733.csv` |
| المعجم الأوسط | 13 (9,499) | 6 / 28171 / دار الحرمين / الطبراني | 9,899 | `6\b28171.csv` |
| المعجم الصغير | 14 (1,203) | 6 / 13068 / الروض الداني / الطبراني | 1,378 | `6\b13068.csv` |
| سنن الدارقطني | 18 (4,840) | 13 / 1224 / ط الرسالة / الدارقطني | 4,544 | `13\b1224.csv` |
| السنن الكبرى للبيهقي | 17 (21,891) | 11 / 31640 / ت عطا ط العلمية / البيهقي | 37,008 | `11\b31640.csv` |
| المطالب العالية | 26 (5,603) | 3 / 22804 / بزوائد المسانيد الثمانية / ابن حجر | 6,613 | `3\b22804.csv` |

Alternates worth considering (same works):

- جامع الترمذي: `12\b1201.csv` — ت بشار عواد (p 6,961), أكمل تحقيقًا لكن ترقيمه يختلف عن المعتمد.
- مسند أحمد: `6\b25794.csv` — ط الرسالة (p 23,350), أدق تحقيقًا؛ «مخرجا» أقرب حجمًا لنسخة aljam3.
- مصنف ابن أبي شيبة: `20\b33967.csv` — ت عوامة (p 35,322).
- صحيح ابن حبان: `6\b60.csv` — مخرجا (p 15,098).
- المطالب العالية: `12\b31850.csv` — «محققا» ط العاصمة/الغيث ‏(p 22,025) أشمل بكثير.
- سنن سعيد بن منصور: مجلدا التفسير منفصلان في الشاملة (`5\b1254.csv`, `5\b13008.csv`) — يمكن إلحاقهما لاحقًا.
- موطأ مالك: رواية يحيى ت عبد الباقي موجودة فقط في archive 0 (`Books\0`, bkid 40192, mdb) — تتطلب مسار استخراج Access.

### 4.2 Analysis books (20)

| Work | aljam3 # (pages) | Recommended: archive / bkid / edition / author | p | CSV path |
|---|---|---|---|---|
| تهذيب الكمال | 48 (11,497) | 15 / 3722 / ط الرسالة ت بشار / المزي | 19,037 | `15\b3722.csv` |
| تهذيب التهذيب | 49 (12,259) | 16 / 3310 / ط دائرة المعارف النظامية / ابن حجر | 6,393 | `16\b3310.csv` |
| الكاشف | 50 (8,355) | 15 / 2171 / ت عوامة / الذهبي | 1,220 | `15\b2171.csv` |
| تقريب التهذيب | 51 (12,071) | 16 / 8609 / ت عوامة / ابن حجر | 692 | `16\b8609.csv` |
| إكمال تهذيب الكمال | 52 (5,228) | 9 / 329 / ت أبو المعاطي / مغلطاي | 4,787 | `9\b329.csv` |
| لسان الميزان | 53 (15,505) | 11 / 1041 / ت أبي غدة / ابن حجر | 16,770 | `11\b1041.csv` |
| الكامل في الضعفاء | 54 (2,333) | 13 / 12579 / ط العلمية / ابن عدي | 4,520 | `13\b12579.csv` |
| تعجيل المنفعة | 55 (1,733) | 16 / 1893 / ت إكرام الله / ابن حجر | 2,693 | `16\b1893.csv` |
| الكواكب النيرات | 58 (71) | 16 / 309 / ت عبد القيوم / ابن الكيال | 549 | `16\b309.csv` |
| تعريف أهل التقديس (طبقات المدلسين) | 59 (155) | 16 / 1186 / ت القريوتي / ابن حجر | 72 | `16\b1186.csv` |
| سير أعلام النبلاء | 62 (6,206) | 15 / 10906 / ط الرسالة / الذهبي | 14,563 | `15\b10906.csv` |
| الفصل للوصل المدرج | 68 (112) | 4 / 10842 / — / الخطيب البغدادي | 958 | `4\b10842.csv` |
| تأويل مختلف الحديث | 69 (149) | 1 / 7292 / — / ابن قتيبة | 516 | `1\b7292.csv` |
| البيان والتعريف | 72 (1,840) | 2 / 6000 / — / ابن حمزة الحسيني | 640 | `2\b6000.csv` |
| الاعتبار في الناسخ والمنسوخ | 73 (154) | 4 / 22868 / — / الحازمي | 246 | `4\b22868.csv` |
| أمثال الحديث | 77 (123) | 1 / 13083 / — / الرامهرمزي | 164 | `1\b13083.csv` |
| معجم المعالم الجغرافية | 95 (458) | 1 / 937 / — / عاتق البلادي | 346 | `1\b937.csv` |
| المنهاج شرح صحيح مسلم | 35 (3,262) | 1 / 1711 / شرح النووي على مسلم / النووي | 4,087 | `1\b1711.csv` |
| حاشية السندي على ابن ماجه | 39 (4,276) | 2 / 9810 / — / السندي | 5,539 | `2\b9810.csv` |
| شرح مشكل الآثار (المكرر) | 85 (1,004) | ⚠ نفس كتاب W-24 أعلاه (bkid 22547) — **انظر 4.3** | — | — |

Alternates: سير أعلام النبلاء ط الحديث `16\b22669.csv` (p 10,265); لسان الميزان ط النظامية `16\b12063.csv` (p 4,148).

### 4.3 Flags needing a decision

1. **Duplicate work — شرح مشكل الآثار**: work 24 (aljam3 #31, 7,274 pages) and
   work 61 (aljam3 #85, 1,004 pages) are both titled شرح مشكل الآثار للطحاوي.
   Both would map to the same Shamela book (bkid 22547). Recommendation:
   attach the Shamela edition to work 24 only, and investigate whether
   aljam3 #85 is a partial duplicate that should be merged into work 24
   (or is actually a different selection, e.g. المعتصر).
2. **تهذيب الكمال sizes**: the Shamela ط الرسالة (19,037 pp) is much larger than
   aljam3 (11,497) — expected (35 vols with indexes); fine to load.
3. **الكاشف/تقريب التهذيب sizes**: aljam3 paginates per-entry (8k/12k rows) while
   Shamela paginates per printed page (1,220/692) — expected, not an error.
4. **Two works remain aljam3-less by design**: الجرح والتعديل (work 48) and
   فتح المغيث (work 55) exist only as Shamela editions (their aljam3 crawls had
   no content and the stubs were removed). No action needed.
5. **Volume**: the 49 recommended books total **≈ 383,000 pages** — this more
   than doubles the current 276k Shamela pages. Load order below is chosen so
   the six canonical books go first.

## 5. Preprocessing pipeline (per approved book)

Steps run in this order; every step is resumable and already implemented —
no new tooling is required except registering the mappings.

1. **Register mapping** — add `hadith_book_id: (archive, bkid, note)` to
   `Al-Shamela\book_map.py` (`BOOK_MAP`).
2. **Stage into `alshamela.db`** — `python Al-Shamela\build_alshamela.py`.
   Header-driven CSV parsing (`nass`/`id`/`part`/`page` + optional
   `hno`/`sora`/`aya`), computes `nass_norm`, resumable (books already loaded
   with expected counts are skipped). Log: `build-log.txt`.
3. **Verify identity** — `python Al-Shamela\evaluate_matches.py` for books where
   aljam3 has text: sampled pages must match the mapped Shamela book on
   letters-only normalized comparison (the first 40 books scored 100%).
   Fix any mismatch before loading.
4. **Load into Postgres** — `python etl\load_shamela.py` (from `AdvancedHadith\`).
   Attaches the edition to the existing work via the aljam3 edition
   (`source='sunna' AND source_book_id=<hadith_book_id>`), converts bare `\r`
   to `\n` (page-context/offset-safe), fills `text_norm` via `normalize_arabic`,
   COPY-bulk inserts, marks `etl_state` per book.
5. **Build the book index (TOC)** — `python ops\build_shamela_toc.py --edition <id>`.
   Classifies in-text headings (كتاب/أبواب/سورة/تفسير سورة → depth 1؛ باب → 2؛
   فصل/مقدمة/خاتمة/مسألة/‏[أقواس]/§ → 3), anchors every page to its TOC node,
   sets leaf flags. Validate with `ops\index_validate.py`. The reader side
   panel then shows the index with the root expanded.
6. **Markdown-style display** — automatic: the reader renders shamela pages
   through the block renderer (`pageBlocks` + `FormattedPage`): styled heading
   levels, hadith-number highlighting, Quran-quote highlighting. Spot-check a
   few pages per book. aljam3 editions keep their native pre-formatted display.
7. **Hadith identification / matn indication** — automatic heuristics on
   display (sanad → matn boundary highlighting, hadith segmentation) plus the
   `hno` per-page metadata preserved from the CSV. No per-book work; verify
   using a couple of hadith-bearing pages.
8. **Tashkeel (bare words only)** — `python -m arabiclib.neural.tashkeel bulk`
   (from `Arabic-lib\`). Adds model diacritics **only to fully-bare words**,
   preserving all author-supplied tashkeel; writes the diacritized display
   layer to `passage_annotations`; resumable per edition. NOTE: a bulk run
   over the existing 40 editions is currently in progress on the GPU — new
   editions simply extend the same ledger and get picked up by a re-run.
9. **Embeddings (semantic search)** — start an embed job per new edition from
   Admin → Embeddings (or the `embed_jobs.start_job([...])` CLI pattern in
   `ops\pilot_embed.py`), so the new pages participate in
   semantic/hybrid search.
10. **Validation pass** — page counts vs index expectation, TOC node counts,
    tashkeel/matn toggle smoke test in the reader, search hit test.
11. **Production (Railway)** — run steps 4–5 against Railway
    (`DATABASE_URL` swapped from `RAILWAY_PG_URL`, never printed), then push
    tashkeel layers with `ops\railway_push_annotations.py`, and run embed jobs
    against production once the data is live.

Analytics note: narrator graph, timeline, and hadith-type analytics are
computed from aljam3 `unit` passages, so loading page-archive editions does
not disturb them; the search index, reader, and compare views gain the
new content.

## 6. Suggested load order

1. **The six canonical books** (مسلم، أبو داود، الترمذي، النسائي، ابن ماجه، الموطأ) — highest reader value.
2. Remaining matn books, smallest first (المراسيل، الشمائل، الحميدي، المنتخب، المعجم الصغير، المنتقى…), the giants last (مصنف ابن أبي شيبة، السنن الكبرى للبيهقي، المعجم الكبير، مسند أحمد).
3. Analysis books (rijāl/ʿilal/shurūḥ), smallest first.
4. Flags in §4.3 resolved as decided during approval.

## 7. Approval checklist

- [ ] Part B §4.1 matn mappings approved (or edition swaps noted per row)
- [ ] Part B §4.2 analysis-book mappings approved
- [ ] §4.3 flag 1: شرح مشكل الآثار duplicate — merge W61 into W24? or map separately?
- [ ] Choice of alternates (الترمذي ت شاكر vs ت بشار؛ مسند أحمد مخرجا vs ط الرسالة؛ المطالب العالية العادية vs المحققة)
- [ ] Load order approved
- [ ] Approval to run the pipeline locally, then on Railway
