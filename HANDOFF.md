# Handoff: RegWatch (as of 2026-11-12, latest)

Paste this whole section to whoever picks the work up next. The older 11 Nov handoff is kept below for history; where they disagree, this one wins.

## Where things stand
Everything is on `main` (no other branches) and pushed. Plan of record: DECISIONS.md. Work is **paused**: the three Windows scheduled tasks on the collecting PC are disabled, not deleted.

| Step | State |
|---|---|
| Phase 0: bug fixes (security, data safety, migrations, frontend uses the real backend) | Done |
| Uploads: only admins upload to the shared library; any user can upload private circulars only they can see | Done |
| Phase 1: new-circular checker (date-filter POST, 15 s spacing, bot-check/empty page = FAILED_RETRY, rejected file = skipped) | Done, scheduler off by default (`SCHEDULER_ENABLED=false`) |
| Phase 2: archive versions (SHA-256, ETag, Last-Modified, weekly re-check, old version SUPERSEDED; English/Bangla kept as variants) | Done |
| Phase 3: page reading (PyMuPDF for English; Bangla, legacy-font and scanned pages queued as PENDING_VISION for Gemini 3.5 Flash-Lite with line boxes; Tesseract and Bijoy removed) | Done |
| Phase 4: quotes by sentence ID (`p3.s12`), code copies the exact text; Gemini responseSchema + backoff; OpenAI-compatible provider; no fake health result | Done |
| UI redesign (light default, dark toggle, Source Sans 3 + Noto Sans Bengali, framer-motion, tabbed admin) | Done |
| Quote highlight on the original page image (page image endpoint, word boxes for English, line boxes for Bangla) | Done; Bangla highlight covered by tests only |
| Pick the analysis model | Not started. The old test set on drive E: is lost; rebuild it first |
| Docs update, always-on server in Bangladesh | Not started |

Tests: `.venv\Scripts\python.exe -m pytest -q` from the repo root gives 213 pass, 6 fail, 1 error. All 7 are old known failures. One test rewrites a fixture PDF; run `git checkout -- backend/app/tests/fixtures` afterwards. Frontend: `npm run build` and `npm run lint` pass.
The click-by-click testing guide lives in the TickTick task "RegWatch + Tool".

## Paused jobs (Windows Task Scheduler on the collecting PC)
- `RegWatchDetectPoll`: the live new-circular detection test (`research/detect/detect_test.py poll`), every 10 min 10:00-18:00.
- `RegWatchDetectReconcile`: nightly full-list check at 17:50.
- `RegWatchArchiveDownload`: downloads the Bangla-only archive PDFs (`research/archive/fetch_archive.py download`) daily from 10:05.

Resume: `Enable-ScheduledTask -TaskName RegWatchDetectPoll` (same for the other two). The detection test's window was 12 Nov 12:00 to 19 Nov 18:00; pausing cuts it short, so either extend `TEST_END` in `detect_test.py` and the task end dates, or accept a shorter test.

## Results so far
- **Detection test (12 Nov only):** 25 polls, 9 ok and 16 timeouts; 3 new circulars caught, median 7 min and max 43 min after upload; nothing missed. The timeouts need a look: they may come from the archive download running in the same hours (both share one request lock) or from the site being slow. Run `python research/detect/detect_test.py summary` for the latest numbers, and record the verdict in research/06_VERDICT.md and DECISIONS.md.
- **Bangla archive:** 1,021 of 3,591 Bangla-only PDFs downloaded, 5 refused by the site ("Request Rejected", skipped). Files and state are in `research/archive/data/` (not in git; copy that folder by hand if the work moves to another PC).

## Decisions made on 12 Nov (not all in DECISIONS.md yet)
- No paid Gemini key. New circulars use the free API tier. The old Bangla archive is read by hand through 5 Gemini app subscriptions with the fixed prompt in `research/archive/READING_PROMPT.md`, then loaded with `python -m backend.scripts.import_manual_reading <folder> [--dry-run]` and spot-checked with `--sample 10`. The cost write-up is in `deliverables/` (not in git).
- No second-model check on page reading.
- Anything scheduled runs only 10:00-18:00 Bangladesh time; the PC is off otherwise.
- Analysis of private uploads: deferred. Today only admins can run analysis.

