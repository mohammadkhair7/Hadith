# Shamela book pipeline — the complete command playbook

Every command needed to take one Shamela book from CSV export to fully
prepared, uploaded, and verified — locally and on Railway. This is the
operational companion to `ALSHAMELA_BOOK_SOURCES.md` (which holds the book
mappings and the design rationale). Validated end-to-end on the pilot book
**صحيح مسلم** (archive 12, bkid 1161 → edition 132) on 2026-08-21.

All commands are PowerShell, run from `AdvancedHadith\` unless noted.
`python` = the default interpreter (has psycopg, google-genai);
neural steps use `Arabic-lib\.venv-gpu\Scripts\python.exe`.

---

## 0. Prerequisites (once per machine)

| What | Where |
|---|---|
| Shamela CSV export | `E:\Al-Maktaba Al-Shamela 2017\CSV\<archive>\b<bkid>.csv` |
| Shamela index | `E:\Quran Computing Institute\Hadith.chat\- no duplicates فهرس الشاملة 3.xlsx` |
| Staging DB (created by step 2) | `Hadith.chat\Al-Shamela\alshamela.db` |
| Local Postgres URL | `AdvancedHadith\.env.local` → `LOCAL_PG_URL` (**must be saved UTF-8 *without* BOM** — a BOM makes older python-dotenv silently skip the first key and the backend dies with `fe_sendauth: no password supplied`; `backend/app/config.py` now reads `utf-8-sig` as a safety net) |
| Railway URL | never stored on disk; fetched per session, see step 10 |

Scripts that talk to Postgres resolve the URL as: `DATABASE_URL` env var →
`LOCAL_PG_URL` env var → `.env.local`. Exception: `etl\*.py` loaders use
`ETL_TARGET`/`DATABASE_PUBLIC_URL` for Railway (step 11). `build_shamela_toc.py`
requires `DATABASE_URL` to be set explicitly.

```powershell
# set DATABASE_URL for the session from .env.local (never echo its value)
$env:DATABASE_URL = (Get-Content .env.local |
    Where-Object { $_ -match '^LOCAL_PG_URL=' }).Substring(13)
```

---

## 1. Register the mapping

Add one line to `Hadith.chat\Al-Shamela\book_map.py` (the approval artifact —
only books listed here are ever staged):

```python
# aljam3_book_id: (archive, bkid, note)
2:  (12, 1161, "صحيح مسلم ت عبد الباقي"),
```

The (archive, bkid) pair comes from the approved table in
`ALSHAMELA_BOOK_SOURCES.md` Part B. For a book with **no aljam3 counterpart**
use a fresh id above the aljam3 range and note it; `load_shamela.py` will
create a new work instead of attaching to an existing one.

## 2. Stage the CSV into alshamela.db

```powershell
cd "e:\Quran Computing Institute\Hadith.chat"
python Al-Shamela\build_alshamela.py
```

Resumable: books already staged with the expected row count are skipped, so
running it after adding one mapping loads only that book. Expect a small
shortfall vs the index page count (rows without a numeric id are dropped —
Muslim: 8,903 of 8,941).

## 3. Verify identity against aljam3

```powershell
python Al-Shamela\evaluate_matches.py
```

Samples 20 aljam3 pages per mapped book and checks a mid-page fragment exists
verbatim (letters-only normalization) in the staged Shamela text.

**This check is informational, not a gate.** The Shamela and aljam3 copies of
a work are often *different prints* (publisher, تحقيق, page format, coverage —
e.g. سنن سعيد بن منصور scores 45% only because the approved Shamela edition
lacks the تفسير volumes aljam3 includes), so a sub-100% rate is expected and
acceptable. **The book mappings were manually verified as equivalent works by
the project owner (2026-08-21), and every approved book is processed without
requiring perfect page-level equivalence.** Use a low rate only as a prompt
to *explain* the difference (print variance vs a genuinely wrong bkid — a
wrong bkid shows near-0% plus a mismatched title/author in the index).
Batch reference: 46 of 48 books scored 85–100%; the two below that were
print-coverage differences, loaded as approved.

## 4. Load into local Postgres

```powershell
cd AdvancedHadith
$env:PYTHONIOENCODING = "utf-8"
python etl\load_shamela.py
```

Attaches a `source='shamela'`, `book_type='page-archive'` edition to the same
work as the aljam3 edition (via the book_map id), COPYs all pages as
`kind='page'` passages, converts the bare `\r` line separators to real `\n`
(same length — stored raw-text offsets stay valid), and keeps `hno`
(hadith number), `sora`, `aya` in passage meta. Resumable via the `etl_state`
ledger (step `shamela_book_<bkid>`).

Find the new edition id:

```powershell
python ops\_q.py "SELECT edition_id, work_id, passage_count FROM editions
                  WHERE source='shamela' AND source_book_id=1161"
