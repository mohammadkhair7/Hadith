# Hadith.chat ↔ Alifta.chat — Data & Architecture Comparison

**Date:** 2026-08-19
**Scope:** relationship between the two source websites, the two SQLite databases we
built from them, verified ID-space equivalence, and concrete SQL join strategies for
a future combined platform.

---

## 1. The two source websites

| | the sunna portal (→ Hadith.chat) | the legacy archive portal (→ Alifta.chat) |
|---|---|---|
| Official name | جامع خادم الحرمين الشريفين للسنة النبوية المطهرة | same program, same publisher |
| Publisher | الرئاسة العامة للبحوث العلمية والإفتاء (developed by Harf) | same |
| Technology | live ASP.NET MVC app (`/BookToc/ViewMatnPage` etc.) | **retired** ASP.NET WebForms app, now a static archive |
| State today | fully dynamic and crawlable | only ~45 sitemap pages served; postbacks/paging/trees dead |
| Corpus | 33 matn books + 57 service books, full text | same corpus (site self-describes: 33 matn + 55 service) but full text no longer served |
| Extra features | subjects tree (مكانز), FTS search, book cards | narrator DB (رواة), أطراف, أسانيد, معاجم, إحصائيات — **data unreachable**, only first-page samples remain |

**Key conclusion:** they are two generations of the *same* product over the *same*
database. The sunna portal is the modern replacement; the archive portal is the legacy
front-end frozen as a static snapshot.

## 2. Verified equivalence of the ID spaces

This is the load-bearing finding for any future join. Three independent proofs:

1. **BookID space is identical.** Deep URLs recovered from the archive portal
   (`viewhadith_bookid_50_method_2_mainid_489991_hadithtype_service.html`) use
   BookID 50 for الكاشف للذهبي — the same ID the sunna site uses and the same ID in
   `hadith.db.books`. The `hadithtype` (`matn`/`service`) also matches our
   `books.book_type` split.
2. **MainID (page/node) space is identical.** Of the 12 preserved deep pages on
   the archive portal, 9 mainids resolve **directly** in `hadith.db.toc`/`hadith.db.matn`
   with the same book and the same entry title (e.g. mainid `440802` → book 48,
   leaf «أبان بن صمعة الأنصاري البصري…», identical text). The 3 misses are in
   books our sunna crawl has not reached yet (61, 83) — explained by crawl
   progress, not ID mismatch.
3. **Text is identical.** Page content fetched from both sites for book 50
   matches verbatim (same entries, same part/page markers `[2/39]`).

