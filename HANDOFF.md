# START HERE (26 Nov 2026): SEO live

- What was built is in `docs/CHANGELOG.md` (26 Nov) and the keyword research in `docs/seo/KEYWORDS.md`.
- **SEO and analytics guide** (accounts, Search Console, PostHog, IndexNow, weekly routine): `docs/seo/SEO_GUIDE.md`.
- **Deployed 26 Nov.** Live: `/circulars`, `/circulars/<dept|year>`, `/circulars/topic/<subject>`, `/llms.txt`,
  sitemap with about 450 addresses, IndexNow key at `/60b49caa6f7be62ceb2165ea3dc93699.txt`.
- **Google Search Console:** domain property amarcircular.com (Google account hozaifah626), verified by a TXT record
  in Cloudflare; sitemap submitted; home, /circulars, /circulars/brpd, /circulars/2026 sent for indexing.
- **Bing Webmaster Tools:** amarcircular.com verified by a CNAME record in Cloudflare; sitemap submitted.
- **IndexNow:** first try got 403 "SiteVerificationNotCompleted" (normal for a new key); it retries hourly. Check
  `journalctl -u regwatch-backend | grep IndexNow` for "sent N new pages".
- Only "Ready" circulars are indexable (393 live); the 275 "Analysing" ones stay `noindex` (owner's decision,
  DECISIONS.md 16). Popular circulars reach Google by getting verified.
- **Dated future tasks** (content, links, weekly checks): TickTick project "amarcircular seo".
- OpenSEO (app.openseo.so) account exists, free trial, about $0.30 credit left. Its keyword tool works in the browser.

# Visitor analytics (26 Nov 2026)

- **PostHog** (us.posthog.com, project "Amar Circular", id 767935, signed in with Google). Code: `frontend/services/analytics.ts` + `components/Analytics.tsx`. Runs only on amarcircular.com; sent through `/ingest` (rewrites in `next.config.js`) so ad blockers don't drop it. Records page views, time on page, clicks, heatmaps and session replays (typed text masked). Signed-in readers are identified by account id with email, name, phone, admin flag; company and designation are added when a reader finishes sign-up step 3. Events: `signed_up`, `signup_details_completed`.
- Project settings done: session replay on, heatmaps on, time zone Asia/Dhaka. Still to do after the first real events: an internal-users filter on `is_admin = true`.

# START HERE (24 Nov 2026): go-live polish, sign-in gate, free launch

- **Launch is free for everyone, sign-in required.** Plans and prices are gone from every screen (`/plans` redirects home); the Free plan in `plans/plans.py` allows every feature with no question cap. Signed-out visitors see only a full-page sign-in (`components/AuthGate.tsx`, `AuthForm.tsx`); the backend refuses anonymous reads too (`documents/access.py` `get_document_reader` -> 401, plus `/institutions`, `/sources*`, `/documents/provider-status`, `/feed/topics`, `/plans`). Health and `/auth/*` stay open. Tests read as an ordinary signed-in user (`tests/factories.py` `signed_in_reader`); `test_sign_in_required.py` checks the 401s.
- **Circular page:** every section folds (Collapse all / Expand all); long lists show the first few with "Show N more"; long texts clamp with "Read more"; previous/next circular arrows (and J / K keys); phone action bar shows the main buttons plus "More"; duplicate title under the list row hidden on phones.
- **Source-page preview:** opens zoomed to a readable size and scrolled to the highlighted quote ("Highlight" button re-centres); zoom 100-400% by buttons, +/- keys, Ctrl+wheel / trackpad pinch, two-finger pinch on phones, double-click; drag to pan; full-screen button; one compact toolbar row. Wide screens hide the circular list while the preview is open. Phones: bottom sheet with backdrop and the page behind locked. Text view joins PDF line wraps into paragraphs.
- **Navigation:** phone bottom tab bar; phone top bar holds a search field. The internal progress page `/summary` is admin-only ("Status" in the nav), wording "in scope" instead of "launch".
- **Wording:** no "today's free limit", "did not pass our checks" or "Checked against page N" left for readers.
- **Mind map:** phones open an Outline view (full-text tappable cards), Diagram tab scrolls sideways; desktop uses one trunk line, root stays near the top, points cut at a word after 4 lines; "(by within 14 days)" fixed in the map and in emails (`share/mail.py`).
- **Links graph:** citations not in the library are keyed by number + year (Bangladesh Bank restarts numbers yearly), labels split into number and short date; phones get a list of link cards instead of the hidden graph.
- **Register deadlines in words:** analysis now stores `deadline_text` on the obligation (`analysis/service.py`, `claims/status.py`); register items take it from the obligation's checked point (`compliance/router.py` `deadline_words`). **Run once on the real database:** `.venv\Scripts\python.exe backend\scripts\backfill_deadline_text.py --yes` (dry run without `--yes`). Lists show "None stated" when the circular gives no deadline.
- **Register names** no longer repeat the circular number.
- **Checks:** full pytest 490 pass, 5 fail (the old known ones: stats truthfulness, end-to-end AI pipeline, human review workflow, genuine documents status, authenticated QA). `npx tsc --noEmit`, `next lint` and `next build` pass. Browser-checked at 375 px and desktop, light and dark, on the local seed data plus two hand-analysed circulars (FEID 04, BRPD 15/2024).
- **Analysis backfill is done:** `hozaifa1/regwatch-analysis-work` has 622 answers on `main` (all 634 queued answered or skipped; 12 skipped for unreadable text; 31 long ones in `inbox_long/` wait). They load only into the laptop's `data/regwatch.db` (sentence IDs point at its pages).
- **Hosting warning:** `render.yaml` uses SQLite + local storage on Render Free, whose disk is wiped on every restart. `STORAGE_DRIVER=s3` is a setting with no code behind it. The live database and `storage/` belong on one always-on server (see the go-live decisions in the project notes).

