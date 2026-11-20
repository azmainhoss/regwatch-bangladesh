# RegWatch: decisions (read this first)

This is the single source of truth for architecture decisions. Last updated 2026-11-20.
- Where `docs/DECISION_LOG.md` or any older doc disagrees, **this file wins**.
- Only research from 2026-11-10 onward counts. Older notes (the Nov 5 ADRs and before) are out of date.
- A decision moves from "Open" to "Decided" only after a test on 100+ real circulars, scored on the held-out test split.

---

## Decided

### 1. Spotting new circulars
- **Use our own small Python script.** It asks the circular page's date filter for the last 7 days:
  `POST https://www.bb.org.bd/en/index.php/mediaroom/circular` with body `from_date=YYYY-MM-DD&to_date=YYYY-MM-DD&search_circular=Search`.
  No token or cookie is needed. The reply is about 50 KB and comes back in under 1 s.
- **Schedule:** every 10 min Sun-Thu 09:00-19:00 Bangladesh time, hourly otherwise.
- **Key each item by its PDF URL.** Compare parsed rows, not raw HTML.
- **The only backup is a nightly full-list check** (about 2.6 MB, 02:00) to catch anything the checker missed.
- **Dropped as unneeded:** changedetection.io, the homepage ticker watcher, news watchers, paid scraping services
  (Firecrawl, Bright Data, Zyte and the like) and AI scrapers (Crawl4AI and the like).
- **Confirmed by the live test, 10-19 Nov 2026** (numbers in `research/06_VERDICT.md`, Step 1):
  - All 10 new circulars were caught, 6 min after upload on average (median 5.8 min, worst 7.5 min).
  - The nightly full-list check found 0 missed circulars in 9 runs. **Keep it** as the safety net; it is the only proof that nothing slipped past.
  - Keep the schedule as it is. All 10 circulars were uploaded on working days between 11:20 and 16:30, so the hourly off-hours check is enough.
  - **One failed check is normal and needs no alarm.** 17 of 388 checks (4%) failed on a dropped connection or a DNS failure, and the next check always worked. Count it as "failed, try later" (decision 2). Tell the admin only if checks keep failing for more than an hour.
  - **Run the live checker on its own, apart from bulk downloads.** On 12 Nov, on the other PC, it shared one request queue with the archive download and 16 of 25 checks timed out. On the always-on PC, where they ran as separate tasks, there were no timeouts.

### 2. How the script talks to the site
- **It uses its own name, `DocFetchBot/1.0`, not a fake Chrome identity.**
  - The only block seen on 2026-11-10 came from a fake Chrome name with requests 3 s apart.
  - The same downloads under the script's own name, 10 s apart, all worked.
  - 126 PDFs downloaded 15-20 s apart (38 min) with no block.
- **About 15 s between PDF downloads. One request at a time.**
- **A "Request Rejected" page for one URL means skip that file, not a block.** Two files in the sample are like this.
  Other files keep downloading fine.
- **A challenge page ("What code is in the image", /TSPD/) or a page with no table means "failed, try later".**
  It never means "nothing new". This rule exists so we never silently miss a circular.
- **No legal or "ethics" angle.** Downloading public circulars is normal. Dropped by the user, 2026-11-10.

### 3. Hosting
- Run from Bangladesh. The user's home connection is fine for now. A small Bangladeshi server later.
- **The home laptop is not good enough for the live checker at launch** (live test, 10-19 Nov). It was off or asleep for two full working days (Sun 15 Nov and Tue 17 Nov) and most of a third afternoon (Wed 18 Nov). Nothing was missed only because nothing was published in those hours. Launch needs a machine that stays on.
- **The site never showed a challenge page to the checker** in 388 checks over 9 days under the name `DocFetchBot/1.0` from a home connection. This confirms decision 2.

### 4. Official access
- The user emails webmaster@bb.org.bd asking for a feed or an IP allow-list
  (TickTick task in "RRH Tasks", due 11 Nov 2026). This is a nice-to-have; the app doesn't depend on it.