```

(`ops\_q.py` is a tiny ad-hoc query runner; any psql works too.)

## 5. Build the book index (TOC)

```powershell
python ops\build_shamela_toc.py --edition 132        # add --rebuild to redo
```

Generates الفهرس from heading lines in the text (كتاب/باب/فصل grammar +
bracketed editor headings) and anchors every page to its innermost node
(`passages.toc_node_id`). Pilot: 1,395 nodes over 8,903 pages. The reader
side panel shows this tree with the root expanded; no per-book work needed.

## 6. Unitize + crosswalk + validate

```powershell
python ops\unitize_shamela.py --edition 132          # add --rebuild to redo
```

One command, three results (design: `ALSHAMELA_BOOK_SOURCES.md` §5A):

- **`shamela_units`** — hadith-level segmentation. Units start at number
  lines (`272 - (168) حدثنا…`, the two-number Muslim convention, or plain
  `123 - حدثنا…`) and at repeated-chain paren numbers (`(1098) وحدثناه…`,
  gated on proximity to the previous global number so footnote markers don't
  fire). `hadith_seq` = unique per-book 1..N; global id = `S<bkid>:<seq>`;
  `hadith_num` = printed (عبد الباقي) number.
- **`unit_map`** — crosswalk aljam3 unit → shamela unit by printed number +
  normalized-token overlap of the text after the number.
- **Validation report** (printed as JSON) — review before declaring the book
  done. Pilot reference numbers:

```json
{ "pages": 8903, "units": 8765, "distinct_nums": 3013,
  "hno_pages": 6977, "hno_agree": 6458, "sanad_end_filled": 0,
  "crosswalk": { "aljam3_units": 7626, "matched": 7592, "coverage": 0.9955,
                 "mean_conf": 0.7341, "high_conf": 7004, "high_share": 0.9226 } }