# Earlier: 21 Nov 2026, evening: TickTick "Regwatch" list built

- **Built and tested in Brave (commits 88a14f6, c833fde, 3fb632a, local only):** dashboard home (Today / This week / This month / Read later boxes, Ask a question, Assigned box), Departments + Categories tabs (31 categories in `topics/taxonomy.py`, all 4,789 circulars sorted by Flash-Lite via `backend/scripts/classify_topics.py`; new circulars are sorted by the live checker after each check), stronger search (short forms like ECL expand to "expected credit loss", whole-word only, words may sit on different pages, summaries and categories count), Favourites / Read later / own lists (`/me/lists`), original PDF in the right panel, back links strip, arrow-key page navigation, mind map from checked points (big window, emailable picture), Assign to team (`/share/assign`, shows on both dashboards) and Email (`/share/email`, summary + mind map + PDF attached; `.eml` download when SMTP is off), plans Free / Pro / Enterprise (min 20 seats; `plans/plans.py`; admin tab "Plans" switches one on), installable web app (manifest, `public/sw.js`).
- **Bot checks:** the checker keeps the site's cookies, falls back to the full list when the date filter is challenged, and waits at most 2 h. Back-off cleared and `RegWatchLiveChecker` restarted on 21 Nov.
- **Waiting on the user:** plan prices (placeholders: Pro Tk 2,500/person/month, Enterprise Tk 1,800/seat/month); SMTP settings for real email (Brevo per hosting plan); a live domain before a Play Store app (TWA) can be built.
- **Tests:** full suite 487 pass, 7 fail + 1 error, all old known ones (`test_human_review_and_publication_workflow` fails because no point waits for a person any more).
- Demo banks are on Enterprise (`backend/scripts/seed_demo_plans.py`). Design page: https://claude.ai/artifact/NCjxu3xD8vbWjh37V8B5kf

# START HERE (20 Nov 2026, end of day)

- **Model plan (settled):** the backfill of ~635-670 past circulars runs on subscription scheduled tasks. Live circulars use a paid model API, bought only at launch (~$20/month); until then they run through the subscription app. Free-model and Gemini tuning loops are dropped.
- **Backfill lanes:** lane 1 account A; lane 2 (account B, account B2) retired via the runbook; lane 3 account C (current); lane 4 rrh trial (account D), no per-run cap. 245 of 635 done; finish expected 28-30 Nov.
- **Live checker:** detection test passed; registered on the laptop as `RegWatchLiveChecker`.
- **Page reader:** no longer parks pages for human review. It retries across keys, then a bigger Gemini model, and lists unread pages in `data/unread_pages.md`.
  - User still to run: `backend/scripts/requeue_pages.py`, then restart the `RegWatchPageReader` task.
  - The 9 "redo" circulars: settled, no redo needed (see below).
- **Git:** everything is committed on local `main` (latest f4b3f6b, 6 commits ahead of `origin/main`, not pushed). The scorer, research and notes files went in with 6c29d3f.
- **Hosting:** one free Oracle Cloud server (Mumbai) for both apps; BankEye on Turso; the laptop scans the 3 banks that block cloud IPs. Waiting on the user to create Oracle and Cloudflare accounts.
- **Rule:** no human review step, ever. Avoid repeated permission prompts.

