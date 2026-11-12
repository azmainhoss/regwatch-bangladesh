# Research 2: reading Bangladesh Bank PDFs (2026-11-10)

Hands-on: 23 real circular PDFs were downloaded and measured (44 pages), and the OCR tools and Bijoy converters were tested on them.
Scripts and outputs are in the session scratchpad (pdf_research/).
M = measured, R = read.

## The big finding (M)
OCR isn't the main problem. The main problem is Bangla text that sits inside the PDF in a legacy font.
- **English PDFs:** 100% clean text, never scanned.
- **Bangla PDFs (13 sampled):** none had clean Unicode text.
  - 54% SutonnyMJ/Bijoy font. This includes 4 of the 6 recent (2025-2026) ones.
  - 23% "NokshiStandard", another legacy font (2005-2009). bijoy2unicode can't read it.
  - 15% scanned images.
  - 8% broken Unicode: it looks like Bangla but the letters are wrong.
- **The archive is 75% Bangla-only**, 17% English-only and 8% both.
  - Real OCR need: about 11-12% of documents (scans only).
  - About 30-35% if Nokshi and broken-Unicode pages also go to OCR.
- **Backlog OCR volume:** about 4-5k pages. New circulars add about 1 OCR page per day.

## Tools tested (M)
| Tool | RAM | Speed (CPU) | Notes |
|---|---|---|---|
| Tesseract 5.5 ben+eng (tessdata_best) | 88-123 MB | 8-24 s/page, dense pages up to 50 s | Very good on clean scans. Misreads ৪ as 8 and flattens tables. |
| Tesseract tessdata_fast | 75-80 MB | 3-5.5 s/page | 94-96% the same as best, but more visible errors. |
| EasyOCR bn+en | 1-4 GB | about 160 s/page | Same quality as Tesseract, far heavier. Ruled out. |
| PyMuPDF 1.28 (pinned below 2) | 58 MB for 74 pages | 0.11 s/page | Best fit for reading text layers. |
| PyMuPDF 2.x / pymupdf4llm | 240-340 MB | 0.4-1.2 s/page | Now pulls in a layout model. Breaks Bijoy tables apart. |
| unicodeconverter (Bijoy, 2022) | tiny | 11-13 ms/page | 89-95% match. Some letter order is wrong; needs a small fix-up rule set. |
| bijoy2unicode (2018) | tiny | fast | 89-93% match, similar errors. |

Neither Bijoy converter is maintained.

## Tools read about, not tested (R)
- **PaddleOCR PP-OCRv5:** Bengali not officially listed.
- **Docling, Marker/Surya, MinerU:** heavy (GB-class RAM) with weak or no Bangla support.
- **olmOCR, dots.ocr, DeepSeek-OCR, Qwen3-VL:** need a GPU in practice; weak or unproven on Bangla.
- **bbOCR / apsisOCR (Bengali.AI):** made for Bangla, about 1 GB+, from 2023. Worth one test.
- **Paid options:**
  - Google Document AI OCR: $1.50 per 1,000 pages, Bengali listed.
  - Mistral OCR 3: $2 per 1,000 pages ($1 with batch).
  - Gemini 2.5 Flash-Lite: about $0.10 per million tokens in and $0.40 out. Roughly $0.5-1 per 1,000 pages (estimate).

## Recommended pipeline (subagent's view)
1. **Sort each page** by font name, Bangla letter share, invalid letters and image coverage.
2. **English / clean Unicode:** PyMuPDF text, a clause parser (1., 1.1, 2(a), (ক), ২।) and table detection.
3. **Bijoy pages:** convert span by span using a tested mapping table, then run a quality check.
   Pages that fail go to OCR.
4. **Scanned, Nokshi and broken pages:** a separate OCR worker running Tesseract, about 120 MB per worker.
   Afterwards, fix digits (8 back to ৪). It shouldn't run on the web server.
5. **Backlog:** a one-off batch of 4-6 hours on any 2-4 core machine, or about $5-10 through Google Document AI or Mistral.
6. **Ongoing:** about 1 OCR page a day. Use a paid API as the fallback for low-confidence pages. Well under $1 a month.

## Caveat (main session note)
This brief assumed the old 512 MB free-tier server, which is no longer a given.
There's one option it didn't fully weigh: send every Bangla page (Bijoy, Nokshi, scanned, broken) to a vision model or OCR API,
and skip the fragile Bijoy conversion entirely. At about 1 page a day plus a one-off backlog of a few thousand pages,
that costs a few dollars in total. It trades a hand-maintained converter for a paid dependency.
