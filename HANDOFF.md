# Handoff: RegWatch (as of 2026-11-13 late night, latest)

## Archive download (13 Nov, always-on PC; nothing committed)
- Full archive: 5,191 PDFs (1,226 English, 3,965 Bangla) in about 4,800 circulars, downloading into `research/archive/data/pdfs/` (git-ignored).
- Rate: one request every 3 s, 24/7 (speed test clean down to 2 s; see `research/archive/SPEED_TEST.md`, DECISIONS.md 11). Scheduled task `RegWatchArchiveDownload`; it restarts itself and backs off on a challenge page.
- Status any time: `E:\regwatch-research\venv\Scripts\python.exe research\archive\fetch_all.py status`. Full report: `research/archive/ARCHIVE_REPORT.md`.
- Load into the app when the download is done: `.venv\Scripts\python.exe backend\scripts\import_archive.py --app-db` (default without the flag is a throw-away test database). No analysis is run.

## START HERE: next session (written 13 Nov late night; nothing committed)

**Paste this to start the next session:**

> Read the project notes, DECISIONS.md (decisions 11-12 are new), research/07_REDUCE_HUMAN_REVIEW.md, then this section. The user approved building the 07 plan. Usage is tight: do the design and judgement work yourself (no Opus subagents); use only Sonnet subagents for building, one at a time, never in parallel, each with a self-contained brief. Step 1 is done. Next: write docs/specs/CLAIM_CHECKS_SPEC.md yourself (plan steps 2, 3 and 5: claim-level checks, per-claim status with hiding, a small one-claim-at-a-time reviewer screen, and checking only the quoted Bangla sentences instead of decision 10's page-level 2% rule), ordered into 2-4 build chunks with "done when" checks. Then hand each chunk to one Sonnet subagent in turn. Then plan step 4: the answer key for the 40 tuning + 90 test circulars and a scoring harness (the same test also picks the analysis model; include the main paid models as candidates as the user decided (price the test first); the app itself stays on free tiers during the build). Keep archive analysis on hold until the claim checks exist. Every screen must say what it waits for and how long, update by itself, and show no technical codes.

**Running on this PC right now (started in a session, so they stop if the PC restarts):**
- Archive download: scheduled task `RegWatchArchiveDownload`, 2 s gap. Progress: `E:/regwatch-research/venv/Scripts/python.exe research/archive/fetch_all.py status`.
- Archive import loop: adds new downloads to the library every 10 min (`backend/scripts/import_archive.py --app-db`); last run imported 659 files, 0 failed.
- Page reader: `backend/scripts/read_pages.py` with 8 free keys, about 6 pages a minute, newest circulars first. Log `data/page_reader.log`; `--status` for counts.
- To make the reader and import survive a restart, the user runs once: `powershell -ExecutionPolicy Bypass -File backend/scripts/register_reader_tasks.ps1` (registering was blocked for me).

**Done in this session (all tested; full suite earlier 368 pass with the 5 old failures; `test_speed_fixes.py` now 16 pass):**
- Step 1 of the 07 plan: analysis refuses to run while any page waits to be read (`analysis/auto.py`; the button answers "N pages are still being read"). New circulars from the live checker (status PUBLISHED_MACHINE_PROCESSED) are analysed by themselves once all pages are read (hooked into the page reader and the web job). Archive circulars (status EXTRACTED) are never analysed automatically.
- New GET `/documents/{id}/reading-status` and a plain line on the circular page: "Reading the page images: x of y pages ready, about N minutes left", or "Waiting in line: N pages from newer circulars are read first", or "paused: today's free reading limit is used up; starts again at about HH:MM", plus what happens next (analysed by itself / added later for older circulars / an admin can run it). Archive circulars with no analysis say the summary comes later. Checked by API on a real archive circular; the browser check at 375 px is still to do.
- SQLite now waits up to 60 s for another process's write (WAL when possible), so the reader, import and app share the file safely.
- The Opus design subagent was stopped before writing anything (usage). `research/07_scratch/` holds the 07 research scripts.

**Notion:** item 6 updated 13 Nov through Composio (the Notion connector was failing; use Composio for Notion).

**Background jobs now:** all three run as Windows tasks (the user registered them 13 Nov): `RegWatchArchiveDownload`, `RegWatchArchiveImport`, `RegWatchPageReader`. They do not depend on an open session.

**Decided by the user (Notion item 2, 13 Nov):** the analysis-model test scores free AND paid models (the main paid models, including paid Gemini). Price the paid test runs before running them.

## Archive pages read by the API, not by hand (13 Nov late night)
- Decided by the user 13 Nov: the old Bangla archive pages are read by the app itself with all free Gemini keys, instead of hand-copying through the Gemini app (the 12 Nov plan). Hand reading (`READING_PROMPT.md`, `import_manual_reading`) stays as the fallback for pages that fail. The paid tier is bought only at the very end; the build runs on free tiers.
- Free limits seen in AI Studio for `gemini-3.5-flash-lite`: 15 a minute and 500 a day per project; no weekly or monthly cap; daily reset at midnight Pacific (about 14:00 Bangladesh time). Free-tier input may be used by Google and seen by reviewers: fine for public circulars, but private bank uploads must move to the paid tier before launch.
- Code: a daily-quota reply rests that key until the reset; busy, rate-limit or quota replies never count as a failed try on the page (so no good page is sent to a person for that). Newest circulars are read first, so new ones never wait behind the archive. The backlog is read batch after batch without waiting.
- `backend/scripts/read_pages.py` is the always-on reader (lock `data/page_reader.lock`; while it runs, the web app's own reading job stands aside). `--status` prints page counts. Log: `data/page_reader.log`.
- `backend/scripts/import_archive.py --app-db` adds downloaded archive files to the real library; safe to re-run. Database backup from before the import: `data/regwatch.before-archive.db`.
- `backend/scripts/register_reader_tasks.ps1` makes both permanent (tasks `RegWatchPageReader`, `RegWatchArchiveImport`); registering needs the user to run it once.
- Estimate: about 15,000 archive pages need image reading; at about 4,000 a day across 8 keys, about 4 days.
- Download rate is now 2 s between requests (decision 11 updated).

## Slow screens made fast: done (13 Nov late night, nothing committed)
The "Next task" prompt below is finished. Only our own design (the "b" parts) was changed; no paid model was switched on.

| # | Screen | Before (13 Nov) | After (measured on this PC, free tier, one key) | What changed |
|---|---|---|---|---|
| 1 | Admin, AI engine, Test connection | 38-145 s | 1.3-1.7 s | Tiny prompt on `gemini-3.5-flash-lite`, one try, 15 s timeout (`PROBE_GEMINI_MODEL`, `PROBE_TIMEOUT_SECONDS`). Busy (429/503/timeout) says "busy, try later" at once. Plain message, no codes. Result counts as the configured model's health. |
| 2 | Run analysis | 30-60 s with the button busy | Button answers in 0.25 s; the work ends in the background (20 s and 30 s in two runs) and the page redraws by itself | `analysis/jobs.py`: POST `/analyze` returns 202 RUNNING; GET `/documents/{id}/analysis-status` (IDLE/RUNNING/DONE/FAILED/UNCHANGED). The circular page polls every 2.5 s and picks up a run already going. "Analysis failed" now shows with a plain reason. Same pages + same model = not sent again ("Run it again anyway" forces it). Lease is 15 min so a slow run is not taken over. |
| 3 | Ask this circular / Search Ask | 30 s to 2+ min | Matching lines on screen in 0.08-0.23 s; written answer 1.8-8.9 s | New POST `/research/matches` (local search, exact page sentences, no model). Only matching sentences plus neighbours go to the model (about 5,000 chars per circular instead of up to 6,000 per page). Answers use Flash-Lite, one retry, 45 s timeout (`ANSWER_*` settings). |
| 4 | Admin, Check now | about 7 min | Answers right after the listing (well under 2 s in tests); downloads go on in the background with live counts | `background_ingest=True` on the manual trigger; GET `/sources/{id}/ingest-status`. Downloads use their own lock, so a listing check never waits for them; the shared request gate still keeps one request per 15 s. Screen: "N new found, adding them now: x of y done", then "Added N". A failed or blocked listing says "did not count", never "0 new". Live click NOT done here, to avoid clashing with the archive download running on this PC; covered by `test_phase2_source_monitoring.py`. |
| 5 | Bangla / scanned page reading | 12 pages in 2-4 min (10-20 s a page) | 8 pages in 45 s; 7 scanned pages in about 60 s (about 6-8 s a page) | Upload already woke the worker; now pages of one circular are read 2 at a time per key (`VISION_CALLS_PER_KEY`, cap `VISION_MAX_PARALLEL`), rotating over `GEMINI_API_KEY` + `GEMINI_EXTRA_API_KEYS` (comma list), committing after each batch. Circular page shows "Reading the page images: x of y pages ready" and fills in text by itself (polls every 4 s). Raw error text no longer shown on the page panel. |

Row 5 with more keys (done 13 Nov): `.env` now has `GEMINI_EXTRA_API_KEYS` with 7 extra free keys (8 in all, all tested OK; 3 new ones from the hozaifah626 AI Studio projects AgenticDev, libre, Natively). `VISION_MAX_PARALLEL` is now 8. A 7-page scanned circular was read in about 20 s, all pages at once. Google refused a new project on that account (project limit), so more keys would need another Google account. `new-api.txt` in the repo root holds one of the keys and is now git-ignored.

Checks: full pytest 368 pass, 5 fail, 1 error (the old data/setup failures: missing seeded genuine circulars and a missing stored file; none from this work). New tests: `backend/app/tests/test_speed_fixes.py` (11). `npm run build` and `npm run lint` pass. Browser checks done at desktop (Test connection, Run analysis incl. the unchanged skip and forced rerun with badge redraw, Ask with instant matching lines, live page-reading counter) and at 375 px (circular page, no sideways scroll). A test rewrote `backend/app/tests/fixtures/genuine_corpus/test_genuine_brpd_circular.pdf`; run `git checkout -- backend/app/tests/fixtures` before committing.

### For the user to decide (the "a" parts: a paid tier)
The rest of the waiting in rows 2, 3 and 5 is Google's free tier being busy (503) or capped per minute. Paid list prices found 13 Nov (third-party trackers quoting Google): Gemini 3.5 Flash $1.50 per million tokens in, $9.00 out; Flash-Lite $0.30 in, $2.50 out. Rough cost at about 10 new circulars a week (about 43 a month, 5 pages each, half needing image reading, about 200 questions a month): analysis on paid Flash about $2.60, Ask on Flash-Lite about $0.45, page reading on Flash-Lite about $0.45, so roughly **$3-4 a month** (estimate, not a quote). Expected effect: analysis about 5-15 s, page reading of 12 pages about 10-20 s with full parallel reading. The test connection and Check now need no paid model.

## Earlier on 13 Nov night
## What changed since the 13 Nov evening note (nothing committed)
- **4. Alerts: done.** Hooks wired into sources, analysis, relationships and compliance routes. Tests: `test_alerts.py` (24), `test_alerts_email.py` (12), helper `fake_smtp.py`. Screens: bell + panel in the header, `/alerts` inbox, `/alerts/settings` (with the admin email box), `/admin?tab=`. Spec 9.2 browser checks 1-9 and 11-15 passed at desktop and 375 px; check 10 (real SMTP) not done.
- Full pytest: 357 pass, 5 fail, 1 error (known old ones; `test_stats_truthfulness_and_department_deduplication` now passes in the full run, it depends on run order).
- **No technical details on screens:** SHA-256 removed from the admin upload message, upload help text, source box, evidence list and history line. Still stored in the backend.
- **Test logins:** `backend/scripts/seed_test_users.py` (run after `seed`) adds one login per bank role in ABC Bank, a second bank (XYZ) and a no-bank user. The list is in the TickTick task "RegWatch build test". `seed.py` no longer prints an emoji (it crashed on the Windows console).
- **`test-setup.bat`** in the repo root runs checklist A1-A8, C11-C12, then B9-B10, with logs in `test-logs\` (git-ignored).

## Next task: make the slow screens fast (prompt for the next session)

Paste this to start the next session:

> Read DECISIONS.md, then this section. In a full browser test on 13 Nov, five things were slow. Split each into (a) the part a faster paid model would fix and (b) the part our own design causes. **Build every (b) fix now.** Do not switch to a paid model: DECISIONS.md #8 says free first, and the user decides on paying. Write down the (a) part for the user to decide. Keep DECISIONS.md #2 as it is: one request to bb.org.bd at a time, 15 s apart. Every screen must show progress at once and update by itself when the work ends (the user's top rule: instant, never-stale UI). No technical codes on screen. Run the full pytest, `npm run build` and `npm run lint`, then check each fix in a real browser at desktop and 375 px.
>
> | # | What is slow (measured 13 Nov) | (b) Our design: build this now | (a) Paid model: user decides |
> |---|---|---|---|
> | 1 | Admin, AI engine, "Test connection": 38 s to 145 s. `POST /documents/provider-test` (`analysis/router.py`) makes a full call on `gemini-3.5-flash` with 3 retries and a 120 s timeout. It also spends the free Flash quota (about 17 a day per key). | Probe with a tiny prompt on `gemini-3.5-flash-lite`, one try, 15 s timeout. Show "Busy, try later" when the model answers 429 or 503, instead of waiting through retries. | None. A connection check doesn't need a paid model. |
> | 2 | "Run analysis": 30 s to 60 s, while the button blocks the screen. `POST /documents/{id}/analyze` runs inside the web request. | Run it as a background job, the same pattern as `extraction/vision_jobs.py`. The endpoint returns at once with "Analysing". The circular page polls, or uses the store, and redraws when it's done. Add an "analysis failed" status (a known leftover). Don't re-send unchanged pages: skip when the page hashes match the last run. | The free Flash tier often answers 503 "high demand", and the retry waits are most of the time. Paid Gemini 3.5 Flash, or a paid Flash-Lite tier, would cut it to roughly 5-15 s. Price it per circular for the user. |
> | 3 | "Ask this circular" / `/search` Ask: 30 s to more than 2 min. | Send only the top matching sentences, not whole pages, so the prompt is small. Use Flash-Lite for answers. Show the matching quotes at once (search is local and instant), then fill in the written answer when it arrives. | Same 503 waits as #2. A paid tier makes the answer itself fast. |
> | 4 | Admin "Check now": about 7 min with the button spinning. `sources/service.py::execute_source_monitoring` lists new circulars (under 1 s), then in the same request downloads and ingests up to 5 of them, 15 s apart, with page reading and analysis. | Return as soon as the listing is done: "10 new found, adding them now". Move download and ingest into the background worker, still one request per 15 s. The Review queue and Library counts tick up live. Never mark a failed or blocked listing as "0 new". | None. The 15 s spacing is a fixed decision, not a model limit. |
> | 5 | Bangla and scanned page reading: 12 pages took about 2-4 min (`VISION_POLL_SECONDS=60`, one page at a time, retries on 429/503). | Wake the vision worker the moment an upload queues pages, instead of waiting up to 60 s. Read pages of one circular in a small parallel batch within the free per-minute limit, rotating keys as `part_api.py` does. Show "Reading page 3 of 12" on the circular. | The free Flash-Lite per-minute limit caps throughput. A paid tier would allow full parallel reading, roughly 10-20 s for 12 pages. |
>
> Finish by writing the measured before and after times for each row in HANDOFF.md, and a short note for the user on the (a) items with the cost per month of a paid tier at about 10 new circulars a week.

Still to do: steps 5-7 below (analysis model pick, always-on startup after 19 Nov 18:00, Notion/TickTick update), then delete `.venv`, `frontend/node_modules`, `frontend/.next` before the user tests from scratch.

# Handoff: RegWatch (as of 2026-11-12)

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

## Detection test: two PCs reconciled (13 Nov)
- The always-on PC (the one with `E:\regwatch-research`) never paused. Its tasks `RegWatchDetectPoll` (every 10 min, Sun-Thu 09:00-19:00, hourly otherwise) and `RegWatchDetectReconcile` (02:00) use the same method as `research/detect/detect_test.py` (7-day date-filter POST, 15 s spacing). Their end date is now 19 Nov 18:00, the planned end of the test.
- This PC is now the only detection runner. Do **not** re-enable `RegWatchDetectPoll` / `RegWatchDetectReconcile` on the collecting PC: two runners would break the one-request-per-15 s rule.
- Result as of 13 Nov 11:20: 155 OK polls, 4 errors (all at night, DNS/connection drops), 6 new circulars caught (median 4.8 min, max 7.4 min after upload), 0 misses in 5 nightly full-list checks. The collecting PC's 12 Nov run caught the same 3 circulars that day. Its 16 timeouts did not happen here, so they most likely came from the archive download sharing the request lock.
- Latest numbers: `E:\regwatch-research\venv\Scripts\python.exe E:\regwatch-research\detect\summary.py`.
- `RegWatchArchiveDownload` stays on the collecting PC (its 1,021 files and state are there). If you resume it, expect it to slow nothing here, since it runs on a different machine.

## Build queue, latest (13 Nov evening; stopped by the user; nothing committed)
Done and checked in a real browser (desktop + 375 px), all uncommitted:
1. `/search`: full-text search with filters, highlighted snippets, deep link `/?doc=&page=`, "Ask a question" with exact-quote sources, "Corrected by / on / why" line on corrected pages.
2. Relationship map + compare: target linking (`relationships/linking.py`), in-force status (verified links only), `/circular/[id]/links` (timeline + SVG graph), `/compare`, admin Links tab. No migration.
3. Bank compliance workspace per `docs/specs/COMPLIANCE_WORKSPACE_SPEC.md` (defaults D1-D7 used): routes under `/workspace`, migration `a3c5e7f9b1d4`. Tests after this step: 317 pass, 6 fail, 1 error (the 7 old known failures).

Stopped half-way: **4. Alerts** per `docs/specs/ALERTS_SPEC.md` (defaults A1-A12). Partial files: `backend/app/modules/alerts/` (16 files), `backend/migrations/versions/b9d1f3a5c7e8_alerts.py`, `backend/app/core/storage.py` (shorter evidence path fix), `backend/app/tests/test_evidence_storage.py`. Not known: whether hooks, router registration or any frontend exists yet, or whether tests pass. Review `git status` / `git diff` first, then finish it.

Still to do, in order (one helper at a time):
5. Pick the analysis model (Opus writes the answer key from `E:\regwatch-research\gold\batches.json`, dev first, `validate_gold.py` to 0 errors; Sonnet builds the harness and runs free models; test split scored once; verdict in `research/06_VERDICT.md` + DECISIONS.md).
6. Always-on startup tasks for backend + scheduler on this PC, enabled only after 19 Nov 18:00.
7. Update TickTick task "RegWatch build test" (project 6ae6f48a8f0847e165e47f9b) and Notion page 417366f4-5d6d-8173-b470-c09e9af7c267 (send base64 through COMPOSIO_REMOTE_WORKBENCH).
Then delete `.venv`, `frontend/node_modules`, `frontend/.next` before the user tests.

Known leftovers from this round: re-running analysis on a circular drops earlier link approvals; no metadata-edit endpoint, so relinking after an edit is manual (`POST /relationships/relink`); page image in the source panel looked blank in one screenshot (not investigated); `/workspace` picker and modals not checked at 375 px; board report print preview not opened.

## Build queue (13 Nov, paused for usage limit; nothing committed)
- Done, uncommitted: sign-up in the account modal; admin "Edit text" page correction in PagePanel (tests in `backend/app/tests/test_signup_and_page_edit.py`; 219 pass, the 7 old failures remain).
- Stopped half-way: search screen `/search` (full-text search + ask across circulars + store page-correction reason/who/when). Review the working tree before continuing; it may hold partial edits.
- Still to do, in order, one helper at a time: relationship map + old-vs-new compare (Sonnet, spec by lead); bank compliance screens and alerts (Opus designs, Sonnet builds; alerts = in-app inbox + email when SMTP is set); analysis model pick (Opus writes the answer key from `E:\regwatch-research`, which still exists; Sonnet runs harness and models); always-on setup on this PC, enabled only after 19 Nov 18:00; then update the TickTick/Notion "RegWatch build test" steps.
- Before handing over for testing, delete `.venv`, `frontend/node_modules`, `frontend/.next` so the user's test starts from install.

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
- Never mention AI or an agent in any file, commit or doc. Never commit the local assistant settings folder or key files.
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
- **Nothing in `research/`, DECISIONS.md, HANDOFF.md is committed yet.**

