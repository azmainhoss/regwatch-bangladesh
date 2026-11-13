# Handoff: download the full Bangladesh Bank circular archive (13 Nov 2026)

Paste everything below into a fresh session on THIS PC (the always-on one: it has `E:\regwatch-research` and runs the detection tasks).

---

Goal: have every past Bangladesh Bank circular (English and Bangla, all departments, all years) downloaded, archived and loaded into the RegWatch app, so the app can launch with a complete library. Work autonomously; report back only when done or blocked.

Read first: `DECISIONS.md`, `HANDOFF.md` (top section), `research/archive/fetch_archive.py`, `research/detect/detect_test.py`, `research/03_DEEP_RESEARCH_SCRAPING.md`, `research/04_LOCAL_MODEL_TEST.md` (block findings).

## New rules from the user (13 Nov), they override older notes
- This PC may run 24/7. Drop the 10:00-18:00 window for downloads (keep it nowhere unless a test shows night requests get blocked). Update DECISIONS.md and HANDOFF.md to say so.
- The 15 s spacing was the safe rate proved on day 1, not a tested limit. Find the real limit with a careful speed test (below), then download at the fastest clean rate.

## What is known
- Listing: `POST https://www.bb.org.bd/en/index.php/mediaroom/circular` with a date filter (see DECISIONS.md 1). The full list is about 2.6 MB.
- Use User-Agent `RegWatchBot/0.1`. Never fake a browser.
- Blocked: fake Chrome name, 3 s apart, after about 20 files. Fine: own name 10 s apart (7 files), own name 15-20 s apart (126 files). Never tested faster with our own name, never tested parallel.
- A block looks like an HTTP 200 HTML challenge page ("What code is in the image", /TSPD/, 40-50 KB) instead of a PDF. A "Request Rejected" page for one URL means skip that file, not a block.
- The detection task `RegWatchDetectPoll` runs on this PC every 10 min and must keep working until 19 Nov 18:00. Downloads must share its request lock (one request at a time across both) so they never overlap.
- An earlier run on another PC downloaded 1,021 of 3,591 Bangla-only PDFs into `research/archive/data/` there. That folder is NOT on this PC. Start fresh here; ask the user to copy it over only if the speed test shows we must stay slow.

## Step 1: speed test (about 30-60 min)
1. Build the full index once (all circulars, English and Bangla, with every PDF URL per circular). Save to `research/archive/data/index.json`.
2. Download in stages with our own name, one request at a time, stopping at the FIRST challenge page:
   - 100 files at 5 s apart;
   - then 100 at 3 s;
   - then 100 at 2 s.
   Do not try parallel requests unless 2 s is fully clean; if it is, try 2 at once for 50 files.
3. On a challenge page: stop at once, wait 30 min, then check one listing request. If it works, use the last clean rate plus a margin (e.g. clean at 3 s → run at 5 s). Log every stage (rate, files, blocks, average file time) to `research/archive/SPEED_TEST.md`.
4. Never go below 2 s spacing. Never use proxies, fake browsers or unblocker services.

## Step 2: full download
- Extend `fetch_archive.py` (or a new `fetch_all.py`) to cover ALL circulars, not just Bangla-only: every PDF URL per circular (English and Bangla variants), resumable, skipping files already saved (by URL and SHA-256).
- Run at the rate from step 1, 24/7, as a Windows scheduled task that restarts if it stops (`RegWatchArchiveDownload` on this PC). Keep the shared lock with the detection task.
- Back off on any challenge page: 30 min, rising to 6 h; after 3 blocks in a day, stop and report.
- Save state after every file. Record per file: URL, circular reference, date, department, language, SHA-256, ETag, Last-Modified, size, status (ok / rejected / failed).

## Step 3: load into the app
- Load every downloaded PDF into the app's shared library through the same pipeline as uploads (archive with SHA-256, versions, duplicates detected), using the existing backfill/ingest code in `backend/app/modules/sources/service.py` with a local-file source, not fresh downloads. Metadata (reference number, title, date, department) comes from the index.
- English pages are read at once (PyMuPDF). Bangla, legacy-font and scanned pages are queued as PENDING_VISION. Do NOT run AI analysis on the whole archive yet: the analysis model is not chosen (HANDOFF step 5). Just store and read.
- Check: number of circulars in the app = number in the index minus rejected files; spot-check 10 random circulars open with the right title, date and page text.

## Step 4: report
Write `research/archive/ARCHIVE_REPORT.md`:
- speed test results and the chosen rate;
- totals: circulars, PDFs, English vs Bangla, rejected, failed, total size, pages, pages waiting for vision reading;
- how long the full download took.
Update DECISIONS.md (rate, 24/7) and HANDOFF.md. Tell the user in plain, short words what is done and what is left (the Bangla page reading and analysis).

## Rules (mandatory)
- Never mention AI, an agent or how code was written in files, commits, comments or docs. Never commit local assistant settings, keys, or `research/*/data/`.
- Don't commit or push unless the user asks. Commit as `hozaifa-rrh <hozaifahossain@rrh.com.bd>` with plain messages.
- Never stop or change `RegWatchDetectPoll` / `RegWatchDetectReconcile` before 19 Nov 18:00.
- Windows Python: open files with `encoding="utf-8"`; use forward slashes in paths inside Python.
- Never print API keys.
- Heavy legwork can go to one Sonnet subagent at a time (never parallel agents); judgement calls (the chosen rate, what counts as a block) stay with the lead.