- **The 9 "redo" circulars needed no redo (20 Nov, later).** Their 21 "damaged" pages were clean English forms; the damaged-text check counted dotted fill-in lines ("Name: ……"), Bangla vowel signs and Word bullets as garbage. Check fixed (`extraction/quality.py`); the 21 pages and 147 more wrongly requeued clean pages got their exact text layer back (DB copies `data/regwatch.before-restore-*.db`). All 281 shared-repo answers match today's page text, so nothing was removed. REDO.txt approvals cleared.
- **New circulars never go to analysis with a bad page.** Ready = every page `SUCCESS_*` with text that passes the damaged-text check (not just "none waiting"). Order per page: text layer -> Gemini (main, then stronger) -> last route (`extraction/strong_reader.py`, one read of the page image; needs `STRONG_READER_API_KEY` and `STRONG_READER_MODEL` in `.env`) -> circular held + admin alert. A hand-started analysis with a bad page holds every point for a person.
- **Until the last route has a key, held pages are read by hand.** Any coding session on this laptop: run `.venv\Scripts\python.exe backend\scripts\held_pages.py list`, open each page image it writes (`research/archive/data/held_pages/`), write the exact transcription to a text file (page's own language, numbers and dates as printed, table rows with " | "), then `held_pages.py save <page_id> <file>`. The circular is analysed once all its pages are clean. The hourly sync (`sync_analysis_repo.ps1`) writes a `held:` line to `research/archive/data/manual_analysis/sync.log` when such pages exist. On 20 Nov: 0 held pages.

- **Badges (20 Nov, later):** banks see only "Checked" (analysed; only points that passed every automatic check are shown) or "Not checked yet". No point waits for a person: a failed point is hidden, a change-the-law link that passed every check shows as "Mentions". The 1,508 points that were waiting were routed again (`backend/scripts/reroute_waiting_points.py`, DB copy `data/regwatch.before-reroute-*.db`). Admins see "Hidden: failed a check (re-check pending)". **Next work:** a coding session re-analyses hidden points automatically; rewrite the 29 old review-desk tests skipped in `backend/app/tests/conftest.py`.

(Older notes below may be out of date where they conflict with this section.)

# Handoff: RegWatch (as of 2026-11-20, latest)

## Plan changed on 20 Nov (user's decision; overrides the autoresearch "START HERE" below)
- **The free-model tuning loop is dropped.** No more scorer rounds on free Gemini (round 14 never ran). The archive backfill (about 670 circulars, DECISIONS.md 14) runs on subscription scheduled tasks, and live analysis of new circulars moves to a paid model API (key still to be wired).
- New order: (1) finish reading the Bangla archive pages, (2) backfill of the ~670 circulars on subscription scheduled tasks (already set up by the user, nothing to do), (3) wire the paid API key for live analysis, (4) run 24/7.
- Commit `b874f8d` (claim checks, prompt v4, page reader) is made, not pushed. The scorer, research and notes files are still uncommitted.

## Step 1, reading the Bangla archive pages (20 Nov, uncommitted)
- State before: 17,500 pages read (7,691 from the PDF text, 9,778 from the page image), 141 waiting, 1,117 sent to a person. Of the 1,117: 271 failed only because their key's project was suspended on 14 Nov, 802 were never read from the image at all (the PDF text looked damaged, so they went straight to a person; about half are legacy-font Bangla, the rest English forms with dotted lines), 44 really failed (no text in the answer).
- Built: a deleted, suspended or invalid key (`vision.is_dead_key_reply`) is benched for the rest of the run and never counts as a failed try on the page; the reader stops with a plain log line when no key works. New uploads: a text layer with broken characters or runs of odd symbols (`quality.text_layer_looks_damaged`) is read from the page image instead (`extraction/service.py`, reason `damaged_text_layer`), with the text layer kept in `native_text` for a person; a page that is only short keeps its text as before. Tests: `test_page_requeue.py` (9). `test_vision_job_reads_pending_pages_and_stores_boxes` was flaky (about 1 run in 5, parallel reads finish in any order); it now checks content, not order.
- `backend/scripts/requeue_pages.py` (dry run unless `--yes`, saves a database copy first) sends wrongly flagged pages back. Dry run with `--repo F:\side-income\regwatch-analysis-work`: 271 key pages (154 circulars) + 529 damaged pages (152 circulars) go back = 800 pages; 124 damaged pages in 35 circulars stay, because those circulars are already analysed or handed out and replacing their text would change sentence IDs their answers cite; 149 short clean pages keep their text; 44 stay with a person. **Not run yet:** reading the 800 pages costs page-image calls, which needs the user's yes on which reader to use (the free Gemini page reader is still running, or the subscription route).
- Gap fixed (20 Nov): `manual_analysis.py export` used to hand a circular out once no page was *waiting*, so pages with a person went out blank or garbled. Now a circular is held back until every page has usable text (`targets()` field `unread` = waiting + pages with a person that are empty or damaged; short clean pages don't count). An unanswered held-back circular is taken off the cloud queue (`inbox/`, `inbox_long/`) and goes out again by itself once read. At the next hourly sync this takes 31 circulars off the queue (40 of the 668 have unread pages). Tests: `test_manual_analysis_export.py` (5).
- REDO list: `research/archive/data/manual_analysis/REDO.txt` (new `manual_analysis.py mark-redo`) holds the 35 circulars that went out with damaged pages. 26 are unanswered: the requeue script re-reads their damaged pages and the export re-sends them once read, then drops them from the list. 9 are already analysed in the app: their 21 damaged pages are left alone, and the export lists them as "fully read but already analysed" only once read. Replacing those analyses (removing the old answer from the shared repo) is the user's call.
- **No page goes to a person any more (20 Nov, DECISIONS.md 15).** Failed page -> next key (Flash-Lite, 5 tries) -> Flash on a 300 dpi image (2 tries) -> READ_FAILED, listed in `data/unread_pages.md`. The status NEEDS_HUMAN_REVIEW came from the 5 Nov quality checker (commit 646f385) and the 12 Nov page reader (7540dfe) sent failed pages there; nothing sets it now. Screens say "Could not be read"; admin alert "N pages could not be read". Tesseract is not installed and stays dropped (decision 10). The requeue script now also marks the 149 short clean pages as read and sends the 44 real failures straight to the stronger route; only the 21 damaged pages of the 9 analysed redo circulars keep the old status until the user decides.
- **Requeue not run yet.** The user said yes (free Gemini, existing keys), but this session's safety check refused `requeue_pages.py --yes`. Dry run now: 271 key pages + 632 damaged pages = 903 pages go back; 21 pages (9 analysed circulars) stay; 149 short clean pages are marked as read; 44 real failures go to the stronger route. To run it: `.venv\Scripts\python.exe backend\scripts\requeue_pages.py --repo F:\side-income\regwatch-analysis-work --yes`, then `read_pages.py --status` should show PENDING_VISION go up and fall as the reader works.

## Check on 20 Nov (nothing committed)
- The 13 Nov evening "Build queue" items 1-4 (`/search`, relationship map + compare, bank workspace, alerts) are all in commit 8daf4c4, already pushed. Alerts is finished: hooks in sources, analysis, relationships, compliance and claim review ("new circular" once per circular, never for archive circulars). Nothing alerts-related is left half-done. Only open alerts item: spec check 10 (a real SMTP send), which needs the user's mail settings.
- Uncommitted work is all from 13-14 Nov after that commit: claim checks (chunks 1-4), prompt v4 + `deadline_text`, autoresearch scorer, speed/page-reader changes. 9 frontend files show as changed only because of line endings (no content change).
- Full pytest (20 Nov): 476 pass, 6 fail, 1 error. Same 7 as 14 Nov, all missing seed data or setup: `test_document_stats_endpoint_truthfulness`, `test_second_genuine_document_generalisation_brpd15`, `test_end_to_end_ai_pipeline_on_corpus_document`, `test_genuine_documents_honest_publication_status`, `test_authenticated_regulatory_qa` (no seeded SMESPD circular), `test_storage_immutability_and_sha256`, error in `test_alembic_lifecycle_full_upgrade_and_downgrade`. Alerts tests: 36 of 36 pass. The run rewrote `backend/app/tests/fixtures/genuine_corpus/test_genuine_brpd_circular.pdf` again; restore it (`git checkout -- backend/app/tests/fixtures`) before committing.
- Next: the user approves the commit split; then the 14 Nov autoresearch loop below.

## Detection test finished (20 Nov; nothing committed)
- The live test ended 19 Nov 18:00. **Verdict: decided.** 10 of 10 new circulars caught, median 5.8 min and worst 7.5 min after upload, 0 missed, 0 challenge pages, 17 of 388 checks failed and each recovered on the next try. Full write-up: `research/06_VERDICT.md` Step 1; rules in DECISIONS.md 1 and 3.
- On this PC (Hozaifa-Laptop, the always-on one with `E:\regwatch-research`) `RegWatchDetectPoll` and `RegWatchDetectReconcile` are now **disabled**, not deleted. Still running and untouched: `RegWatchArchiveDownload`, `RegWatchArchiveImport`, `RegWatchPageReader`, `RegWatchAnalysisSync`.
- **The other (collecting) PC** can't be reached from here. Its own copies of `RegWatchDetectPoll` / `RegWatchDetectReconcile` (running `research/detect/detect_test.py`) were paused on 12-13 Nov. On that PC, check they're still disabled or delete them with `schtasks /delete /tn RegWatchDetectPoll /f` and `schtasks /delete /tn RegWatchDetectReconcile /f`.
- App's own live checker (user said yes on 20 Nov): `backend/scripts/live_checker.py` runs only the monitoring schedule, no web server (09:00-19:00, every 10 min Sun-Thu, hourly Fri-Sat, full-list check 18:50; overnight uploads are caught at 09:00 by the 7-day filter). Log `data/live_checker.log`. Its task is registered by `backend/scripts/register_live_checker.ps1`; as of 20 Nov the user still has to run that script once (this session was not allowed to). Never also run the web backend with `SCHEDULER_ENABLED=true`. Long-term home: an always-on machine.

## Archive download (13 Nov, always-on PC; nothing committed)
- Full archive: 5,191 PDFs (1,226 English, 3,965 Bangla) in about 4,800 circulars, downloading into `research/archive/data/pdfs/` (git-ignored).
- Rate: one request every 3 s, 24/7 (speed test clean down to 2 s; see `research/archive/SPEED_TEST.md`, DECISIONS.md 11). Scheduled task `RegWatchArchiveDownload`; it restarts itself and backs off on a challenge page.
- Status any time: `E:\regwatch-research\venv\Scripts\python.exe research\archive\fetch_all.py status`. Full report: `research/archive/ARCHIVE_REPORT.md`.
- Load into the app when the download is done: `.venv\Scripts\python.exe backend\scripts\import_archive.py --app-db` (default without the flag is a throw-away test database). No analysis is run.

## START HERE: autoresearch state (14 Nov, after the overnight loop; nothing committed)

**Paste this to start the next session:**

> Read DECISIONS.md, `research/scoring/AUTORESEARCH_LOG.md` and this section. Continue the dev-split autoresearch loop from the kept state (SCORE 21.04, leak 17.8%) with candidate `gemini_flash_v6_types` (its prompt is now the app's own prompt v4). One change per round; keep it only if SCORE rises and the leak rate does not. Next targets, cheapest first: (1) false alarms are 22% (72 right claims hidden): look at DUTY_WORDING, WHO and NUMBERS failures on right claims with `--rescore-only`; (2) dates the model misses (104 "from 01/01/2027", 1484, 3056); (3) links score is only 18%. Do every step yourself (no subagents). Do not change the scorer's rules without the user's yes. When the loop stalls: price the paid candidates (`price.py`, vendor price pages, OpenAI first) and show the user the total before any `--yes-spend`.

**What changed (14 Nov):**
- Answer key for the 40 dev circulars is in `E:\regwatch-research\answer_key_kit\answers\` (from github.com/hozaifa1/regwatch-answer-key); `check_key.py`: 0 errors, 40 of 40. Audited 104, 671, 190, 2450 against the page images: every quote matches. Doubtful calls in 671 (an eligibility rule marked "must"; "stay within the limit" marked "must not").
- All 141 dev pages are read (`prepare_inputs.py --split dev` done).
- Keys: `.env` GEMINI_EXTRA_API_KEYS has 28 keys (+ the shell key = 29). See memory `regwatch-api-keys`. Accounts account B, account E and the DU account need the AI Studio terms accepted first (waiting on the user's own yes); never use account F.
- Scores (all 40 dev): baseline with round 1 12.84 / leak 18.5% -> kept state **21.04 / leak 17.8%**. Obligation F1 11.5% -> 33.2%; duties taken from enclosed copies 14 -> 0.
- App changes kept: who-check name variants and wider address block (`claims/wording.py`, `claims/checks.py`); new obligation field `deadline_text` (deadline in words) in the answer format, claims, checks, review screen, circular page ("Deadline: within 1 month ...") and scorer; prompt v4 in `analysis/prompts.py`.
- Not checked: the `deadline_text` line on the circular page in a real browser (no analysis in the app database has it yet; it appears after the next analysis run).
- Tests: full pytest 471 pass, 6 fail, 1 error (the old data/setup failures plus `test_authenticated_regulatory_qa`, a login/seed failure not touched here). `test_quote_ids_and_providers.py` now expects prompt "v4". `npx tsc --noEmit` passes. Tests rewrote `backend/app/tests/fixtures/genuine_corpus/test_genuine_brpd_circular.pdf`; restore it before committing.
- Scorer cache: its key includes the answer format, so adding `deadline_text` orphaned the old v3 answers (re-running v3 costs 40 calls).
- Page reader restarted with 29 keys; if it ever exits at once with "Another page reader is running", delete a stale `data/page_reader.lock` whose pid is gone.

## Earlier START HERE (written 14 Nov, before the loop)

**Paste this to start the next session:**

> Read the project notes, DECISIONS.md (10 was updated, 13 is new), research/09_SCORER_SPEC.md, research/scoring/README.md, and this section. The user has written the answer key for the 40 dev circulars outside this repo; copy their `answers/` folder into `E:\regwatch-research\answer_key_kit\answers\` and run `python E:\regwatch-research\answer_key_kit\check_key.py` (it must say 0 errors and 40 of 40). Audit 4 keys (10%) yourself against the page images; fix nothing silently, ask the user about real doubts. Then: (1) finish `prepare_inputs.py --split dev` if any Bangla or scanned pages still wait; (2) run the free baseline candidate and `score.py` on dev, and write the baseline numbers into this file; (3) start the overnight `/autoresearch` loop on the dev split only, with `score.py`'s `SCORE` as the metric and the leak rate as a guard that must not rise. One change per round, keep it only if SCORE rises. Order of work for the loop: first the free changes that re-score from cache in seconds (`run_candidate.py --rescore-only`): the duty check (it raised every false alarm in the 13 Nov review: polite "Please bring this to the notice of", Bangla "করবে", caps like "shall not exceed"), the who check (spelling variants such as তফসিলী/তফসিলি, residents, agent customers, offshore banking units), numbers like "15 (fifteen) percent", exemption wording ("will not, however, apply", "যোগ্য বিবেচিত হবে না"), Act names in the target check. Then prompt changes that need model calls (free tier): issue date given as effective date, added words ("formally", "strict"), rules taken from enclosed older circulars, "issued under section X of an Act" called a change link, a form's mention of the circular itself read as a link. Also re-run the two empty analyses (FID Circular No. 03, FCRPD Circular No. 6) in the app. (4) In the morning: report the best dev SCORE and what changed; list the paid candidates to try (main paid models incl. paid Gemini; prices from each vendor's own price page, OpenAI's first), run `price.py` for each and show the user the total (estimate was about $20-35) before any `--yes-spend`. (5) Only after the user writes the 90 test keys (same kit, test split): score the finalists once with `--final`. One helper at a time, never in parallel; A careful helper for design and judgement, a build helper for building. Every screen must update by itself and show no technical codes. Commit and push only when the user asks; scrub any mention of the assistant first.

**State after the 13-14 Nov session (nothing committed since 8daf4c4):**
- Claim-checks spec chunks 1-4 all built and tested. Full pytest: 472 pass, 5 fail, 1 error (the old known failures). Build and lint pass.
  - Chunk 3: "Points to check" review screen (admin tab), approve / fix / reject / ask for review, keys A F R J K ? Esc Ctrl+Enter, instant updates across tabs. A decision that clears review sends the "new circular" alert once (never for archive circulars). Fix keeps the fingerprint, so fixed points carry over to the next run.
  - Chunk 4: Bangla and scanned quotes get a second reading from a crop of their lines; DECISIONS.md 10 records the change. First live run: 31 of 35 sentences matched, 2 misread (one real digit error, ১৪৮৮ vs ১৪৪৮), 2 unclear (bad line boxes on FEPD-1 Circular Letter No. 20 page 1).
  - Not checked by eye: the "Fix the page reading" link opening the editor (the browser pane was hidden), and two admins in two real browsers (the user said it is not needed).
- Stand-in review (decision 13) of the 8 backfilled circulars: 6 approved, 33 fixed, 10 rejected, 7 held for page-reading errors. Log: `research/review_log_2026-11-13.md`. Backup before it: `data/regwatch.before-review.db`.
- On-screen "AI" wording replaced with "analysis" (admin tab "Analysis engine", messages "The analysis service ..."). The admin key-setup guide still names Google AI Studio, because the steps need it.
- Answer-key kit for the 40 dev circulars: `E:\regwatch-research\answer_key_kit.zip` (PDFs, `PROMPT.md`, `manifest.json`, English page text, `check_key.py`). Copies in `research/08_ANSWER_KEY_PROMPT.md` and `research/08_check_key.py`. The same kit can be rebuilt for the 90 test circulars later (script: the `make_kit.py` logic, with `split == "test"`).
- Scorer: spec `research/09_SCORER_SPEC.md`; code `research/scoring/` (README has every command). Built 14 Nov, no app code changed, 22 scorer tests pass. Dev inputs: 93 of 141 pages ready; 48 Bangla or scanned pages wait for the free page-reading quota (back about 14:05 Bangladesh time; `prepare_inputs.py --split dev --wait` finishes them, sharing quota with the page reader). The free baseline `gemini_flash_v3` already ran on the 16 ready circulars (cached); run it on the other 24 once their pages are ready. Paid batch submit is untested against a live service and only runs with `--yes-spend`; Gemini batch is upload-by-hand then `--collect`.
- Low-text pages: 17 image-read pages in 13 circulars have under 150 characters (for example SMESPD Circular No. 05/2026 page 1 holds only the letterhead). Suggested rule, not built: an image-read page under 150 characters that is page 1, or not an obvious divider page, goes back for reading once, then to a person.
- 16 points on BRPD Circular No. 15/2024 sit in "checking" with empty checks; not looked at yet.
- Background tasks keep running: `RegWatchArchiveDownload`, `RegWatchArchiveImport`, `RegWatchPageReader` (restarted 14 Nov on the chunk 4 code).

## Earlier START HERE (14 Nov early morning, done)

**Paste this to start the next session:**

> Read the project notes, DECISIONS.md (decision 13 is new), docs/specs/CLAIM_CHECKS_SPEC.md (sections 0, 5.2, 6.2, 7, 8 chunks 3-4), then this section. Chunks 1 and 2 of the claim-checks spec are built and tested (not committed). Next, one helper at a time, never in parallel: (1) a build helper builds chunk 3 (review screen, "Points to check"), including the chunk 1 notes in the spec (send the "new circular" alert when a decision clears review; keep the fingerprint on Fix). (2) Then ONE careful helper, as the stand-in reviewer (decision 13), works slowly and serially through the held points of the 8 backfilled circulars via the chunk 3 decision endpoints, writing a short reason per decision; check usage before starting. (3) Then a build helper builds chunk 4 (Bangla quoted-sentence second reading); afterwards record in DECISIONS.md that decision 10 is replaced. (4) Then plan step 4: answer key for the 40 tuning + 90 test circulars and a scoring harness; paid candidates run once each in batch mode (estimate about $20-35 total; check OpenAI's own price page first). A careful helper for design and judgement, a build helper for building. Every screen must update by itself and show no technical codes. Commit and push only when the user asks; scrub any mention of the assistant first.

**State after this session (13-14 Nov):**
- Pushed to GitHub main on 13 Nov (commit 8daf4c4). Everything after that is uncommitted: claims module, migration `c7e9a1b3d5f8` (applied to data/regwatch.db), checked customer view, backfill script, spec, DECISIONS.md 13.
- Backfill applied to 8 circulars. Most points are hidden for now because v2 analyses had no evidence for summaries; re-running analysis (v3 prompt) brings them back checked. Backups: `data/regwatch.before-claims.db`, `data/regwatch.before-backfill.db`.
- Tests: 425 pass, 5 fail, 1 error (the old known failures). `test_claim_checks.py` 40, `test_claims_view.py` 12, all pass. Build and lint pass.
- Known gaps: the "still being checked, about N minutes" line shows but nothing works that queue until chunk 4 (those points stay hidden, safe). Some admin messages still say "The AI service ..." (`analysis/jobs.py`, `providers/factory.py`, `analysis/router.py`); reword to plain text.
- Overview artboard: `private/regwatch-artboard.html` (git-ignored, offline, 9 boards).
- Usage rule from the user: one helper at a time; the stand-in reviewer is one careful helper working serially and slowly.

**Running on this PC right now (started in a session, so they stop if the PC restarts):**
- Archive download: scheduled task `RegWatchArchiveDownload`, 2 s gap. Progress: `E:/regwatch-research/venv/Scripts/python.exe research/archive/fetch_all.py status`.
- Archive import loop: adds new downloads to the library every 10 min (`backend/scripts/import_archive.py --app-db`); last run imported 659 files, 0 failed.
- Page reader: `backend/scripts/read_pages.py` with 8 free keys, about 6 pages a minute, newest circulars first. Log `data/page_reader.log`; `--status` for counts.
- To make the reader and import survive a restart, the user runs once: `powershell -ExecutionPolicy Bypass -File backend/scripts/register_reader_tasks.ps1` (registering was blocked for me).

**Done in this session (all tested; full suite earlier 368 pass with the 5 old failures; `test_speed_fixes.py` now 16 pass):**
- Step 1 of the 07 plan: analysis refuses to run while any page waits to be read (`analysis/auto.py`; the button answers "N pages are still being read"). New circulars from the live checker (status PUBLISHED_MACHINE_PROCESSED) are analysed by themselves once all pages are read (hooked into the page reader and the web job). Archive circulars (status EXTRACTED) are never analysed automatically.
- New GET `/documents/{id}/reading-status` and a plain line on the circular page: "Reading the page images: x of y pages ready, about N minutes left", or "Waiting in line: N pages from newer circulars are read first", or "paused: today's free reading limit is used up; starts again at about HH:MM", plus what happens next (analysed by itself / added later for older circulars / an admin can run it). Archive circulars with no analysis say the summary comes later. Checked by API on a real archive circular; the browser check at 375 px is still to do.
- SQLite now waits up to 60 s for another process's write (WAL when possible), so the reader, import and app share the file safely.
- The design helper was stopped before writing anything (usage). `research/07_scratch/` holds the 07 research scripts.

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

Row 5 with more keys (done 13 Nov): `.env` now has `GEMINI_EXTRA_API_KEYS` with 7 extra free keys (8 in all, all tested OK; 3 new ones from the account C AI Studio projects AgenticDev, libre, Natively). `VISION_MAX_PARALLEL` is now 8. A 7-page scanned circular was read in about 20 s, all pages at once. Google refused a new project on that account (project limit), so more keys would need another Google account. `new-api.txt` in the repo root holds one of the keys and is now git-ignored.

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
5. Pick the analysis model (a careful helper writes the answer key from `E:\regwatch-research\gold\batches.json`, dev first, `validate_gold.py` to 0 errors; a build helper builds the harness and runs free models; test split scored once; verdict in `research/06_VERDICT.md` + DECISIONS.md).
6. Always-on startup tasks for backend + scheduler on this PC, enabled only after 19 Nov 18:00.
7. Update TickTick task "RegWatch build test" (project 6ae6f48a8f0847e165e47f9b) and Notion page 417366f4-5d6d-8173-b470-c09e9af7c267 (send base64 through COMPOSIO_REMOTE_WORKBENCH).
Then delete `.venv`, `frontend/node_modules`, `frontend/.next` before the user tests.

Known leftovers from this round: re-running analysis on a circular drops earlier link approvals; no metadata-edit endpoint, so relinking after an edit is manual (`POST /relationships/relink`); page image in the source panel looked blank in one screenshot (not investigated); `/workspace` picker and modals not checked at 375 px; board report print preview not opened.

## Build queue (13 Nov, paused for usage limit; nothing committed)
- Done, uncommitted: sign-up in the account modal; admin "Edit text" page correction in PagePanel (tests in `backend/app/tests/test_signup_and_page_edit.py`; 219 pass, the 7 old failures remain).
- Stopped half-way: search screen `/search` (full-text search + ask across circulars + store page-correction reason/who/when). Review the working tree before continuing; it may hold partial edits.
- Still to do, in order, one helper at a time: relationship map + old-vs-new compare (build helper, spec by lead); bank compliance screens and alerts (careful helper designs, build helper builds; alerts = in-app inbox + email when SMTP is set); analysis model pick (a careful helper writes the answer key from `E:\regwatch-research`, which still exists; a build helper runs harness and models); always-on setup on this PC, enabled only after 19 Nov 18:00; then update the TickTick/Notion "RegWatch build test" steps.
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
Plain, short explanations. Never mention AI tools in files, commits or docs. Commit as `hozaifa-rrh <account D>` with plain messages. Never call bb.org.bd faster than one request per 15 s. Never commit API keys or `research/*/data/`.

---
# Handoff: RegWatch architecture benchmark (as of 2026-11-11)

Read in this order: [DECISIONS.md](DECISIONS.md), then [research/06_VERDICT.md](research/06_VERDICT.md), then [research/05_TEST_PLAN.md](research/05_TEST_PLAN.md).
The user wants one tested verdict per app step, scored on a locked test split of real circulars. No caveats left for them to resolve.

## User rules that apply to this work
- Talk ELI5 and briefly. Lead with the verdict.
- **One helper at a time.** The user's Pro limit was hit twice by parallel helpers. On a Max account, still run one at a time unless the user says otherwise.
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
  - shell env GEMINI_API_KEY (account account C);
  - GOOGLE_API_KEY_FALLBACK in `F:\Projects\titan-title-review\.env`;
  - two in `E:\regwatch-research\gemini_keys.env` (accounts G and D).
- **Free Gemini limits:**
  - 3.5 Flash: about 17 requests per key per day;
  - 3.5 Flash-Lite: much higher;
  - 3.8 Flash: returns 503 "high demand" almost always;
  - Pro models: no free quota.
- **Other free keys in the titan `.env`:** SambaNova (GLM-5.3, gpt-oss-120b, Llama 3.3 70B, MiniMax, gemma-4-31B) and OpenRouter (about $0.44 credit plus 1000 free-model requests a day).

## Next steps, in order
1. **Write the analysis answer key.**
   - **How:** one helper per batch from `gold\batches.json`, dev batches first. Each follows `GOLD_SPEC_ANALYSIS.md` and must run `validate_gold.py` until 0 errors.
   - **Model:** on Max, the strongest model is the better choice for this key. The Pro plan forced a switch to a lighter one.
   - **Cost to expect:** the 26-page transcription job used about 40% of a Pro 5-hour window. The analysis key is about 366 pages.
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
- **bb.org.bd:** use User-Agent `NoticeIndexBot/0.1`, about 15 s between requests. A "Request Rejected" page for one URL means skip that file (2 sample files are like this). It isn't a block.
- **Windows Python:** always open files with `encoding="utf-8"`. Heredocs eat backslashes, so use forward slashes in paths inside Python.
- **Some pages are misclassified.** For example `1191_0_p10` is marked English but is Bangla. Route by font check, not by class label alone.
- **Free OpenRouter "reasoning" vision models** run out of output tokens on dense pages.
- **The old `docs/DECISION_LOG.md` has a pending local edit (not committed).** DECISIONS.md overrides it.
- **Nothing in `research/`, DECISIONS.md, HANDOFF.md is committed yet.**

