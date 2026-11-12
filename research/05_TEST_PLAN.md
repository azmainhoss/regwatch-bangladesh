# Research 5: the full benchmark plan (started 2026-11-10)

Goal: one tested verdict for each step of the app. Every number in the final verdict comes from the held-out test split.
Work folder for data and scripts: `E:\regwatch-research\`.

## Ground rules
- **Sample:** 130 real circulars picked at random (seed 20261110): 100 from the whole archive and 30 from 2025-2026.
- **Split:** dev (40 rows) is the only data allowed for tuning prompts, rules or fix-ups.
  Test (90 rows) is run once per finalist, at the end. A result measured on the data it was tuned on is never reported.
- **Gold answers:** written by Opus agents from the page images plus text. Every gold quote is checked by code
  (exact match after NFC and whitespace normalization). I audit 10% of gold docs myself.
- **Scoring is mechanical wherever possible.** A predicted obligation matches a gold one by quote overlap on the same page
  (at least 50% character overlap). Type, deadline and applies-to are compared field by field.
  Only summaries need a judge: two different judges, both reported.
- **Bot rules for bb.org.bd:** honest User-Agent, one request at a time, at least 15 s apart, stop on any challenge, never bypass.

## Step 1: spotting new circulars
- Run the planned poller (date-filter POST every 10 min in office hours, hourly otherwise) for at least 5 working days.
- Compare it against the nightly full list (the only backup kept; changedetection.io, the ticker and news watchers were dropped on 2026-11-10 as unneeded).
- Measure: missed circulars, minutes from upload (PDF Last-Modified) to detection, challenges or blocks, false "nothing new" replies.

## Step 2: reading PDFs (80-page subset: 60 Bangla, 20 English)
- **Gold:** a checked Unicode transcription of each page.
- **Methods:**
  - PyMuPDF text;
  - Bijoy converters (raw and with fix-ups tuned on dev pages only);
  - Tesseract (best and fast);
  - Gemini 3.5 Flash-Lite, 3.5 Flash and 3.8 Flash reading page images;
  - Gemma 4 31B (vision);
  - paid OCR if a key is available.
- **Measure:**
  - character error rate;
  - key numbers exactly right (amounts, %, dates, circular references);
  - clause numbering kept;
  - tables kept;
  - time, RAM and cost per page.

## Step 3: analysis (metadata, obligations, applies-to, deadlines, relationships, English summary)
- **Candidates:**
  - rules only;
  - local models (NuExtract3, qwen3:4b and others);
  - Gemini 3.5 Flash-Lite, 3.5 Flash and 3.8 Flash;
  - Gemma 4 31B;
  - open models on SambaNova;
  - free models on OpenRouter.
- **Paid models skipped (user's choice, 2026-11-10):** only free tiers and local models are tested.
- **Ways of asking:** whole document; span pointer (the model returns sentence IDs, code copies the text); hybrid (rules find candidates, the model labels them).
- **Tuning:** the autoresearch loop tunes prompts for the top candidates on dev only, then one final run on test.
- **Measure:**
  - recall and precision per field;
  - share of quotes that are word for word on the right page;
  - share of docs that pass the publish gate;
  - time and cost per document;
  - also an end-to-end run (best reader plus best analyzer) on test.

## Final output
`research/06_VERDICT.md`: one winner per step, with its test-split numbers, its cost, and the runner-up.
