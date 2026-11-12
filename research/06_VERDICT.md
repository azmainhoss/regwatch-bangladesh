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

## Step 1: spotting new circulars. Live test runs until 18 Nov 2026
- After day 1: 3 of 3 new circulars caught, median 7 min after upload, 0 missed in the nightly full-list check,
  and 2 network errors that recovered on the next check.

## Step 3: analysis. Not decided yet
- The answer key for the 40 tuning circulars is next. Then tuning with autoresearch on those 40, then one scored run on the 90 test circulars.
