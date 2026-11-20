# Scorer for the analysis (plan step 4)

One command runs an analysis candidate on the dev circulars, scores it against the answer key and prints one number.
The spec is `research/09_SCORER_SPEC.md`. This file only says how to use the tool.

Run every command from the repo root. `py` below means `.venv\Scripts\python.exe`.
Data, caches and outputs live in `E:\regwatch-research\scoring\`. Code and candidate configs live here.

## The short version

```
py research\scoring\prepare_inputs.py --split dev                                  # 1. save the pages (once)
py research\scoring\run_candidate.py --candidate gemini_flash_v3 --split dev       # 2. run a candidate
py research\scoring\run_candidate.py --candidate gemini_flash_v3 --split dev --rescore-only   # 3. rebuild claims after a checks change
py research\scoring\score.py --candidate gemini_flash_v3 --split dev               # 4. score it
py research\scoring\price.py --candidate my_paid_one --split dev                   # 5. price a paid candidate
```

The last line of `score.py` is `SCORE 63.21` and nothing else, so a loop can read it.

## 1. Prepare the inputs

`prepare_inputs.py --split dev` saves every page as `inputs\<page_id>.json`.

- English pages: text and word boxes exactly as the app's ingest makes them.
- Bangla, old-font and scanned pages: read once from the page image with the app's own page reader (free Gemini keys, rotating).
- It never uses the answer kit's or the gold transcriptions.
- A page is saved only when its reading worked. If the free quota stops the reading, the page stays unsaved and counts as waiting.
- It is safe to run again. Saved pages are skipped.

Useful flags:

- `--status` prints the counts and stops.
- `--wait` sleeps until the free quota is back (about 14:05 Bangladesh time) and carries on. It shares the page reader's free Flash-Lite quota, so only use it when the archive reading can spare it.
- `--rows 2450,1426` limits it to some circulars.

A circular with a Bangla twin file (an `_1` file) has both files saved. The app only analyses the first (English) file, so the scorer does the same.

## 2. Run a candidate

A candidate is a small JSON file in `research\scoring\candidates\`:

| field | meaning |
|---|---|
| `name` | used in file names and reports |
| `provider` | `gemini`, `openai_compat` or `mock` |
| `model` | the model id (model names go only in these files) |
| `prompt` | `app` for the app's current prompt, or the path of a prompt variant file |
| `method` | `whole_document` (the only one built) |
| `paid` | `true` or `false` |
| `settings` | `base_url`, `api_key_env`, `response_format` for `openai_compat`; `api_key_env` for a single Gemini key |

Free Gemini candidates rotate over `GEMINI_API_KEY` and `GEMINI_EXTRA_API_KEYS` in `.env`.

`run_candidate.py --candidate NAME --split dev` does, for each circular whose pages are all saved:

1. loads the pages into a throwaway database through the app's own models;
2. calls the app's own `AnalysisService.analyze_document_version`, so claims are built, code-checked and routed exactly as in the app;
3. writes `runs\<candidate>\<row>.json` with every claim: kind, fields, quote text, page ids, every check result, shown or hidden.

Things to know:

- **The model's raw answer is cached** in `cache\`, keyed by circular, candidate, model, prompt and inputs. Same model, prompt and inputs means no model call.
- `--force` asks the model again. `--rows` runs only some circulars.
- `--rescore-only` never calls a model. It rebuilds claims and checks from the cached answers. Use it after changing `claims\wording.py` or `claims\checks.py`. It takes seconds.
- Busy, rate-limit and daily-quota replies are never saved as answers. The run waits, tries the next key, and stops (without recording the row) when every key is used up for today. It prints when the quota comes back.
- An empty answer is recorded as `EMPTY_ANSWER` and scores zero for that circular. So does an error or a run with no claims.
- The second reading of quoted Bangla sentences (chunk 4) is **not run** here. Those checks never block a claim.
- The throwaway database is deleted after each circular. `data\regwatch.db` is never opened.

### Prompt variants

A variant file has two parts:

```
=== SYSTEM ===
...the system prompt... ({entity_names} is filled in)
=== USER ===
...the user prompt... must contain {document_pages_text}; write a literal brace as {{ or }}
```

Copy the app's prompt from `backend\app\modules\analysis\prompts.py` and change it. The scorer swaps it in while a circular runs and puts the app's prompt back afterwards. No app code is changed.

## 3. Rescore after a checks change

```
py research\scoring\run_candidate.py --candidate gemini_flash_v3 --split dev --rescore-only
py research\scoring\score.py --candidate gemini_flash_v3 --split dev
```

## 4. Score

`score.py --candidate NAME --split dev` reads the runs and the answer keys in `E:\regwatch-research\answer_key_kit\answers\`.
It scores the circulars that have both a run and a key, and lists the others. It never writes a key.

It prints a table per circular and in total, the leak rate, the false-alarm rate, and how each code check did on right and wrong claims.
It also writes `reports\<candidate>_<split>_<date>.md`.

- `--diff OTHER` shows the circulars where two candidates differ most.
- `--json out.json` writes every number to a file.
- `--keys-dir DIR` reads keys from another folder (the tests use made-up keys this way).

How the headline number is made, in one line:
`100 * (0.35 obligation F1 + 0.15 links + 0.10 effective date + 0.10 applies-to + 0.15 summary and changes + 0.15 * (1 - false alarms)) - 200 * leak rate`.
The weights are in one dict at the top of `score.py`.

Choices the spec left open (change them in `score.py` if you disagree):

- Obligations the model puts on pages outside the key's page window are not scored (the key has no answer there). The count is printed.
- When a circular has two files, only the first is analysed, as in the app.
- The links score pools all circulars: link recall times type accuracy, minus 0.5 for each false change claim divided by the number of circulars, floored at zero.
- A link's type is the type the model claimed (not the weaker "Mentions" the app shows before review). That is what "false change claim" measures.
- Clause-tree claims (PROVISION) are not scored: the circular page does not show them.
- A date claim (not an effective date) is right when it equals a deadline in the key.
- The throwaway database holds only the one circular. So the "other circular is in the library and older" checks can fail. They only decide a link's wording, never whether it is shown, so the score is not affected.

## 5. Price and batch (paid candidates)

Nothing paid runs by itself.

- `price.py --candidate NAME --split dev` prints the estimated cost. It uses real token counts from saved runs of the same circulars, or a length estimate. The prices come from the candidate's config: `price_input_per_mtok`, `price_output_per_mtok`, `batch_discount`, `price_source` (the vendor's price page) and `price_checked` (date). Fill them in from the vendor's own page.
- `run_candidate.py --candidate NAME --split dev --batch` writes the vendor's batch request file to `batches\` and prints the estimate. It sends nothing.
- `... --batch --submit --yes-spend` sends an OpenAI-style batch. This part has not been tried against a live service. For a Gemini batch, upload the file in the vendor's console yourself.
- `... --collect [results.jsonl]` reads finished results into the cache. With no file it fetches them for an OpenAI-style batch. Then run `--rescore-only` and `score.py`.
- A paid candidate refuses a direct run unless `--yes-spend` is given.

Each paid candidate runs once on dev and, if it is a finalist, once on test.

## The frozen test split

`--split test` is refused unless `--final` is given. Every `--final` run (prepare, run, score) adds a line to `research\scoring\TEST_RUNS.log`.
The scorer also checks that `split_FROZEN.json` still matches `FROZEN.sha256`. Tuning never reads test keys.

## Tests

```
py -m pytest research\scoring\tests -q
```

No network. They use made-up circulars (rows 9001, 9002, 9101) and made-up keys. The app's own suite is separate: `py -m pytest -q`, then `git checkout -- backend\app\tests\fixtures`.

## Files

| file | job |
|---|---|
| `common.py` | paths, the circular list, the test-split guard |
| `prepare_inputs.py` | step 1 |
| `run_candidate.py` | step 2, batch files |
| `provider_cache.py` | the cache and the wait-and-rotate logic around the model |
| `quota.py` | notes on which free keys are used up |
| `score.py` | step 3 |
| `price.py` | cost estimate |
| `candidates\` | candidate configs |
