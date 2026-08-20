# Neural Models Performance Report (§12.9)

**Date:** 2026-08-20 · **Hardware:** NVIDIA GeForce RTX 3080 (12 GB), CUDA 12.4,
PyTorch 2.6.0+cu124 · **Venv:** `Arabic-lib\.venv-gpu`

Three trainable models per the plan (§12.9), operated **only via local CLI** —
text in, processed text out. The deployed application never invokes them; only
their precomputed outputs would be pushed to Postgres. All datasets were
generated from our own corpus (659k passages, 33 matn books) — "the corpus is
the labeler": no manual annotation was used.

| Model | Task | Architecture | Params | Test metric |
|---|---|---|---|---|
| A. Page indexing | word labeling: HNUM / ISNAD / MATN / HEADING | char-BiLSTM word encoder → 2-layer word BiLSTM | 2.84 M | **99.91 %** word accuracy; **99.79 %** matn boundary ±2 words (median error 0) |
| B. Tashkeel | per-letter diacritic class (16 classes) | char embedding → 2-layer BiLSTM (768 hid) | 5.15 M | **4.17 % DER** (all letters), **4.02 % DER** (marked letters) |
| C. POS | word tagging, 24 tags distilled from CAMeL | same word-tagger architecture as A | 2.85 M | **95.87 %** token accuracy vs silver |

---

## Datasets (auto-generated, `Arabic-lib/training/build_datasets.py`)

| Dataset | Source | Samples (train/dev/test) | Ground truth |
|---|---|---|---|
| `tashkeel.jsonl` | Shamela editions with vocalization density ≥ 0.6 (e.g. مجمع الزوائد 0.86, فتح الباري 0.80), windows ≤ 380 chars | 54,009 / 2,987 / 3,004 (514k test chars) | the vocalized text itself — stripping diacritics yields perfect parallel pairs |
| `pos.jsonl` | 4,000 random hadith units | 3,637 / 182 / 181 (19k test tokens) | CAMeL morphology engine (ensemble member, §12.8) silver tags |
| `indexing.jsonl` | 40,000 units with the rule-extractor's raw sanad/matn boundary (`isnad_chains.sanad_end_raw`) + 8,000 TOC headings | 43,275 / 2,383 / 2,342 (181k test tokens, 1,903 boundaries) | rule pipeline §12.7 output over the 33-book extraction |

Split is a deterministic 90/5/5 content hash; test was never seen in training.

## A. Neural page indexing

- **Formulation** (per plan): token-level labeling, not generation — deterministic
  and auditable. Classes: `HNUM` (hadith number), `ISNAD`, `MATN`, `HEADING`.
- **Training:** 3 epochs, ~5.5 min/epoch, batch 32, AdamW 1e-3.
  Dev accuracy 97.97 % → 99.56 % → 99.95 %.
- **Test:** word accuracy **0.9991**, matn boundary within ±2 words **0.9979**,
  median boundary error **0 words** (1,903 test boundaries).

```text
> python -m arabiclib.neural.indexing infer --text "1248 - حدثنا محمد بن بشار قال حدثنا يحيى عن عبيد الله قال حدثني نافع عن ابن عمر ان رسول الله صلى الله عليه وسلم قال من اقتنى كلبا الا كلب ماشية او ضاري نقص من عمله كل يوم قيراطان"
[HNUM] 1248
[ISNAD] - حدثنا محمد بن بشار قال حدثنا يحيى عن عبيد الله قال حدثني نافع عن ابن عمر ان
[MATN] رسول الله صلى الله عليه وسلم قال من اقتنى كلبا الا كلب ماشية او ضاري نقص من عمله كل يوم قيراطان
```

The model reproduces the extractor's boundary convention exactly (the
introducing «أنّ» stays in the sanad).

## B. Neural tashkeel

- **Formulation** (per plan): character-level classification — for every Arabic
  letter, one of 16 classes (fatḥa/ḍamma/kasra/sukūn + 3 tanwīn forms + none,
  each ± shadda). Base letters are never altered.
- **Training:** 3 epochs, ~2 min/epoch, batch 64, AdamW 2e-3.
  Dev DER(all) 5.50 % → 4.36 %.
