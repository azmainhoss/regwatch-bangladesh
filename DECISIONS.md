# RegWatch: decisions (read this first)

This is the single source of truth for architecture decisions. Last updated 2026-11-10.
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
- **Being confirmed by a 5-working-day live test that ends 18 Nov 2026** (see "Running tests" below).

### 2. How the script talks to the site
- **It uses its own name, `RegWatchBot/0.1`, not a fake Chrome identity.**
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
- No paid Claude or GPT for now. They can be tested later if free falls short.
- Keys: GEMINI_API_KEY in the shell environment, plus `F:\Projects\titan-title-review\.env`.
  The project's own `env` file has empty key lines.

### 9. Competitor
- RegAlert (regalert.today) already covers Bangladesh Bank circulars. It's the benchmark we'll be compared against.

---

### 10. Reading Bangla and scanned pages (decided 2026-11-11, test split)
- **Send every Bangla or scanned page to Gemini 3.5 Flash-Lite as an image.** It scored 4-7% CER on the test pages, and 94% of numbers came out exact.
- **Also read each one with Gemini 3.5 Flash.** If the two readings agree within 2%, the page passes. Otherwise a person checks it.
- **Dropped:**
  - the Bijoy converters (22.7% CER on test pages, after 2.9% on tuning pages);
  - Tesseract;
  - Gemma 4, Gemini 3.8 Flash and the free OpenRouter models (too slow or unavailable on free tiers).
- **English pages:** keep PyMuPDF (decision 6). Pages with Bijoy, legacy or broken-Bangla fonts go to Gemini.
- Details: `research/06_VERDICT.md`.

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
- **Gold answers:** the page transcriptions were written by Opus. The analysis answers are written by Sonnet,
  one agent at a time, to stay inside the user's Claude usage limit. Every quote is checked by code, and I audit 10% by hand.
- **Scoring is by code wherever possible.** A number measured on data it was tuned on is never reported.
- **Tuning uses the autoresearch skill (user's instruction).** It runs overnight loops of "change one thing, score, keep or discard",
  on the dev split only. It tunes:
  - the Bijoy converter fix-ups;
  - the prompts and method (whole document, span pointer, hybrid) for the top free analysis models;
  - how pages are routed between the converter, OCR and vision.
  It starts once the gold answers exist, because it needs a score to chase. The finalists then run once on test.
- **Final answers:** one verdict per step, with test numbers. No caveats left for the user to resolve.

## Running tests
- **Detection test:** scheduled tasks `RegWatchDetectPoll` (every 10 min) and `RegWatchDetectReconcile` (02:00 daily).
  - Both end 2026-11-18 06:00.
  - Results: run `E:\regwatch-research\detect\summary.py`.
  - To remove early: `E:\regwatch-research\detect\REMOVE_TASKS.md`.
  - The PC must stay on and logged in.
- **Reading test:** outputs in `E:\regwatch-research\reading\`.

## Research files
- `research/01-04`: the 2026-11-10 findings.
- `research/05_TEST_PLAN.md`: the benchmark plan.
- `research/06_VERDICT.md`: the final verdict (not written yet).
