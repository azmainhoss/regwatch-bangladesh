# Answer key for 40 Bangladesh Bank circulars

Paste everything below the line into a fresh session with the strongest model you have, at its highest reasoning setting.
Give it this whole folder (upload the zip, or open the folder in a coding tool). In a chat with no file access, upload
`PROMPT.md`, `manifest.json` and a few circulars' PDFs at a time, then save each JSON it returns as `answers/<row>.json`.

---

You are writing the answer key for a test of software that reads Bangladesh Bank circulars. The software's output on
these same 40 circulars will be scored against your answers, field by field, so your answers must be **exactly right and
complete**. Accuracy matters far more than speed. When the page and your memory disagree, the page wins.

## What is in this folder
- `manifest.json`: one entry per circular (`row`). It lists its PDF file(s) and every page as `page_id` (for example
  `2450_0_p1` = file `2450_0.pdf`, page 1), the page `kind`, and `in_obligation_window`.
  `listing_title` and `listing_date` come from the website listing and only help you find the file; take every answer from the document itself.
- `pdfs/`: the original PDFs. **The page image is the truth.** Render pages at 200-300 dpi and read them closely,
  zooming into strips for small print, tables and Bangla.
- `english_text/<page_id>.txt`: the text layer of English pages. For these pages, copy quotes from this file
  (it is what the software sees), never retype them.
- `check_key.py`: checks your files (standard-library Python). `answers/`: where your files go.

Page kinds: `english_text` (clean English text layer); `bangla_or_legacy_font` (Bangla, often in old Bijoy/SutonnyMJ
fonts whose text layer is garbage: read the image); `scanned` (an image only: read the image).

## How to work
1. Work on **one circular at a time**, in `manifest.json` order. Skip any row that already has `answers/<row>.json`
   that passes the checker (so the work can be resumed in a new session).
2. For each circular: read every page fully first, then write the JSON, then run `python check_key.py <row>` and fix every ERROR.
   For each WARN (Bangla or scanned quote), compare your quote letter by letter with the image once more.
3. A row may have two files (an English and a Bangla version of the same circular). Treat it as one circular.
   Take quotes from the English version when the same clause is in both.
4. At the end, run `python check_key.py` on everything and report: per row, the number of obligations and relationships,
   the rows you found hard, and anything listed in `uncertain`.

## Output: `answers/<row>.json` (UTF-8, Bangla as Unicode)
```json
{
  "row": 2450,
  "metadata": {
    "doc_type": "circular_letter",
    "department": "BRPD",
    "reference_number": "BRPD Circular Letter No. 20",
    "issue_date": "2018-10-09",
    "issue_date_quote": "October 09, 2018",
    "issue_date_page_id": "2450_0_p1"
  },
  "effective": {"basis": "immediate", "date": null, "quote": "This will take effect immediately.", "page_id": "2450_0_p2"},
  "applies_to": [{"entity": "all_scheduled_banks", "quote": "...", "page_id": "2450_0_p1"}],
  "exempt": [],
  "obligations": [
    {"id": "o1", "page_id": "2450_0_p1", "quote": "...", "type": "report", "subject": "all_scheduled_banks",
     "what": "Submit the quarterly statement of ... to BRPD",
     "deadline": "within 15 days after each quarter end", "deadline_quote": "...", "deadline_page_id": null}
  ],
  "relationships": [
    {"type": "amends", "target_reference": "BRPD Circular No. 14", "target_date": "2012-09-23", "quote": "...", "page_id": "..."}
  ],
  "key_changes": [{"text": "The limit rises from 10% to 15% of capital.", "quote": "...", "page_id": "..."}],
  "summary_points": [{"text": "...", "quote": "...", "page_id": "..."}],
  "summary_en": "...",
  "enclosures": [{"what": "copy of FEPD Circular No. 41 dated 2021-05-03", "page_ids": ["..."]}],
  "page_notes": [{"page_id": "...", "content": "letterhead_only", "note": "..."}],
  "uncertain": ["anything you were not sure of, and why"]
}
```

## Rules for every quote
- A quote is the **exact words** of one sentence or clause on **one** page. Never span two pages; never join pieces.
- English pages: an exact substring of `english_text/<page_id>.txt` after collapsing whitespace. Copy it from the file.
- Bangla and scanned pages: Unicode exactly as printed, including Bangla digits (০-৯), spelling as printed
  (do not correct "তফসিলী" to "তফসিলি" or the reverse), and punctuation such as "।". Check numbers, years
  (Gregorian, Bangla calendar and Hijri), memo numbers and negations (না, নয়, নহে, নি) twice. These are where readings go wrong.
- Every field that states a fact must have a quote that actually supports it. If no sentence supports it, leave it out.

## Field rules
- **doc_type**, one of `master_circular`, `circular`, `circular_letter`, `guideline`, `policy`, `notification`, `letter`, `other`,
  from the document's own heading or reference line ("FE Circular No." → `circular`; "Circular Letter" → `circular_letter`).
