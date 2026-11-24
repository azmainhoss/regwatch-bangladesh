# Review: points hidden by the second page reading (2026-11-24)

Readers saw boxes like "2 summary points are not shown here". On the live site 4,343 of about 10,900 reader
points (40%) were hidden. Almost all failed one check: `QUOTE_READING`, the second reading of the page image
(Gemini) that must agree with the text we quote. Ten random hidden cases were inspected by hand (both
readings side by side, then run through `same_reading()` to see which rule rejected them).

Rule kept throughout: **no new manual step**. Nothing below adds review work for a person.

## The 10 cases

| # | Circular, sentence | Result | What the evidence showed | Root cause |
|---|---|---|---|---|
| 1 | BRPD-2 CL 09/2026 p1.s5 | MISREAD | Ours `১৭৭`, both readers `৭১৭` (notification number) | Our text-layer reading is wrong (legacy-font digit order) |
| 2 | BRPD-1 CL 38/2026 p1.s8 | MISREAD | এতদতীত / এতদ্ব্যতীত, উল্লেখিত / উল্লিখিত, `।` / `.`; 4% edits | Spelling variants over a 3% edit limit |
| 3 | BRPD-1 CL 16/2026 p1.s8 | MISREAD | Readers have the word নতুন ("new") that ours lacks; ইন্সট্রুমেন্ট / ইনস্ট্রুমেন্ট | A real dropped word (correctly fails) plus a spelling variant |
| 4 | ACD-1 C 02/2026 p3.s15 | MISREAD | Both readings empty | Crop missed the sentence |
| 5 | FCRPD CL 19/2026 p1.s10 | MISREAD | Readers saw only the last line, `হবে।` | Crop missed the sentence (box off by about 2 lines; boxes checked: lines 23 and 24 at y 648-680) |
| 6 | BRPD-2 CL 13/2026 p2.s11 | UNCLEAR | Readers read clauses (খ)/(গ) below ours | Crop missed the sentence |
| 7 | BFIU C 34/2026 p3.s15 | UNCLEAR | Readers read clause (২) below ours | Crop missed the sentence |
| 8 | BRPD-3 C 01/2026 p1.s3 | UNCLEAR | One reader read the phone line above; the other differs on the year (১৪৩০ / ১৪৩৩) | Crop miss, plus a real figure disagreement |
| 9 | ACD-1 C 03/2026 p15.s13 | UNCLEAR | Readers start one line above ours | Crop missed the sentence |
| 10 | BRPD-1 CL 17/2026 p1.s2 | UNCLEAR | The two readers disagree with each other on the year (২০২৪ / ২০২৬); one skipped a line | Reader disagreement, plus a crop issue |

## Root causes and what was done

1. **Crop misses (cases 4-9, part of 8 and 10). Fixed.** The strip sent for the second reading was cut from
   the line boxes with 15/1000 margin (one line), and the tie-break strip had none. The boxes come from a model
   reading of the page and are often off by one or two lines, so the strip held other lines. The two readings
   then "disagreed" with a sentence they never saw.
   - Strips now have 40/1000 margin, about three lines, on both readings. `focus_reading()` already keeps only
     the lines that answer to ours.
   - A strip that does not hold our lines at all is recorded as `CROP_MISS`, not as evidence. The whole page is
     read once and our lines are found in it (`locate_in_page_reading`).
2. **Bangla spelling variants (case 2, part of 3). Fixed.** Hasant and conjunct forms, short and long i and u,
   khanda ta, and the danda against a full stop no longer count as edits (`fold_spelling`). Meaning stays
   protected: numbers, dates, "no" words and reference codes are still compared exactly, and a **whole word
   missing on one side still fails** (`whole_word_gap`), so case 3 correctly stays unconfirmed.
3. **Real disagreements (case 1, parts of 8 and 10). Kept as failures, shown with "Check page N".**

**Display.** Readers no longer see "N points are not shown here". Every point that is not rejected is shown.
Points that passed every check keep "Page N · Checked"; the others carry a **"Check page N"** link that opens the
highlighted lines (`SHOW_UNCONFIRMED_POINTS`, default on).

**Existing data.** `backend/scripts/rejudge_readings.py` re-judged the stored readings with no model calls.
Live, 2026-11-24 (backup `data/regwatch.before-rejudge-20261124-110011.db`):

| Before | After | Count |
|---|---|---|
| MISREAD / UNCLEAR | CLEAN (accepted by the new comparison) | 17 |
| MISREAD / UNCLEAR | queued again; every stored reading was a crop miss, so the page reader reads it again with the wider strip and the page fallback | 396 |
| MISREAD / UNCLEAR | kept (genuine disagreement) | 400 |

891 claims on the 81 changed pages were checked again. The re-reads run by themselves within the free Gemini
quota, about one to two days.

## Self-correction when both readers agree (built 2026-11-24)

Case 1 is the common shape of a genuine "misread": the two independent readers (different models and image
sharpness) agree with each other and differ from our reading only in a figure. Our reading is the odd one out,
so it is corrected automatically (`reading.figure_fixes`, `claims/autofix.py`). The reading becomes `CORRECTED`
when every one of these holds:

- both readings agree with each other (`same_reading`);
- the figures are the only difference: our text with their figures put in must then agree with them in every
  word, "no" word and reference code;
- every changed figure has 2 or more significant digits (`০৩` → `০৫` is refused), and the text layer does not
  confirm ours;
- one old figure maps to one new figure, and no unchanged copy of the old figure stands in the same sentence.

The point's wording and its displayed quote get the corrected figures. The old wording is kept in
`original_fields` and `review_note` reads "Figures corrected from two agreeing page readings: 177 -> 717". The
checks then run on the corrected sentence, so the point is shown as "Checked" when everything else passes.

Live, 2026-11-24 (backup `data/regwatch.before-rejudge-20261124-111746.db`): **31 sentences corrected, 82 points
updated, 53 of them now shown as Checked.** All 31 were checked by hand before applying. Typical cases:
`১৭৭→৭১৭` in the BRPD-2 law-review notification number (a recurring digit reversal), `৩`/`৬` in years
(`২০২৩→২০২৬`), সঞ্চয়পত্র রুলস `১৯৯৭→১৯৭৭`, ব্যাংক রেজল্যুশন অধ্যাদেশ `২০২৩→২০২৫`.

**Spreading a proven correction (built 2026-11-24).** A correction proven by two agreeing readings also fixes
the same figure elsewhere in the same circular, under three conditions:

- it stands in the same surroundings, the 8 characters before and 4 after (e.g. `(ল’রিভিউ)১৭৭/২০২৬`);
- that sentence's own reading did not confirm the old figure (it is not CLEAN);
- the text layer does not confirm the old figure.

A plain `১৭৭` elsewhere (for example "section 177") is never changed. The point's wording and quote get the
corrected figure. If that sentence still has other unresolved differences, it keeps "Check page N"
(`claims/autofix.py` `load_fixes`).

Live: 24 circulars carry a proven correction, and 242 of their points were checked again. On BRPD-2 CL 18/2026
every quote of the law-review notification now reads `৭১৭`. One point is "Checked"; the four on the enclosure
page keep "Check page 2" because that page's reading also differs in `৪৪৫` vs `৪৪৫৪`.