- **Test:** DER **4.17 %** over all letters, **4.02 %** on letters that carry a
  mark in the reference (514,153 test characters).

```text
> python -m arabiclib.neural.tashkeel infer --text "قال رسول الله صلى الله عليه وسلم انما الاعمال بالنيات وانما لكل امرئ ما نوى"
قَالَ رَسُولُ اللَّهِ صَلَّى اللَّه عَلَيْهِ وَسلم انما الاعمال بالنيات وانما لكل امرئ مَا نوى
```

Note the model reflects its training distribution: classical texts vocalize
selectively, so the model is conservative on words the sources typically leave
bare. Training on a fully-vocalized subset (density ≥ 0.9) sharpens coverage at
the cost of corpus size.

## C. Neural POS (distilled from the Arabic-lib engine ensemble)

- **Formulation** (per plan §12.9-C): distill the CAMeL morphology engine (the
  available ensemble member; Farasa/AlKhalil join the consensus when their
  ports land) into a compact tagger that needs no morphology database at
  inference.
- **Training:** 4 epochs, ~15 s/epoch, batch 32, AdamW 1e-3.
  Dev accuracy 84.59 % → 95.75 %.
- **Test:** **95.87 %** agreement with the silver teacher on 19,025 tokens.
  Top confusions are the classic Arabic ambiguities (noun ↔ verb 293 cases,
  noun_prop ↔ noun 171, adj → noun 117) — largely unvocalized homographs.

```text
> python -m arabiclib.neural.pos infer --text "حدثنا قتيبة بن سعيد قال حدثنا سفيان عن الزهري"
حدثنا/verb قتيبة/noun_prop بن/noun سعيد/noun_prop قال/verb حدثنا/verb سفيان/noun_prop عن/prep الزهري/adj
```

## CLI reference (run from `AdvancedHadith\`, GPU venv)

```powershell
$env:PYTHONPATH = "<repo>\AdvancedHadith\Arabic-lib"

# datasets (backend venv — needs Postgres + camel-tools)
.venv\Scripts\python Arabic-lib\training\build_datasets.py --task all

# train / evaluate / run (GPU venv)
Arabic-lib\.venv-gpu\Scripts\python -m arabiclib.neural.tashkeel train --epochs 3
Arabic-lib\.venv-gpu\Scripts\python -m arabiclib.neural.tashkeel eval
Arabic-lib\.venv-gpu\Scripts\python -m arabiclib.neural.tashkeel infer --text "..."   # or --file in.txt

Arabic-lib\.venv-gpu\Scripts\python -m arabiclib.neural.pos      train --epochs 4
Arabic-lib\.venv-gpu\Scripts\python -m arabiclib.neural.pos      infer --text "..."

Arabic-lib\.venv-gpu\Scripts\python -m arabiclib.neural.indexing train --epochs 3
Arabic-lib\.venv-gpu\Scripts\python -m arabiclib.neural.indexing infer --text "..."
```

Checkpoints: `Arabic-lib/models/*.pt` (gitignored; each stores its vocab,
config, dev metrics, and version). Data: `Arabic-lib/training/data/*.jsonl`
(gitignored).

## Limitations & upgrade path

- These are the from-scratch **v0.1 baselines** of the §12.9 program, chosen to
  train in minutes on the RTX 3080 with zero external downloads. The plan's
  next steps remain: CAMeLBERT-CA token-classification head for indexing (+
  LoRA incremental fine-tuning from `training_examples` deltas), ByT5-small
  benchmark for tashkeel, and Farasa/AlKhalil joining the POS consensus.
- POS accuracy is measured **against the silver teacher**, i.e. it bounds
  agreement with CAMeL, not absolute linguistic truth.
- The indexing model learns the rule extractor's boundary convention; its value
  is generalizing that convention to books/pages the rules parse poorly, and
  its per-token confidence can queue low-confidence pages for review (active
  learning), per the plan.
- Tashkeel DER is measured on selectively-vocalized classical text; a
  fully-vocalized training subset is the lever for a stricter model.