### 5. Archive
- Keep every original PDF unchanged, with its SHA-256, ETag and Last-Modified.
- Re-check old files' ETags now and then to catch silently replaced files.
- A changed file becomes a new version, and the old one is kept.

### 6. Reading English PDFs
- Use the PDF's text layer with PyMuPDF, pinned below version 2 (2.x pulls in a heavy layout model).
- All English pages tested were clean text, never scanned.

### 7. Quotes
- The AI never types quotes. It returns sentence or span IDs, and code copies the exact text.
  In testing this raised word-for-word quote accuracy from 29-80% to 85-92%.

### 8. AI budget
- **Testing uses free models first (user's choice, 2026-11-10).** This is not a ban on paid models.
  If the best free option isn't good enough on the test split, the verdict says so and names the paid model to try next,
  and the user decides whether to pay. The free candidates are:
  - Gemini free tier: Flash, Flash-Lite and Gemma 4 (Pro is blocked on free);
  - free OpenRouter models;
  - SambaNova;
  - local models.
- No other paid models (such as GPT) for now. They can be tested later if free falls short.
- Keys: GEMINI_API_KEY in the shell environment, plus `F:\Projects\titan-title-review\.env`.
  The project's own `env` file has empty key lines.

### 9. Competitor
- RegAlert (regalert.today) already covers Bangladesh Bank circulars. It's the benchmark we'll be compared against.

---

### 10. Reading Bangla and scanned pages (decided 2026-11-11, test split; second-reading rule replaced 2026-11-14)
- **Send every Bangla or scanned page to Gemini 3.5 Flash-Lite as an image.** It scored 4-7% CER on the test pages, and 94% of numbers came out exact.
- ~~Also read each one with Gemini 3.5 Flash. If the two readings agree within 2%, the page passes.~~ **Replaced 2026-11-14 by `docs/specs/CLAIM_CHECKS_SPEC.md` section 7 (built as chunk 4):** only the quoted sentences are read a second time, from a crop of their lines (Flash, tie-break on a sharper crop with Flash-Lite). A quote passes when the readings match: same numbers, negations and reference codes, and at most 3% other difference. Otherwise the point is hidden and a person checks it. The thresholds (3%, word lists, crop margins) are provisional until plan step 4 tunes them on dev and scores them once on test. First live run (2 circulars, 35 sentences, 17 calls): 31 matched, 2 misread (one real digit error), 2 unclear.
- **Dropped:**
  - the Bijoy converters (22.7% CER on test pages, after 2.9% on tuning pages);
  - Tesseract;
  - Gemma 4, Gemini 3.8 Flash and the free OpenRouter models (too slow or unavailable on free tiers).
- **English pages:** keep PyMuPDF (decision 6). Pages with Bijoy, legacy or broken-Bangla fonts go to Gemini.
- Details: `research/06_VERDICT.md`.

### 11. Downloading the full archive (decided 2026-11-13)
- **Own name `DocFetchBot/1.0`, one request at a time, 2 s between requests.** (Started at 3 s; moved to 2 s, the fastest tested-clean rate, on 13 Nov at the user's request.) The speed test (300 files at 5 s, 3 s, then 2 s) had no challenge page at any rate.
  Never below 2 s; no parallel requests (untested, and a block would also stop the live detection test). Details: `research/archive/SPEED_TEST.md`.
- **Runs 24/7** on the always-on PC as the scheduled task `RegWatchArchiveDownload` (`research/archive/fetch_all.py run`). The 10:00-18:00 window is dropped for downloads.
- **Back-off on a challenge page:** 30 min, doubling up to 6 h; after 3 blocks in one day it stops and writes `data/STOPPED`.
- The 15 s spacing in decision 2 still applies to the app's own live checker. The 2 s rate is for the one-off bulk download only.
- Loading into the app: `backend/scripts/import_archive.py` (stores and reads pages, no analysis).

### 12. Reading the archive's Bangla and scanned pages (decided 2026-11-13, replaces the 12 Nov hand-reading plan)
- The app reads them itself with all free Gemini keys (`gemini-3.5-flash-lite`, the reading benchmark winner), rotating keys, newest circulars first, via `backend/scripts/read_pages.py`.
- Free limits: 15 a minute and 500 a day per project, no weekly or monthly cap. A key out of daily quota rests until the reset; quota or busy replies never count against a page.
- ~~Hand reading through the Gemini app stays as the fallback for pages that fail.~~ Replaced 2026-11-20 by decision 15 (automatic stronger route, then READ_FAILED; no person).
- Build phase runs on free tiers only; the paid tier is bought at the end (also needed before launch so private bank uploads are not sent to the free tier).

### 13. Claim-level checks (decided 2026-11-13; spec `docs/specs/CLAIM_CHECKS_SPEC.md`)
- Each point of an analysis is checked and hidden on its own; the rest of the circular still shows.
- **Bangla golden rule wording (replaces decision 10's page-level rule once chunk 4 is built):** quotes appear word for word in our reading of the page, and that sentence's reading was confirmed by a second reading.
- **Provisional, to be settled by measurement in plan step 4:**
  - Summary and "what changed" lines show once code checks pass. Keep or tighten based on how much accuracy the later meaning check (plan step 6) adds.
  - "Amends / replaces X" shows only as "mentions X" until reviewed. Measure how often the automatic call is wrong compared with review, then decide whether review is still needed.
  - The archive is fully processed by us before launch; customers only read it. So held archive points are not left hidden for good: before launch they all go through review, newest first (the 12-month line only sets the order). The "usually within one working day" promise applies only to new circulars after launch.
  - Hidden points still link to the page with their quoted lines highlighted, when the quote itself passed (spec 5.1).
  - During testing, the reviewer for held points is a review pass run by the build team's own checker, standing in for the platform team.

### 14. Analysing the archive before launch (decided 2026-11-14, user's choice: no budget for a paid model yet)
- **Only the circulars issued on or after 2024-11-14, plus every Master Circular, are analysed before launch** (668 circulars).
  The rest of the archive stays searchable with its page text, marked as not yet analysed.
- **They are analysed by hand in a coding session on the user's subscription**, the same way the dev answer key was written,
  in the app's own JSON format. `backend/scripts/manual_analysis.py` hands out each circular with sentence IDs and loads the
  answers through the normal pipeline, so every point gets the same code checks as a live model's.
- **Runs in the cloud** (changed the same day, so it does not depend on which account this PC is signed in to):
  the cloud routine "RegWatch circular analysis" (every 5 hours) works on the private repo
  `hozaifa1/regwatch-analysis-work` (circular texts with sentence IDs, rules, a standalone checker, QUEUE.txt, answers/).
  It follows that repo's RUNBOOK.md, at most MAX_PER_RUN circulars per run, and pushes each answer.
  The Windows task RegWatchAnalysisSync (`backend/scripts/sync_analysis_repo.ps1`, hourly, no extra account needed) loads
  new answers into the app and pushes newly read circulars to the repo. The local scheduled task is disabled.
- **Three lanes from 2026-11-20** (supersedes the two-lane line below): RUNBOOK.md splits QUEUE lines by line number
  mod 3. Lane 1 = account A (unchanged), lane 2 (account B) retired, lane 3 = account C (30k/run),
  lane 4 = account D trial (70k/run). Each lane runs every 5 hours.
- **Two accounts, two lanes** (2026-11-14): lane 1 = the desktop app's account (odd QUEUE lines, 06:20/11:20/16:20/21:20/02:20
  Dhaka), lane 2 = the account B account (even lines, 03:50/08:50/13:50/18:50/23:50 Dhaka). Each run stops at about
  30,000 characters so each account keeps half its weekly limit. Short circulars first; launch need not wait for the 27 long ones.
- First trial (3 circulars, 2026-11-14): all loaded. Most hidden points came from the checker, not the answers:
  Bangla circular names are not matched to the English target name, and a duty word in a lead-in sentence is missed.
  Fixed the same day: Bangla department and "circular" words are read as English when matching references
  (`relationships/linking.py`), and Bangla directive phrases, "সাপেক্ষে", applications and "only if" limits count as duty
  wording (`claims/wording.py`). Tests: `test_bangla_references_and_duty_words.py`.
- New circulars after launch: the paid API once there is money; until then the same hand run.
- A circular is handed out only when every page has usable text (none waiting, none unread or damaged). One handed
  out too early is taken off the queue until read; those already analysed are listed in `REDO.txt` (2026-11-20).

### 15. No page is ever left for a person (decided 2026-11-20, user's rule; replaces "the page goes to a person" in 10 and 12)
- **Page reading never ends with a person.** The old status NEEDS_HUMAN_REVIEW (from the 5 Nov quality checker, used by the
  page reader since the 12 Nov page-reading work) is no longer set for any page.
- **Retry path:** a failed page is tried again on the next key with `VISION_MODEL` (Flash-Lite) up to `VISION_MAX_ATTEMPTS` (5)
  times, then on the stronger route, `VISION_FALLBACK_MODEL` (Flash) on a 300 dpi image, `VISION_FALLBACK_ATTEMPTS` (2) times.
  Busy, out-of-quota and dead-key replies never count as a try.
- **Last resort:** status READ_FAILED (no text). Such pages are listed in `data/unread_pages.md`, and their circular is not
  handed out for analysis. Admins get the usual daily queue alert ("N pages could not be read").
- **Damaged text layers** (broken characters, runs of odd symbols) are read from the page image; short clean pages keep their
  text and count as read.
- **Tesseract stays dropped** (decision 10: worse than Flash-Lite on the test pages). It is not installed on this PC; adding
  it as a third route would need a download and a fresh test.
- Claim checks (decision 13) are separate: points that fail their checks are still hidden until decided.
- Old flagged pages are cleared by `backend/scripts/requeue_pages.py --yes` (dry run without it).

## Open (being decided by the benchmark; the verdict goes in `research/06_VERDICT.md`)
- **Analysis:** which free model or method extracts metadata, obligations, applies-to, deadlines, links to other circulars and the English summary.
  Rules are ruled out as the main method: they were tuned on 8 docs and got 26-28 of 40 others right.

## Not researched yet
- Storage and database, search and the Q&A assistant, alert channels, the front end and workspaces.

---

## How research is done (rules)
- **Sample:** 130 random circulars (seed 20261110): 100 from the whole archive plus 30 from 2025-2026.
  That gives 139 PDFs and 880 pages, in `E:\regwatch-research\`.
- **Split, frozen and read-only:** dev (40 circulars) is the only data used for tuning. Test (90) is scored once, at the end.
  Files: `split_FROZEN.json` and `reading_subset_FROZEN.json`, with hashes in `FROZEN.sha256`.
- **Gold answers:** the page transcriptions were written by the strongest model on the plan. The analysis answers are written by a lighter model,
  one at a time, to stay inside the usage limit. Every quote is checked by code, and I audit 10% by hand.
- **Scoring is by code wherever possible.** A number measured on data it was tuned on is never reported.
- **Tuning uses the autoresearch skill (user's instruction).** It runs overnight loops of "change one thing, score, keep or discard",
  on the dev split only. It tunes:
  - the Bijoy converter fix-ups;
  - the prompts and method (whole document, span pointer, hybrid) for the top free analysis models;
  - how pages are routed between the converter, OCR and vision.
  It starts once the gold answers exist, because it needs a score to chase. The finalists then run once on test.
- **Final answers:** one verdict per step, with test numbers. No caveats left for the user to resolve.

## Running tests
- **Detection test: finished 19 Nov 18:00.** Verdict in decision 1 and `research/06_VERDICT.md`. Its tasks `RegWatchDetectPoll` and `RegWatchDetectReconcile` were disabled on 20 Nov (kept, not deleted; full delete commands in `E:\regwatch-research\detect\REMOVE_TASKS.md`). Data stays in `E:\regwatch-research\detect\`.
- **Reading test:** outputs in `E:\regwatch-research\reading\`.

## Research files
- `research/01-04`: the 2026-11-10 findings.
- `research/05_TEST_PLAN.md`: the benchmark plan.
- `research/06_VERDICT.md`: the final verdict (not written yet).
