# Arabic-lib (`arabiclib`)

Unified Arabic linguistic annotation for AdvancedHadith (architecture §12).
One call evaluates all requested layers simultaneously against a single master
token sequence:

```python
from arabiclib import annotate
ann = annotate("حدثنا عبد الله بن يوسف قال أخبرنا مالك عن نافع",
               layers=["segments", "pos", "ner", "roots"])
ann.meta["engines"]         # which engine produced each layer
ann.meta["missing_layers"]  # layers with no available engine on this machine
```

## Engines and roles (registry)

| Layer | Primary | Fallback | Notes |
|---|---|---|---|
| segments | Farasa JAR | CAMeL | Farasa quality is the benchmark (D7/D9) |
| pos | Farasa JAR | CAMeL | |
| ner | Farasa JAR | CAMeL (CAMeLBERT) | |
| roots | **AlKhalil2** | CAMeL | AlKhalil excels at تجذير (§12.6) |
| diacritized | Farasa JAR | — | |
| morphology | CAMeL | — | lemma/root/pattern/features |

Every engine self-reports availability. Diagnostics:

```
.venv\Scripts\python -m arabiclib.pipeline --engines
```

### Enabling engines

- **CAMeL Tools**: `pip install camel-tools` then
  `camel_data -i morphology-db-msa-r13` (morphology) and
  `camel_data -i ner-arabert` (NER).
- **Farasa JARs**: the `Grammar/` folder ships Ant sources without dists.
  Build each with `cd Grammar/<project> && ant jar`; engines find
  `<project>/dist/*.jar` automatically. JARs run as ONE persistent JVM
  process each (never per-call). They remain the permanent validation
  oracles for the staged Python ports (§12.8).
- **AlKhalil2**: pure Python in `Grammar/alkhalil_nlp`, but its lexicon
  (`resources/Data.root` and companions) is not in the repo — obtain the
  AlKhalil Morpho Sys 2 resources and place them under
  `Grammar/alkhalil_nlp/resources/`.

## Batch corpus annotation

```
.venv\Scripts\python -m arabiclib.pipeline --edition 18 --layers roots,pos,ner
```

Writes `passage_annotations (passage_id, layer, engine, version, payload)` —
resumable (existing rows skipped; `--overwrite` to redo).

## Automated book indexing (§12.7)

`arabiclib.indexing` converts flat Shamela page dumps into hadith-unit indexed
content: `headings.py` (كتاب/باب/فصل detection), `numbering.py` (hadith-number
extraction + monotonic reconciliation), `units.py` (unit segmentation via
number heads / headings / isnad openers), `tocbuild.py` (synthetic TOC tree).
Validation harness: `ops/index_validate.py` measures boundary F1 of the rule
pipeline on Bukhari flat pages (shamela) against the native sunna index.

## Isnad heuristics

`arabiclib.isnad.parse_isnad(text)` locates the sanad/matn boundary and parses
transmission hops (verb + name mention) — the input to the Phase 6 KG builder.


## TASHKEEL NOTES:
# tashkeel done and pushed to production (230,689 annotation rows) for alshamela books


## NOTES:
Indexing model v0.2 training completed successfully — and dramatically faster with the GPU to itself (~18 minutes for all 3 epochs, versus the 13+ hours it was projecting while sharing the GPU with the tashkeel job).

Final evaluation on the held-out test set (174,404 tokens, 2,033 boundaries):

Word accuracy: 99.96%
Matn boundary within ±2 words: 99.75%
Boundary median error: 0 words
The model is saved to Arabic-lib\models\indexing_wordtagger.pt and is ready to serve sanad/matn boundary detection. All background GPU work is now finished — nothing left running.