## Next steps, in order
1. Decide whether to resume the paused jobs (see above).
2. Rebuild the analysis test set (real circulars, answer key, locked dev/test split), then compare free models through the new provider config (`ANALYSIS_PROVIDER`, `ANALYSIS_MODEL`, `OPENAI_COMPAT_BASE_URL`) and pick one.
3. Optional: let one Gemini prompt carry several PDFs (`=== FILE <name> ===` markers) and teach the import script to split them, to cut the hand-reading from about 3,591 rounds to about 900.
4. Update docs (INGESTION, SECURITY, SYSTEM architecture) to match the code.
5. Move the backend and scheduler to an always-on machine in Bangladesh; overseas hosting hits the site's bot check.

## Known leftovers
- The admin "Trigger" button only runs the 7-day check; per-source polling frequency is ignored.
- The re-extract endpoint ignores `preferred_language`.
- Old Tesseract/Bijoy pages were re-queued as PENDING_VISION by the migration.
- A failed re-analysis keeps the earlier results; there is no "analysis failed" document status.
- `render.yaml` still uses the old names `AI_PROVIDER` / `GEMINI_MODEL` (still read, but should be renamed).
- Reject in the admin queue still uses the browser's prompt box.

## Rules
Plain, short explanations. Never mention AI tools in files, commits or docs. Commit as `hozaifa-rrh <hozaifahossain@rrh.com.bd>` with plain messages. Never call bb.org.bd faster than one request per 15 s. Never commit API keys or `research/*/data/`.

---
# Handoff: RegWatch architecture benchmark (as of 2026-11-11)

Read in this order: [DECISIONS.md](DECISIONS.md), then [research/06_VERDICT.md](research/06_VERDICT.md), then [research/05_TEST_PLAN.md](research/05_TEST_PLAN.md).
The user wants one tested verdict per app step, scored on a locked test split of real circulars. No caveats left for them to resolve.

## User rules that apply to this work
- Talk ELI5 and briefly. Lead with the verdict.
- **One subagent at a time.** The user's Pro limit was hit twice by parallel agents. On a Max account, still run one at a time unless the user says otherwise.
- Never mention AI, Claude or an agent in any file, commit or doc. Never commit `.claude/`, key files, or anything with "claude" in the name.
- Only research from 2026-11-10 onward counts. No legal or ethics lectures about downloading public circulars.
- Free models first. Paid models only if free falls short, and the user decides whether to pay.
- Never report a number measured on the data it was tuned on.

## Status
| Step | State |
|---|---|
| 1. Spotting new circulars | Decided (own script, date-filter POST, nightly full-list check). Live 5-working-day test runs until 18 Nov. |
| 2. Reading PDFs | **Decided on test split:** PyMuPDF for English; Gemini 3.5 Flash-Lite image reading for Bangla and scans; Flash as second reader. See 06_VERDICT.md. |
| 3. Analysis (metadata, obligations, applies-to, deadlines, relationships, summary) | **Not started.** The answer key isn't written yet. This is the main remaining work. |
| Storage, search/Q&A, alerts, front end | Not researched. |