```

The crosswalk numbers are **advisory, not a gate** (same policy as step 3):
different prints legitimately produce partial coverage or lower confidence
(different numbering scheme, missing volumes, variant readings). Low numbers
mean "this book's crosswalk is thinner — rely on `hadith_seq`/text matching
rather than printed numbers for it", not "don't load it". All approved books
are processed regardless; the report is stored for the §8 retirement study,
which *does* require high coverage before an aljam3 book may be retired.

## 7. Neural structure annotation (GPU)

```powershell
$env:PYTHONPATH = "e:\Quran Computing Institute\Hadith.chat\AdvancedHadith\Arabic-lib"
$py = "Arabic-lib\.venv-gpu\Scripts\python.exe"
& $py -m arabiclib.neural.indexing annotate --edition 132   # sanad/matn spans
# batch form: --all-shamela (resumable per edition via etl_state)
```

Writes `passage_annotations` (layer `structure`) for matn highlighting.
One GPU job at a time — jobs contend badly. Then backfill the sanad/matn
boundary into the units:

```powershell
python ops\unitize_shamela.py --edition 132 --fill-sanad   # or omit --edition for all
```

## 8. Embeddings (semantic search)

```powershell
python ops\pilot_embed.py 132
```

Chunks all passages, embeds via Gemini into local Redis, then smoke-tests a
semantic + hybrid query against the edition. Pilot: 9,614 chunks, 0 errors,
~2 minutes. (On production, embeddings run against the production Redis from
Admin → Embeddings instead.)

## 9. Tashkeel — ALWAYS the closing step

Tashkeel generation runs **last**, after the book's pages, TOC, units, and
structure spans are in place, so the diacritized layer is computed over the
final text:

```powershell
& $py -m arabiclib.neural.tashkeel annotate --edition 132   # bare words only
# batch form: --all-shamela (resumable; skips already-annotated editions)
```

Writes `passage_annotations` layer `diacritized` (engine `neural-tashkeel`) —
diacritics are added **only to fully-bare words**; existing partial tashkeel
in the source text is never altered. A book is not "done" until the Tashkeel
toggle is verified on it:

```powershell
# API check: text_diac must be non-null once the edition is annotated
$p = (Invoke-RestMethod "http://localhost:8090/api/v1/editions/132/passages?seq=500")
[bool]$p[0].text_diac
```

Then in the reader (http://localhost:5173): open the book and flip the
**التشكيل** button both ways — ON shows the diacritized layer, OFF shows the
stripped view; matn highlighting must survive both states (the renderer maps
raw offsets through `stripTashkeel`/`mapRawOffset`, so no per-book work is
needed — this is a verification step, not a build step).

## 10. Local verification

```powershell
$w = Invoke-RestMethod "http://localhost:8090/api/v1/works/2"
$w.editions            # both sunna + shamela editions listed
(Invoke-RestMethod "http://localhost:8090/api/v1/editions/132/toc?depth=1").nodes.Count
Invoke-RestMethod "http://localhost:8090/api/v1/editions/132/passages?seq=500"
```

Reader smoke test at http://localhost:5173 : open the book, check TOC root
expanded, page renders with block formatting, Tashkeel toggle (step 9), matn
highlighting (after step 7), and the edition switcher.

---

## 11. Railway connection (per session)

The production Postgres URL is **never stored or printed**. Rebuild it into
the shell env from the linked service's variables (the `Postgres` service's
own `POSTGRES_PASSWORD` is the superuser, not the app role — use the app
service, role `ah`):

```powershell
$a = railway variables --json | ConvertFrom-Json          # linked app service
if ($a.DATABASE_URL -match '^postgres(?:ql)?://([^:]+):([^@]+)@') {
    $env:RAILWAY_PG_URL =
        "postgresql://$($Matches[1]):$($Matches[2])@acela.proxy.rlwy.net:15631/advancedhadith"
}
python ops\railway_pg_check.py                            # probe: version/size
```

## 12. Load + process on Railway

Same scripts, pointed at production. The unit tables are **rebuilt
deterministically on Railway, never copied by serial id** — passage ids can
differ between environments; (bkid, hadith_seq) and (source, source_book_id,
seq) are the stable keys.

```powershell
$env:DATABASE_URL        = $env:RAILWAY_PG_URL
$env:ETL_TARGET          = "railway"
$env:DATABASE_PUBLIC_URL = $env:RAILWAY_PG_URL
$env:PYTHONIOENCODING    = "utf-8"

python etl\load_shamela.py                     # only the new book (etl_state)
python ops\_q.py "SELECT edition_id FROM editions WHERE source='shamela' AND source_book_id=1161"
python ops\build_shamela_toc.py --edition <railway_id>
python ops\unitize_shamela.py --edition <railway_id>   # report must match local

