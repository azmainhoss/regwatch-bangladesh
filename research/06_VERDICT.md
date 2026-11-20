# Verdict (filled in step by step; numbers come from the locked test split)

## Step 2: reading PDFs. DECIDED 2026-11-11

**Winner:**
- English pages with a clean text layer: PyMuPDF.
- Every Bangla or scanned page: Gemini 3.5 Flash-Lite reading the page image.
- On the free tier, Gemini 3.5 Flash is the second opinion.

**Dropped:** the Bijoy converters, Tesseract, Gemma 4, Gemini 3.8 Flash and the free OpenRouter vision models.

### Test numbers (53 test pages, scored against hand-checked transcriptions)
CER is the share of characters wrong. A missing output counts as 100% wrong. "Numbers exact" is the share of numbers, dates and references copied exactly.

| Method | All pages, CER | Bijoy pages (14) | Old Nokshi font (11) | Scanned (10) | Numbers exact | Pages it failed |
|---|---|---|---|---|---|---|
| **Gemini 3.5 Flash-Lite (vision)** | **6.1%** (4.3% on pages done) | 4.7% | 7.3% | 4.8% | 94% | 1 of 53 |
| Gemini 3.5 Flash (vision) | 12.9% (3.8% on pages done) | 3.7% | 6.7% | 4.0% | 97% | 5 of 53 (free quota ran out) |
| Tesseract best (OCR) | 10.5% | 16.8% | 8.3% | 7.1% | 87% | 0 |
| Bijoy converter (unicodeconverter) | 46.6% | **22.7%** | 79% | 100% | 58% | 0 |
| PyMuPDF text layer | 62.5% | 83% | 79% | 100% | 33% | 0 |
| Gemma 4 31B / Gemini 3.8 Flash / free OpenRouter | mostly not finished | | | | | free tier too slow, overloaded or rate-limited |

### Why
- **The Bijoy converter looked fine on the 27 tuning pages (2.9%) but fell apart on the test pages (22.7%).**
  It can't be trusted, so it's dropped. This is exactly the kind of result the held-out test exists to catch.
- **Gemini reading the page image beats OCR on every Bangla type:** scanned, Bijoy and Nokshi alike.
- **For English, PyMuPDF is under 1% CER on normal pages.** It only goes wrong when a page marked English is really Bangla or has an odd layout.
  Rule: if a page's text layer has Bijoy/legacy fonts or broken Bangla, send it to Gemini instead.

### Built-in quality check (tested)
- Read each Bangla page with both Flash-Lite and Flash.
- **When the two agree within 2%** (19 of 60 Bangla pages), the real error is about 1.5%, so the page goes through automatically.
- **When they disagree**, the error is 7-9%. The page is flagged for a person to check before any quote from it is published.
  That matches the golden rule: nothing unverified gets published.

### Cost
- Free tier: Flash-Lite averages 12 s a page. New circulars need about 1-5 pages a day, which is well inside the free limits.
- The one-time backlog (several thousand Bangla pages) needs about 2-3 weeks on free keys, or a few dollars on a paid key.

## Step 1: spotting new circulars. DECIDED 2026-11-20

**Winner:** our own script asking the circular page's 7-day date filter every 10 min on working days (09:00-19:00) and hourly otherwise, plus one full-list check every night. Name `DocFetchBot/1.0`, one request at a time.

### Live test numbers (always-on PC, 10 Nov 22:08 to 19 Nov 18:00)
| Measure | Result |
|---|---|
| New circulars caught | **10 of 10** |
| Time from upload to caught | median 5.8 min, worst 7.5 min |
| Missed, by the nightly full-list check | **0** in 9 checks (1 more check failed on a dropped connection) |
| Checks made | 388 |
| Checks that failed | 17 (4%): 10 dropped connections, 7 DNS failures. Every one worked on the next try |
| Challenge pages (bot check) | **0** |
| Data used | 0.1 to 10 MB a day |

The 10 circulars: FEPD-1 Circular 42, FCRPD Circular Letter 20, FEPD-1 Circular Letter 21 (11 Nov); FCRPD Circular 6, FID Circular 03, FEPD-2 Circular 12 (12 Nov); FEPD-1 Circular 43, FEPD-1 Circular Letter 22, SDAD Circular Letter 21 (16 Nov); ACD-1 Circular Letter 05 (19 Nov). All were uploaded on working days between 11:20 and 16:30.

### What the test settled
- **The method works.** Every new circular was caught within 8 minutes, and nothing slipped past.
- **Keep the nightly full-list check.** It cost about 2.6 MB a night and is the only proof that nothing was missed.
- **A single failed check is not a problem.** The next check always fixed it. Only checks failing for more than an hour should alert the admin.
- **Keep the checker apart from bulk downloads.** On the other PC on 12 Nov, sharing one request queue with the archive download caused 16 timeouts in 25 checks. Run separately, there were none.
- **The home laptop can't be the launch machine.** It was off or asleep for two full working days (15 and 17 Nov) and part of a third (18 Nov afternoon). Nothing was published in those hours, so nothing was lost this time. At launch the checker needs a machine that stays on.

Data: `E:\regwatch-research\detect\` (`runs.jsonl`, `reconcile.jsonl`, `seen.json`, `pdfs\`). Re-run the numbers with `E:\regwatch-research\venv\Scripts\python.exe E:\regwatch-research\detect\summary.py`.

## Step 3: analysis. Not decided yet
- The answer key for the 40 tuning circulars is next. Then tuning with autoresearch on those 40, then one scored run on the 90 test circulars.
