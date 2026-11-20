# Scorer for plan step 4: build spec

Written 2026-11-14. Purpose: one command that runs an analysis candidate on the 40 dev circulars, scores it against the
answer key, and prints one headline number, so the autoresearch loop can chase it overnight. The same tool later scores
the finalists once on the 90 test circulars, and prices and runs paid candidates once each in batch mode.

## 0. Ground rules
- Reuse the app's own code (`backend/app/modules/analysis/*`, `claims/*`, `relationships/linking.py`). Never re-implement
  the prompt, sentence IDs, claim building or code checks; the score must measure exactly what the app would show.
- Never write or edit answer keys. Keys live in `E:\regwatch-research\answer_key_kit\answers\<row>.json` (dev) and later
  `E:\regwatch-research\answer_key_test\answers\<row>.json` (test). Format: `E:\regwatch-research\answer_key_kit\PROMPT.md`.
  Page IDs `<file stem>_p<n>` (for example `2450_0_p1`) map to `E:\regwatch-research\pdfs\<file stem>.pdf` page n.
  Circular list and pages: `answer_key_kit\manifest.json` (dev); `E:\regwatch-research\gold\doc_index.json` (all 129 rows, `split` field).
- The test split is frozen: `split_FROZEN.json` + `FROZEN.sha256`. The scorer refuses `--split test` unless `--final` is
  given, and every `--final` run appends a line (date, candidate, score) to `research/scoring/TEST_RUNS.log`. Tuning
  never reads test keys.