Remove-Item Env:ETL_TARGET, Env:DATABASE_PUBLIC_URL
```

Push the locally computed neural annotations (structure + tashkeel) up —
mapped by natural key, immune to passage-id divergence:

```powershell
python ops\railway_push_annotations.py
Remove-Item Env:DATABASE_URL                   # ALWAYS restore when done
```

## 13. Production verification

```powershell
(Invoke-RestMethod "https://hadith-chat.up.railway.app/api/v1/works/2").editions
(Invoke-RestMethod "https://hadith-chat.up.railway.app/api/v1/editions/132/toc?depth=1").nodes.Count
```

Plus a reader spot check on https://hadith-chat.up.railway.app.

---

## Quick reference — one book end to end

| # | Step | Command | Target |
|---|---|---|---|
| 1 | Register mapping | edit `Al-Shamela\book_map.py` | — |
| 2 | Stage CSV | `python Al-Shamela\build_alshamela.py` | alshamela.db |
| 3 | Verify identity | `python Al-Shamela\evaluate_matches.py` | — |
| 4 | Load pages | `python etl\load_shamela.py` | local PG |
| 5 | Book index | `python ops\build_shamela_toc.py --edition N` | local PG |
| 6 | Unitize + crosswalk | `python ops\unitize_shamela.py --edition N` (advisory report) | local PG |
| 7 | Structure spans | `…neural.indexing annotate --edition N` then `unitize --fill-sanad` | local PG |
| 8 | Embeddings | `python ops\pilot_embed.py N` | local Redis |
| 9 | **Tashkeel (closing step)** | `…neural.tashkeel annotate --edition N` + toggle verification | local PG |
| 10 | Verify | API + reader smoke test (incl. التشكيل on/off) | local |
| 11 | Connect prod | `railway variables` → `RAILWAY_PG_URL` (env only) | — |
| 12 | Load + process prod | steps 4–6 with swapped env, then `railway_push_annotations.py` (after step 9) | Railway |
| 13 | Verify prod | API + reader spot check | Railway |

Identity/crosswalk numbers never block a book: the owner has manually
verified the approved mappings are equivalent works; print-level differences
(publisher, page format, coverage) are expected and recorded, not fixed.

Markdown-style page rendering requires **no per-book step** — the frontend
block renderer works off raw text offsets and picks up every shamela edition
automatically (aljam3 formatting untouched).

---

## Rāwī (narrator) ingestion — current behavior and the path to "yes"

**Today a Shamela book does *not* feed the ruwāh knowledge base.** Narrator
extraction (`ops/build_kg.py`) parses isnads only from aljam3 `kind='unit'`
passages; Shamela passages are `kind='page'` and are skipped. So importing a
Shamela book currently adds text, index, units, tashkeel, matn boundaries,
embeddings — but no new narrators or transmission edges.

This is deliberate for books that **have an aljam3 counterpart**: their
hadiths are the same hadiths already mined from aljam3, so re-extracting from
the Shamela copy would double every mention count and edge weight without
adding knowledge. The crosswalk (`unit_map`) is what ties the Shamela unit to
the already-extracted chains.

The pilot's unitization layer makes Shamela-side extraction possible when we
do want it — each unit has a start/end and a neural `sanad_end_off`, which is
exactly the input `parse_isnad` consumes. But **nothing enters the knowledge
base blindly**: the same hadith exists in multiple books and the same narrator
appears under many name forms, so every candidate must pass an explicit
redundancy gate first.

### Redundancy gate 1 — is this hadith actually new?

A Shamela unit is presumed to be a *duplicate* of known content until it
fails all of these checks, in order:

1. **Crosswalk by number** (`unit_map`) — matched units are the same hadith
   as their aljam3 twin; they must never be re-mined (that would double every
   mention count and edge weight while adding zero knowledge).
2. **Text overlap within the work** — for crosswalk gaps, retry matching by
   normalized-token containment against the same work's aljam3 units
   (numbering schemes drift between prints; the text usually still matches).
3. **Corpus-wide near-duplicate check** — a hadith absent from this work can
   still be a known hadith from another book (Muslim ⊂ Bukhari overlaps,
   musannaf works quote the six, etc.). Check the candidate matn against the
   global corpus by normalized-token containment and/or embedding similarity
   before treating it as new content; if it matches, record the relation
   (same-matn link) instead of creating an unrelated new entry.

Only units that clear all three are genuinely new hadith material — expected
mainly in Shamela-only books with no aljam3 twin.

### Redundancy gate 2 — is this narrator actually new?

1. **Exact alias resolution** — normalized mentions are matched to
   `narrator_aliases.alias_norm` first, so known narrators (≈36,973) resolve
   to their existing `narrator_id`. This is the same resolution
   `build_kg.py` uses; normalization already folds hamza/alif/ta-marbuta
   variants (ثقه = ثقة class of drift).
2. **Similarity clustering before creation** — an unresolved mention is
   checked against existing narrators by name-token similarity *and* isnad
   context (does it share teachers/students with an existing node?). A
   mention that transmits from the same shaykhs to the same students as an
   existing narrator is almost certainly the same person under another
   kunya/nasab — the three-عائشة duplication happened precisely because
   name-form variants were auto-inserted as separate nodes.
3. **Admin review, never auto-insert** — surviving candidates (seen ≥ 2
   times) are queued to the Admin console, where merge / create-with-alias /
   reject tools already exist and every action is audit-logged
   (`admin_audit`). A reviewed merge attaches the new mention as an alias of
   the existing narrator; only a reviewed create makes a new node. Rijal
   enrichment (generation, death year, grades) then attaches from the rijal
   books.

This extension is scoped in `ALSHAMELA_BOOK_SOURCES.md` §8 as part of the
aljam3-retirement feasibility: before any aljam3 book is retired, its
Shamela units must produce equivalent chains, validated through the
crosswalk. Not implemented yet — flag when needed.
