# Archive download report (13 Nov 2026, written 18:30 BDT while the download is still running)

## Speed test (full log: `SPEED_TEST.md`)
| Gap between requests | Files | Challenge pages | Rejected (single URL) | Avg server time per file |
|---|---|---|---|---|
| 5 s | 100 | 0 | 1 | 1.04 s |
| 3 s | 100 | 0 | 1 | 0.77 s |
| 2 s | 100 | 0 | 1 | 0.82 s |

- Own name `RegWatchBot/0.1`, one request at a time, no proxies, no fake browser.
- Parallel requests were not tried: the download is serial by design, so it would only add risk for no gain.
- **Chosen rate: 3 s** (last clean rate 2 s, plus one step of margin). The rate lives in `data/gap.txt` and is re-read before every file; it can never go below 2 s.

## Index
5,191 PDFs in 4,810 circulars (1,226 English, 3,965 Bangla), dated 20 Jul 2000 to 12 Nov 2026. Built once with one 2.6 MB list request.

## Progress so far (18:27 BDT)
- 400 files saved (272 MB), 3 rejected (skip), 1 retried after a URL with a space was fixed, 4,787 to go.
- Pace: about 4.2 s per file (3 s gap plus about 1 s download). Estimated finish: **about 00:30-01:00 BDT on 14 Nov** (roughly 5.6 hours), with total size near 3.5 GB (50 GB free on drive F).
- Check any time: `E:\regwatch-research\venv\Scripts\python.exe research\archive\fetch_all.py status`.

## Scheduled task
`RegWatchArchiveDownload` (on this PC): starts at logon and every 15 min, never runs twice at once, restarts after a crash, exits by itself when finished (`data/DONE`) or after 3 blocks in one day (`data/STOPPED`; delete the file to resume). Back-off on a block: 30 min, doubling up to 6 h. `RegWatchDetectPoll` and `RegWatchDetectReconcile` were not touched; the poll kept running normally during the speed test.
- Sharing with the poll: the poll scripts on this PC (`E:\regwatch-research\detect\poll.py`) have no shared request lock, only their own `poll.lock`. The download waits whenever that file is fresh and stays quiet 02:00-02:06 (nightly check). Gaps in the poll lock window of a few seconds are possible but each poll is one request.
- To stop it for good: `Disable-ScheduledTask RegWatchArchiveDownload`, then end the `pythonw` process running `fetch_all.py`.

## Loading into the app
Script: `backend/scripts/import_archive.py` (new file; no existing backend file changed).
- Default: loads a throw-away database and storage in `research/archive/data/import_test/`. It never touches the developer database unless you pass `--app-db`.
- It calls the existing `document_ingestion_service.ingest_document` with the local file and index details (reference, title, date, department, language, ETag, Last-Modified). English and Bangla files of one circular become variants of one document. No analysis, no alerts, no model calls (the key is blanked inside the script).
- Reference numbers get the year added (for example `BRPD Circular No. 05/2023`) because departments restart numbering every year and the ingest code treats one reference number as one document.
- Missing departments are created with the department code as the name.
- Safe to stop and re-run; `--limit N` caps one run; `--summary` and `--spot-check N` check the result.

**Test on the files downloaded so far (301 files):** 300 imported, 1 duplicate (same file under a second URL), 0 failed. 296 circulars in the test database = 296 distinct circulars in the index for those files. 2,060 pages, 856 waiting for vision reading (Bangla and legacy-font pages). Spot-check of 10 random circulars (twice, 20 in all): title and date matched the index every time; English pages show real page text, Bangla pages are queued with empty text, as designed. Import speed is about 45 files a minute, so the full import takes about 2 hours.

## When the download is done
1. Confirm `fetch_all.py status` shows no `pending` and `DONE` exists in `research/archive/data/`.
2. Stop the backend while importing (SQLite allows one writer).
3. From the repo root: `.venv\Scripts\python.exe backend\scripts\import_archive.py --app-db` (database must already be created/migrated and seeded; the script adds the Bangladesh Bank institution if it is missing).
4. `.venv\Scripts\python.exe backend\scripts\import_archive.py --app-db --summary`: circulars in the app should equal the circulars in the index minus the circulars whose only files were rejected or failed.

## What is left
- Finish the download (about 5.6 h) and the import (about 2 h).
- Bangla, legacy-font and scanned pages (about 40% of pages) wait as PENDING_VISION; reading them needs the vision worker and a Gemini key (not run here).
- Analysis of the archive is not run (model not chosen).
- Imported documents get status EXTRACTED, not PUBLISHED_MACHINE_PROCESSED, because no analysis has run. If the library screens only show published documents, either show EXTRACTED too or set the status after import. This is a product choice, not a code change in this task.
- Failed files (if any) are retried 3 times automatically; rejected files are skipped for good. Final totals (pages, size, rejected, failed, English vs Bangla) get added here when the download ends.
