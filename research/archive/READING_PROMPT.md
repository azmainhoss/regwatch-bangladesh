# Reading prompt for the Bangla archive

Paste the prompt below into the Gemini app together with one PDF. Copy the whole answer into a
`.txt` file with the same name as the PDF (`2026-01-04_jan042026brpd-101.pdf` becomes
`2026-01-04_jan042026brpd-101.txt`), saved as UTF-8. Put all the `.txt` files in one folder, then run:

```
.venv\Scripts\python.exe -m backend.scripts.import_manual_reading <folder> --dry-run
.venv\Scripts\python.exe -m backend.scripts.import_manual_reading <folder>
.venv\Scripts\python.exe -m backend.scripts.import_manual_reading --sample 10
```

The dry run lists what would be imported and any file whose page count doesn't match its PDF.
`--sample 10` prints 10 random imported pages with their PDF and page number, to check by eye.

## Prompt

```
Transcribe every page of the attached PDF exactly as printed.

Rules:
- Before each page write a line: === PAGE n === (n is the page number, 1, 2, 3 ...). Include every page, even a blank one.
- Copy the text exactly, in its original language and script. Do not translate, summarise, correct or explain anything.
- Keep every number, date, amount, percentage and reference code exactly as printed, including Bangla digits.
- Write each table row on one line, with " | " between cells.
- Write [illegible] for any part you cannot read.
- Plain text only: no markdown, no headings, no bold, no code blocks, and nothing before the first page marker or after the last page.
```

## What the answer should look like

```
=== PAGE 1 ===
বাংলাদেশ ব্যাংক
প্রধান কার্যালয়
...
ক্রমিক | বিবরণ | হার
১ | ... | ২.৫%
=== PAGE 2 ===
...
```