**Caveat:** the visible row number («م») in the archive portal's books grid is a *display
order* (Bukhari, Muslim, Abu Dawud, Tirmidhi, Nasa'i, **السنن الكبرى**, Ibn Majah…)
and does **not** equal BookID. Always join on BookID/MainID, never on display order.

An additional ID observed only on the archive portal: `sayid` (e.g.
`sayid_48001406` = قول/entry id inside a page). Format appears to be
`{bookid:02d}{sequence:06d}`. If asanid/aqwal data is ever recovered, `sayid`
would be the finest-grained join key.

## 3. Database architecture

### 3.1 `Hadith.chat/data/hadith.db` (the full corpus)

| Table | Purpose | Scale |
|---|---|---|
| `books(id, name, ord, details_html, toc_done, book_type, section_id, section_name)` | 33 matn + 57 service books; `book_type` ∈ {matn, service}; service books grouped by section | 90 rows |
| `toc(book_id, node_id, parent_id, title, is_leaf, ord, expanded)` | full TOC tree per book; leaves = readable pages | 622,658 rows |
| `matn(book_id, main_id, html, text_plain, hadith_num, part_page, prev_id, next_id, status, fetched_at)` | page content (hadith text or service-book entry) | 382,576 pages stored |
| `subjects(node_id, parent_id, title, is_leaf, ord, expanded, hits_done)` | subject thesaurus (مكانز موضوعية) | 21,994 rows |
| `subject_hits(subject_id, book_id, main_id, ord)` | subject → hadith links | 1,138,369 rows |
| `matn_fts` (FTS5, in-app) | normalized diacritic-insensitive search index | mirrors `matn` |

Primary keys: `toc(book_id, node_id)`, `matn(book_id, main_id)`.
`toc.node_id = matn.main_id` for leaves — this **is** the MainID of both websites.

### 3.2 `Alifta.chat/data/alifta.db` (the archive)

| Table | Purpose | Scale |
|---|---|---|
| `pages(slug, url, section, ord, title, note, content_html, text_plain, text_norm, fetched_at)` | one row per preserved archive page, organized by the original site's menu sections | 40 rows, ~118K searchable chars |
| `meta(key, value)` | build info / provenance | 2 rows |

The archive's value is **reference material** the sunna site does not expose:
complete tables of أطراف availability per book, متفق وزوائد statistics (66 rows),
narrator statistics, ألفاظ الجرح والتعديل, تعريفات المصطلح, first-page samples of
the narrator database, and root levels of three thesaurus trees.

## 4. Feature overlap and complementarity

```
                     the sunna portal           the legacy archive portal
Full book text       ✔ hadith.db.matn           ✖ (11 sample pages only)
TOC trees            ✔ hadith.db.toc            ✖ (dead postbacks)
Subjects thesaurus   ✔ subjects/subject_hits    △ root level snapshot
Narrator database    ✖ (not exposed)            △ first page + statistics
Atraf / Asanid       ✖ (not exposed)            △ lists + statistics + samples
Lexicons (معاجم)     ✖                          △ root letters snapshot
Hadith-science apps  ✖                          △ definitions (full), أمثال, أقوال
Statistics tables    ✖                          ✔ complete (3 pages)
```

✔ complete △ partial ✖ absent

So the merge story is: **hadith.db carries the corpus, alifta.db carries the
legacy reference/statistics layer**. Nothing overlaps destructively; alifta.db
enriches around the edges.

## 5. SQL join strategies

SQLite `ATTACH` makes cross-database queries trivial:

```sql
ATTACH DATABASE 'e:/Quran Computing Institute/Hadith.chat/data/hadith.db'  AS h;
ATTACH DATABASE 'e:/Quran Computing Institute/Hadith.chat/AdvancedHadith/data/hadith_struct.db' AS a;
```

### 5.1 Resolve an archive page to the live corpus

The stray `viewhadith_*` slugs encode `(bookid, mainid)`; both resolve in hadith.db:

```sql
-- example: slug 'viewhadith_bookid_50_..._mainid_489991_...'
SELECT h.matn.text_plain, h.toc.title, h.books.name
FROM h.matn
JOIN h.toc   ON h.toc.book_id = h.matn.book_id AND h.toc.node_id = h.matn.main_id
JOIN h.books ON h.books.id = h.matn.book_id
WHERE h.matn.book_id = 50 AND h.matn.main_id = 489991;
```

Recommendation: add a small mapping table to the archive db at merge time:

```sql
CREATE TABLE a.page_refs(slug TEXT, book_id INT, main_id INT, say_id INT);
-- populated by parsing slugs + any (bookid, mainid) URLs inside content_html
```

### 5.2 Book-level enrichment (statistics → books)

The alifta statistics tables mention books by *name*. Names match hadith.db
`books.name` closely (same titles, minor spacing/author-suffix differences), so a
normalized-name match table is the right bridge:

```sql
CREATE TABLE a.book_map(alifta_name_norm TEXT PRIMARY KEY, book_id INT);
-- seeded once with normalize_arabic(name) from both sides + manual review
SELECT b.name, s.*            -- attach zawa'id statistics to each book page
FROM h.books b
JOIN a.book_map m ON m.book_id = b.id
JOIN parsed_stats s ON s.name_norm = m.alifta_name_norm;
```

(`parsed_stats` = rows extracted from `a.pages.content_html` for the three
statistics pages; extraction is a simple `<tr class="raw01|raw02">` parse.)

### 5.3 Unified search across both databases

```sql
SELECT 'hadith' AS src, book_id, main_id, snippet(matn_fts, ...) FROM h.matn_fts WHERE matn_fts MATCH :q
UNION ALL
SELECT 'alifta' AS src, NULL, NULL, substr(text_plain, instr(text_norm, :qn) - 60, 240)
FROM a.pages WHERE text_norm LIKE '%' || :qn || '%';
```

Both projects already use the **same Arabic normalization** (identical
`normalize_arabic` implementation), so a shared query string works unchanged.

### 5.4 Subjects tree cross-check

`a.pages.slug = 'viewsubjecttree'` holds the archived root level of the same
thesaurus stored fully in `h.subjects` — usable as a validation fixture
(root titles should match `h.subjects WHERE parent_id = 1`).

## 6. Suggested integration roadmap

1. **Phase 0 (now):** two independent apps — Hadith.chat :8000, Alifta.chat :8001. ✅
2. **Phase 1:** parse the three complete statistics tables + أطراف lists out of
   `a.pages.content_html` into typed tables (`a.book_stats`, `a.atraf_books`),
   seed `a.book_map` by normalized name.
3. **Phase 2:** in Hadith.chat book cards, show the alifta-derived statistics via
   `ATTACH` (read-only) — the first user-visible merge.
4. **Phase 3:** unified search endpoint (5.3) and cross-links: hadith reader pages
   link to matching archive pages when `(book_id, main_id)` appears in `a.page_refs`.
5. **Phase 4 (optional):** if the narrator/asanid data ever becomes reachable
   (site revival or another mirror), its natural home is new tables keyed by
   `sayid`/`rwahid` joined to `matn(book_id, main_id)`.

## 7. Risks / notes

- **Display order ≠ BookID** (see §2 caveat) — never map by row position.
- alifta.db text is entity-decoded during build; hadith.db stores raw Arabic —
  both normalize identically for search, so joins on *text* should always use
  `text_norm`-style comparison.
- The alifta archive can only shrink, not grow: re-fetch (`fetch_pages.py`) is
  cheap and safe, and `data/raw/` preserves original HTML for future re-parsing.
- The 4 permanently-failed sunna pages (books 1, 24, 25) are broken at the source
  and equally absent from the archive portal.

## 8. Coverage test results (2026-08-19)

To settle whether the archive portal could backfill hadith.db's missing service-book
content, `recon/coverage_test.py` probed 19 concrete missing pages (the 4
corrupt matn pages + 3 random missing leaves from each of books 43, 47, 56,
57, 80) against the mirror's static URL scheme, in both `hadithtype_service`
and `hadithtype_matn` forms and both `method_1`/`method_2` variants.

**Result: 0/19 hits.** Every URL returned the identical 1,159-byte JS redirect
shim. The mirror serves only its ~45 sitemap-listed snapshots; it cannot
supply any missing content. The sunna portal remains the sole source.

The transfer that *was* possible ran in the other direction
(`recon/import_archived.py`): of the 12 archived deep hadith snapshots in
alifta.db, 9 duplicated content hadith.db already had (verifying the shared ID
space end-to-end), and **3 were imported into hadith.db** — book 61 mainids
685461 and 685463, and book 83 mainid 832828 (251,936 chars) — pages from
service books not yet crawled.