- Free tiers only unless a run is explicitly marked paid (section 4). Never call bb.org.bd.
- No mention of AI, assistants or agents in code, comments or file names. Model names only in candidate config files.
- Code goes in `research/scoring/` (repo). Data, caches and outputs go in `E:\regwatch-research\scoring\`.
- Do not commit.

## 1. Fixed inputs (built once, then frozen)
`prepare_inputs.py`:
- For every page of every row (dev now; test later with `--split test --final`): English text-layer pages get text and
  word boxes exactly as the app's ingest does. Bangla, legacy-font and scanned pages are read once with the app's own page
  reader (`extraction/vision.py`, free keys, key rotation), giving text and line boxes exactly as the app stores them.
- Saved as `E:\regwatch-research\scoring\inputs\<page_id>.json` (text, boxes, method). Skip pages already saved. Never
  use the answer kit's or gold transcriptions as input (that would hide reading errors).
- Prints how many pages are ready and how many wait (free quota), and is safe to re-run.
- `--status` prints the counts.

## 2. Running a candidate
`run_candidate.py --candidate <config.json> --split dev [--rows 2450,1426] [--force]`
- Candidate config (`research/scoring/candidates/*.json`): `name`, `provider` (gemini / openai_compat / mock), `model`,
  `prompt` (the app's current prompt, or a path to a prompt variant file), `method` (whole document, the app's default),
  any provider settings, `paid: true|false`.
- For each row: load the fixed inputs into a throwaway SQLite database through the app's own models (one document, one
  version, its pages), call `AnalysisService.analyze_document_version` (or the pieces it calls) with the candidate's
  provider and prompt, so claims are built and code-checked exactly as in the app. Reading checks (chunk 4) are not run
  here; treat `QUOTE_READING` as not run so it never blocks (step 4 scores analysis, not reading).
- Cache the raw model answer per (row, candidate name, model, prompt hash, input hash) in
  `E:\regwatch-research\scoring\cache\`. A re-run with an unchanged model, prompt and inputs makes **no model call**.
  `--rescore-only` re-builds claims and re-runs code checks from the cached answers (so tuning `claims/wording.py` or
  `claims/checks.py` costs nothing and takes seconds).
- Output per row: `E:\regwatch-research\scoring\runs\<candidate>\<row>.json` with every claim: kind, fields, quote text,
  page_id of each evidence sentence, each check's result, and whether it would be shown (PASSED) or hidden.
- Free-tier busy or quota replies: wait and retry with the app's existing backoff; never record them as an empty answer.
  An answer that is empty or says there was no content is recorded as `EMPTY_ANSWER` and counted in the score (section 3.6).

## 3. Scoring
`score.py --candidate <name> --split dev [--rows ...] [--json out.json]`. Normalise text with `claims/wording.py::norm`.

### 3.1 Matching obligations
- A predicted OBLIGATION matches a key obligation when they share a page and their quotes overlap by at least 50% of the
  shorter quote's characters (after `norm`). Match one-to-one, best overlap first (greedy is fine). A key item that lists
  two duties with the same quote can match two predictions.
- Per matched pair, fields:
  - `type` (map app types to key types: MANDATORY→must, PROHIBITION→must_not, PERMISSION→may, REPORTING→report,
    RECORD_RETENTION→keep_records, APPROVAL→get_approval, DISCLOSURE→disclose; CONDITIONAL and RECOMMENDATION count as must);
  - `subject` (map app entities to key entities; `other:` values match when the key is `other:` too);
  - `deadline` (both null; or the same date; or relative wording with `difflib` ratio ≥ 0.8; or the same frequency word).
- A pair is **fully right** when all three fields are right.

### 3.2 Other fields
- **Effective date:** the predicted DATE claim of kind EFFECTIVE (or the obligations' effective date when every obligation
  agrees) against `effective`: right when basis and date match (`immediate` is right when the prediction equals the issue
  date and its quote has an immediate-effect phrase; `not_stated` is right when nothing is predicted). Count the
  "issue date given as effective date when the key says not_stated" mistake separately.
- **Applies to:** set precision and recall over entities (`all_scheduled_banks` in the key also accepts any scheduled-bank subtype).
- **Exemptions:** recall and precision by quote overlap (as 3.1).
- **Links:** match by `relationships/linking.py::reference_keys` of the target. Report recall, precision and type
  accuracy, and count **false change claims**: a predicted amends/repeals/replaces/supersedes where the key says
  `references` or has no such link. Predicted links whose quote is on an enclosure page count as wrong.
- **Summary points and key changes:** evidence-overlap recall (a key point is covered when some predicted point's quote
  overlaps its quote by ≥ 50%) and precision (a predicted point is supported when its quote overlaps some key point's or
  key obligation's quote). Wording is not judged here (plan step 6).
- **Enclosures:** predicted obligations whose quote is on a key enclosure page count as wrong (precision).

### 3.3 Shown vs hidden: the code checks
Every predicted claim is labelled **right** (matches a key item with all fields right) or **wrong** (no match, or a field wrong).
Cross with shown/hidden:
- **leak rate** = wrong and shown / all shown. This is the golden-rule number; it must stay as low as possible.
- **false-alarm rate** = right and hidden / all right.
- Per check (`DUTY_WORDING`, `WHO`, `DATES`, `NUMBERS`, `EXEMPT_WORDS`, `OVERCLAIM`, `TARGET_NAMED`, `CHANGE_WORDS`, ...):
  how often it failed a right claim (false alarm) and how often it caught a wrong claim. This drives check tuning.

### 3.4 Headline score (one number, higher is better, 0-100)
```
score = 100 * ( 0.35 * obligation_F1_fully_right_shown
              + 0.15 * links_score            # (link recall * type accuracy) minus 0.5 per false change claim per row, floored at 0
              + 0.10 * effective_accuracy
              + 0.10 * applies_to_F1
              + 0.15 * summary_and_changes_F1 # evidence-overlap
              + 0.15 * (1 - false_alarm_rate) )
        - 200 * leak_rate
```
"Shown" means only claims that pass the code checks count as predictions. The large leak penalty means a change that
shows more by letting wrong points through loses. The last line of `score.py` output is `SCORE <number>` and nothing
else, so the loop can read it. Weights live in one dict at the top of `score.py`.

### 3.5 Reports
- Plain table per row and in total: every metric above, the number of claims shown and hidden, calls made, time and
  tokens per row.
- `--diff <other candidate>`: rows where the two differ most, to guide the next change.
- Write `E:\regwatch-research\scoring\reports\<candidate>_<split>_<date>.md`.

### 3.6 Failures count
A row with `EMPTY_ANSWER`, an error, or zero claims scores zero on every field for that row (no silent skips).

## 4. Paid candidates: price first, then batch, once
- `price.py --candidate <config>` estimates the cost of one run over the split: input and output tokens per row from
  the cached free runs (or a tokenizer estimate), times the candidate's prices written in its config with the page and
  date they were checked (`price_source`, `price_checked`). It prints the total. Prices come from each vendor's own price page.
- `run_candidate.py --batch` writes the vendor's batch request file (OpenAI Batch API JSONL; Gemini batch mode), and
  `--collect` reads the results into the cache. Submitting a batch needs `--yes-spend` and prints the estimate first.
  Nothing paid runs without that flag. Each paid candidate runs once on dev and, if a finalist, once on test.

## 5. Tests (`research/scoring/tests/`, pytest, no network)
- Matching and every metric on two small hand-made keys and predictions (made up for the test, not real answer keys),
  including: a two-duty sentence; an enclosure page; a false change claim; immediate effect; issue date wrongly given
  as effective; a hidden right claim (false alarm); a shown wrong claim (leak); an empty answer row.
- The cache: a second run makes no provider call (count calls on a mock provider).
- `--split test` without `--final` exits with a plain error.
- A run with the app's mock provider end to end on 2 dev rows (inputs from a fake reading) gives a score.

## 6. Done when
- Tests pass. The app's own pytest suite has no new failures (`git checkout -- backend/app/tests/fixtures` after it).
- `prepare_inputs.py --split dev` has saved every English dev page; the Bangla and scanned pages are read or waiting on
  the free quota (say how many and when the quota resets).
- A free baseline candidate (`candidates/gemini_flash_v3.json`: the app's current settings and prompt) has run on the dev
  rows whose inputs are ready, and `score.py` prints a table and `SCORE` once the answer keys are in place.
  Until the keys exist, show the score on the test fixtures only.
- `research/scoring/README.md`: plain commands for prepare, run, rescore, score, price, batch.