## Where everything is: `E:\regwatch-research\` (outside git)
- **The sample:**
  - `pdfs\`: 139 PDFs from 130 random circulars (seed 20261110);
  - `pages.json`: per-page class;
  - `pages_png\`: 200 dpi renders.
- **Locked split (read-only; never edit):** `split_FROZEN.json` (dev 40, test 90 rows), `reading_subset_FROZEN.json` (80 pages), hashes in `FROZEN.sha256`.
- **Reading outputs:** `reading\<method>\<page_id>.txt`, plus the run log `reading\runs.jsonl`.
  Scripts: `part1_text.py`, `part_tess.py`, `part_api.py <method>`. `part_api.py` rotates over all Gemini keys and skips pages already done.
- **Reading answer key:** `gold\reading\<page_id>.txt` (all 80 done). Scorer: `score_reading.py dev|test`. Scores are in `reading_scores.json`.
- **Analysis answer key, not started:**
  - spec: `gold\GOLD_SPEC_ANALYSIS.md`;
  - checker: `gold\validate_gold.py <row>...` (exact-quote check for English, fuzzy for Bangla);
  - doc list: `gold\doc_index.json` (129 rows; long docs scored on pages 1-12 only);
  - work batches: `gold\batches.json` (dev_00..dev_04, then test_05..test_18; about 30 pages each);
  - outputs go to `gold\analysis\<row>.json`.
- **Detection test:**
  - folder: `detect\`;
  - results: run `venv\Scripts\python.exe detect\summary.py`;
  - scheduled tasks: `RegWatchDetectPoll` (every 10 min) and `RegWatchDetectReconcile` (02:00); both end 2026-11-18 06:00;
  - removal commands: `detect\REMOVE_TASKS.md`.
- **Python:** `E:\regwatch-research\venv` (PyMuPDF pinned <2, rapidfuzz, requests, google-genai).

## API keys (never commit or print them)
- **Gemini free keys, 4 of them, each in a different Google project:**
  - shell env GEMINI_API_KEY (account hozaifah626);
  - GOOGLE_API_KEY_FALLBACK in `F:\Projects\titan-title-review\.env`;
  - two in `E:\regwatch-research\gemini_keys.env` (accounts 20hozaifa02 and hozaifahossain@rrh.com.bd).
- **Free Gemini limits:**
  - 3.5 Flash: about 17 requests per key per day;
  - 3.5 Flash-Lite: much higher;
  - 3.8 Flash: returns 503 "high demand" almost always;
  - Pro models: no free quota.
- **Other free keys in the titan `.env`:** SambaNova (GLM-5.3, gpt-oss-120b, Llama 3.3 70B, MiniMax, gemma-4-31B) and OpenRouter (about $0.44 credit plus 1000 free-model requests a day).

## Next steps, in order
1. **Write the analysis answer key.**
   - **How:** one agent per batch from `gold\batches.json`, dev batches first. Each follows `GOLD_SPEC_ANALYSIS.md` and must run `validate_gold.py` until 0 errors.
   - **Model:** on Max, Opus is the better choice for this key. The Pro plan forced a switch to Sonnet.
   - **Cost to expect:** the 26-page Opus transcription job used about 40% of a Pro 5-hour window. The analysis key is about 366 pages.
2. **Audit 10% of the analysis key by hand** (about 13 rows) against the page images.
3. **Produce the reading-winner text for every analysis page.**
   - `pymupdf_raw` already covers English.
   - Gemini 3.5 Flash-Lite has only been run on the 80 benchmark pages. Run it on all non-English pages that are in the obligation window (`part_api.py` reads `subset_ids()`; extend it to the full page list).
4. **Build the analysis harness and scorer.**
   - Every candidate gets the same page texts.
   - Score by code: a predicted obligation matches a gold one when it's on the same page with at least 50% character overlap of quote. Also check that the quote is word for word in the input text, and compare type, deadline and subject.
   - Metadata and relationships are scored field by field. Summaries are scored by key facts covered, with two judges reported.
5. **Candidates (free):**
   - a rules-only baseline;
   - Gemini 3.5 Flash-Lite and 3.5 Flash;
   - Gemma 4 31B;
   - the SambaNova models;
   - OpenRouter free models;
   - local Ollama models (the user moved them to E:; find them and point OLLAMA_MODELS there).
   
   Ways of asking: whole document; span pointer (the model returns sentence IDs and code copies the text, which is required for quotes); hybrid.
6. **Tune with the autoresearch skill on dev only**, then run each finalist once on test. Fill in Step 3 of 06_VERDICT.md.
   If the best free model isn't good enough, say which paid model to test next and let the user decide.
7. **On or after 18 Nov:** run `detect\summary.py` and fill in Step 1 of 06_VERDICT.md.
8. **Update DECISIONS.md, 06_VERDICT.md and project memory.**

## Gotchas
- **bb.org.bd:** use User-Agent `RegWatchBot/0.1`, about 15 s between requests. A "Request Rejected" page for one URL means skip that file (2 sample files are like this). It isn't a block.
- **Windows Python:** always open files with `encoding="utf-8"`. Heredocs eat backslashes, so use forward slashes in paths inside Python.
- **Some pages are misclassified.** For example `1191_0_p10` is marked English but is Bangla. Route by font check, not by class label alone.
- **Free OpenRouter "reasoning" vision models** run out of output tokens on dense pages.
- **The old `docs/DECISION_LOG.md` has a pending local edit (not committed).** DECISIONS.md overrides it.
- **Nothing in `research/`, DECISIONS.md, HANDOFF.md or the CLAUDE.md edit is committed yet.**