- **department**: the issuing department's abbreviation as printed (BRPD, DOS, FEPD, FEOD, PSD, SFD, SMESPD, ACD, DMD, DFIM, BFIU, ...).
- **reference_number**: as printed, in English if the document gives one; otherwise the Bangla as printed.
- **issue_date**: the date printed on the circular (YYYY-MM-DD). If only a Bangla-calendar date is printed, convert it and say so in `uncertain`.
- **effective**: when the rules start.
  - `stated` + `date` only when the text gives a start date ("effective from 1 January 2025").
  - `immediate` when it says "with immediate effect", "will take effect immediately", "অবিলম্বে কার্যকর" or similar.
  - `not_stated` (date and quote null) when it says nothing. **The issue date is never the effective date unless the text says so.**
- **applies_to / exempt**: who the circular addresses or covers, from the addressee line ("All scheduled banks" →
  `all_scheduled_banks`) and any explicit scope or exemption sentence ("shall not apply to", "will not, however, apply",
  "প্রযোজ্য হবে না", "যোগ্য বিবেচিত হবে না"). Entity values: `all_scheduled_banks`, `state_owned_banks`,
  `private_commercial_banks`, `islamic_banks`, `foreign_banks`, `specialized_banks`, `nbfis`, `authorized_dealers`,
  `money_changers`, `payment_system_operators`, `mfs_providers`, `mfis`, `exchange_houses`, `offshore_banking_units`,
  or `other:<short text>` (for example `other:residents`, `other:bank branches`, `other:agent banking customers`).
- **obligations**: one item per distinct requirement this circular places on regulated institutions (or that they must make others follow).
  - `type`: `must` (positive duty), `must_not` (prohibition, including caps like "shall not exceed"), `may` (an explicit
    permission or option), `report` (submit a return, report or information to Bangladesh Bank), `keep_records`,
    `get_approval` (obtain prior approval), `disclose` (publish, or inform customers or the public).
    Use the most specific type ("submit a report to BB" is `report`, not `must`). If one sentence holds two duties of
    different types, list both with the same quote. Bangla "করবে / করতে হবে / করিবে" is a duty (`must`);
    "করা যাবে না / পারবে না" is `must_not`; "করতে পারবে / করা যাবে" is `may`.
  - `what`: one plain English sentence saying the duty, using **only** what the quote says. Do not add words such as
    "formally", "strictly", "immediately", "ADs must ensure", or an appendix or form name that the text does not give.
  - `subject`: an entity value as above.
  - `deadline`: YYYY-MM-DD for a date; the wording for a relative deadline ("within 15 days of each quarter end");
    a frequency counts ("monthly"); "regularly" is not a deadline (use null). Give `deadline_quote`, and
    `deadline_page_id` only when the deadline is on a different page from the duty.
  - **Include:** numbered instructions, conditions that must be met, limits and rates the institutions must apply.
  - **Exclude:** background and recitals ("Bangladesh Bank has decided..."); what Bangladesh Bank itself will do;
    "all other instructions remain unchanged"; "this takes effect immediately"; "please acknowledge receipt";
    "please bring this to the notice of all concerned" and its Bangla forms when it is only distribution boilerplate.
  - Only pages with `in_obligation_window: true`, and never pages inside an enclosure.
- **enclosures**: pages that are a copy of another circular, a previously issued letter, or a form attached to this one.
  List them. **Rules and links that appear only inside an enclosed copy belong to that enclosed document, not to this circular**:
  do not list them as obligations or relationships of this row. (A blank form for banks to fill in is an enclosure too;
  the duty to submit it comes from the main text.)
- **relationships**: only where **this circular's own text** explicitly names another instrument. One item per named instrument.
  - `amends` (changes part of it), `repeals` (cancels or withdraws it), `replaces` (takes its place, including "supersedes"),
    `clarifies` (explains it without changing it), `references` (merely mentions it: "in reference to", "as per",
    "issued under section 45 of the Bank Company Act, 1991").
  - Use `amends`, `repeals` or `replaces` only when the words say so. Being issued under an Act is `references` to that Act.
  - A form or annex that mentions this circular itself is not a relationship.
  - `target_reference` as printed (circular reference, or the Act's name); `target_date` YYYY-MM-DD if printed, else null.
  - Read the whole document for relationships, not only the window.
- **key_changes**: what this circular changes compared with the earlier rules, each with the quote that says it.
  An empty list when it changes nothing (a new rule, a reminder, a clarification).
- **summary_points**: 2-6 short English points a correct summary must contain (what, who, numbers, deadlines), each with its supporting quote.
- **summary_en**: 2-4 plain English sentences.
- **page_notes**: only for pages that are not normal full-text pages: `letterhead_only`, `blank`, `form_or_table_only`,
  `partly_illegible` (say which part), `enclosure`.
- **uncertain**: every judgement call you made and why. Empty is fine when nothing was doubtful.

## Before you finish each circular
- `python check_key.py <row>` shows no ERROR.
- Every WARN quote re-checked against the image.
- You did not invent anything: every value is in the document, and every quote is on the page you name.
