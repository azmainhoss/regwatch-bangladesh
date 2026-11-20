# Claim checks: build spec

Status: ready to build. Written 2026-11-13.
Scope: steps 2, 3 and 5 of `research/07_REDUCE_HUMAN_REVIEW.md` (step 1, "analyse only when every page is read", is already built).
- Step 2: every shown field points at its evidence sentences, and plain code checks each claim (dates, numbers, duty wording, who, change-the-law links).
- Step 3: each claim gets its own status. A failed claim is hidden, not the whole circular. A small screen lets a person decide one held claim at a time.
- Step 5: for Bangla and scanned pages, only the quoted sentences are re-read and compared. This replaces DECISIONS.md 10's page-level 2% rule.

Read first: the business-purpose file at the repo root (golden rule, feature 5), `DECISIONS.md`, `research/07_REDUCE_HUMAN_REVIEW.md` sections 3.2-3.3, and `docs/specs/ALERTS_SPEC.md` section 8.2 (the store pattern this spec reuses).

Not in scope (later plan steps): the answer key and scoring harness (step 4), the independent second-opinion check on meaning (step 6), cited impact lines (step 7), missed-duty search (step 8), the weekly audit (step 10). This spec leaves a slot for step 6 (check `MEANING`, section 3.3) so it can be added without a schema change.

---

## 0. Ground rules for every chunk (read first)

1. **Instant, up-to-date UI is the top priority.** After any approve, reject or fix, every screen that shows that claim or its circular shows the new state at once, without a manual refresh: the review screen, its tab count, the circular page (summary, requirements, links, the "N points not shown" line), the links view and the in-force badge. Same tab: through the shared store. Other tabs: through a `BroadcastChannel`. Other people: through polling (section 6.3). Controls react on the tap; network work runs after. Slow work (re-reading quoted sentences) runs in the background job, never inside a request.
2. **Every waiting screen says what it waits for and roughly how long, and updates by itself.** Examples are in sections 5.1 and 5.2.
3. **No technical details on any screen:** no hashes, IDs, sentence IDs, status codes, model or vendor names, raw error text, internal status names (`WAITING_FOR_PERSON`). Map every internal value to plain words. IDs may travel in JSON; they never show.
4. **Never mention how code was written or which tools wrote it** in code comments, docs, UI copy, test names or commit messages, and never show a model or vendor name on screen. Model names live only in `core/config.py` settings. Say "the analysis" or "the second reading" when you must.
5. **Do not commit or push.** After every pytest run: `git checkout -- backend/app/tests/fixtures` (an old test rewrites a fixture PDF).
6. **Free tiers only.** Never switch on a paid model. Use the keys already in `.env` (`GEMINI_API_KEY` plus `GEMINI_EXTRA_API_KEYS`).
7. **Golden rule.** A customer never sees a claim that has not passed every check that applies to it, or been approved by a person. A quote shown is always text copied from the stored page by sentence ID, never typed.
8. **Tests:** record the pytest baseline before you start (`.venv\Scripts\python.exe -m pytest -q` from the repo root; `pytest.ini` sets `pythonpath = .` and `testpaths`). Last known: 368 pass, 5 fail, 1 error (old data/setup failures). No new failures are allowed. `npm run build` and `npm run lint` in `frontend/` must pass.
9. **Browser checks** at desktop width and at 375 px for every touched screen: each control reacts at once, every other screen showing the same data has already changed (including the screen you go back to, and a second open tab), no sideways scroll at 375 px.
10. Never send requests to bb.org.bd. The archive download, import and page reader keep running; do not stop them except where chunk 4 says so.

---

## 1. What exists today (and what changes)

| Area | File | Today | After this spec |
|---|---|---|---|
| Analysis call | `analysis/pipeline.py`, `prompts.py` (v2) | Quotes by sentence ID for provisions, obligations, links only. Summary, key changes, applicability, dates are free text with no evidence. | Prompt v3: every shown field carries evidence sentence IDs (section 2). |
| Quote check | `analysis/citations.py` | Checks each quote is exact on its page. | Kept as check `QUOTE_FOUND`. |
| Publication gate | `pipeline.py` step 4 | Whole document to `AWAITING_REVIEW` on any failed quote, coverage < 95%, any AMENDS/REPEALS/SUPERSEDES/REPLACES, HIGH impact (dead: never filled), or forced. | Removed. Status is per claim (section 4); document status is derived from claim statuses (4.4). |
| Claims table | `analysis/models.py` `AnalysisClaim` | Only provisions become claims. | Every shown item becomes one claim row (3.1). |
| Obligations / links | `obligations/models.py`, `relationships/models.py` | `verification_status` VERIFIED when the quote is exact. A link of type AMENDS found by the analysis with an exact quote is VERIFIED at once and changes the target's in-force status with no person. | Their `verification_status` follows the claim status (4.5). Change-the-law links become VERIFIED only by a person. |
| Re-review | `service.py` `needs_re_review` | A human-published circular goes fully back to review when re-analysed. | Person decisions carry over claim by claim (4.6). |
| "Unchanged" skip | `service.py` `input_fingerprint` | Model + page texts. | Also includes `PROMPT_VERSION`, so v3 can run on circulars analysed with v2. |
| Customer view | `components/CircularDetail.tsx` | Reads `analysis.structured_payload` directly; shows everything, whatever its status. | Reads a checked view from `GET /documents/{id}/claims` through a new store; hidden claims become one plain line. |
| Admin queues | `app/admin/page.tsx` tabs `queue`, `collection`, `upload`, `library`, `links`, `engine` | No claim review. | New tab `checks` ("Points to check"). |
| Bangla pages | `extraction/vision.py`, `vision_jobs.py`, `scripts/read_pages.py` | One reading (Flash-Lite). The page-level two-reader rule of decision 10 is not built. | Quoted sentences on image-read pages are re-read from a crop and compared (section 7). |
| Alerts | `analysis/service.py::_announce_circular` | Any analysis that publishes fires "new circular", also for archive circulars analysed on request. | No alert when the circular was an archive circular (status `EXTRACTED` before the analysis). |
| Compliance | `compliance/router.py::not_addable_reason` | Needs document status `PUBLISHED*` and obligation VERIFIED. | Needs the obligation's claim to be shown; document status `AWAITING_REVIEW` no longer blocks a shown obligation. |

Background hooks stay as built in step 1: new live circulars (status `PUBLISHED_MACHINE_PROCESSED`) are analysed by themselves once all pages are read (`analysis/auto.py`); archive circulars (status `EXTRACTED`) are only analysed when an admin presses "Run analysis". This spec adds: after any analysis, code checks run at once in the same job, and quoted-sentence reading checks are queued for the background reader (chunk 4).

---

## 2. Prompt v3: evidence for every field

`analysis/prompts.py`: `PROMPT_VERSION = "v3"`. Same sentence-ID rules (DECISIONS.md 7). Changes to the JSON the model returns (update `ANALYSIS_RESPONSE_SCHEMA` and `providers/mock.py` to match):

```
executive_summary: {
  summary_points: [ { text, evidence_ids } ]      # 2-5 short points, each one sentence, max 40 words
  key_changes:    [ { text, evidence_ids } ]      # only explicit changes the circular states
}
obligations[]: { title, obligation_type, requirement_description, quote_span_ids,
                 responsible_entity, who_ids, explicit_deadline, deadline_ids,
                 effective_date, effective_date_ids, reporting_frequency, consequence, consequence_ids, clause_reference }
applicability: { covered: [ { entity, evidence_ids } ], exemptions: [ { text, evidence_ids } ] }
deadlines:     { effective_date: {date, evidence_ids} | null,
                 compliance_deadline: {date, evidence_ids} | null,
                 reporting_deadline: {date, evidence_ids} | null }
relationships[]: unchanged (relationship_type, target_reference_hint, quote_span_ids)
provisions[]:    unchanged
classification:  unchanged (not shown to customers; the header uses the listing record)
```

- Dropped from the prompt: `short_summary`, `detailed_summary`, `background`, `purpose`, `affected_stakeholders`, `important_dates`, `impact_assessment` (unchecked free text; impact comes back in plan step 7).
- Prompt line to add: "Every field you fill must be stated in the sentences whose IDs you give for it. If a field is not stated, leave it null. Use the entity names from this list: ..." (the list in 3.4).
- `apply_quote_ids` (`analysis/sentences.py`) learns the new ID fields: each `*_ids` list is resolved with `SentenceIndex.resolve`; unknown IDs empty that field's evidence (the field then fails `HAS_EVIDENCE`). Quote text and boxes for display still come only from `quote_span_ids` / `evidence_ids`.
- `DocumentAnalysis.executive_summary` (NOT NULL) is filled with the shown summary points joined by a space, or "" when none; nothing reads it for customers any more.

---

## 3. Claims and their checks

### 3.1 One claim per shown item (`claims/build.py`)

`build_claims(payload, sentence_index, doc) -> list[ClaimDraft]`. Kinds:

| Kind | Made from | Fields kept in `fields` | Evidence keys in `evidence` |
|---|---|---|---|
| `SUMMARY_POINT` | each `summary_points[]` | `text` | `quote` |
| `KEY_CHANGE` | each `key_changes[]` | `text` | `quote` |
| `OBLIGATION` | each `obligations[]` | `title, description, obligation_type, who, deadline, effective_date, frequency, penalty, clause` | `quote, who, deadline, effective_date, penalty` (a missing key falls back to `quote`) |
| `APPLIES_TO` | each `applicability.covered[]` | `entity` | `quote` |
| `EXEMPTION` | each `applicability.exemptions[]` | `text` | `quote` |
| `DATE` | each non-null `deadlines.*` | `date_kind` (EFFECTIVE, COMPLIANCE, REPORTING), `date` | `quote` |
| `LINK` | each `relationships[]` | `claimed_type, shown_type, target_hint, target_document_id` | `quote` |
| `PROVISION` | each `provisions[]` (clause tree; not shown on the circular page today) | `number, heading, explanation, provision_type` | `quote` |

The `quote` evidence is what the reader sees and what is highlighted on the page image. One `ClaimCitation` row per run of sentences, as today.

### 3.2 Normalising text (`claims/wording.py`)

- `norm(text)`: Unicode NFC; remove zero-width joiners (U+200C, U+200D); Bangla digits ০-৯ to 0-9; lower case; curly quotes and dashes to plain; whitespace collapsed.
- `dates_in(text) -> set[date]`: finds `DD/MM/YYYY`, `DD-MM-YYYY`, `DD.MM.YYYY`, `D Month YYYY`, `Month D, YYYY`, `YYYY-MM-DD`, two-digit years (00-50 = 20xx, else 19xx), English month names and short forms, and Bangla Gregorian month names (জানুয়ারি, ফেব্রুয়ারি, মার্চ, এপ্রিল, মে, জুন, জুলাই, আগস্ট, সেপ্টেম্বর, অক্টোবর, নভেম্বর, ডিসেম্বর, with common spelling variants). Day first always (Bangladesh style). Bangla-calendar dates (বৈশাখ ...) are not converted, so they never confirm a date.
- `IMMEDIATE_EFFECT`: "with immediate effect", "immediately", "from the date of issue", "অবিলম্বে", "অনতিবিলম্বে", "জারির তারিখ হতে", "তাৎক্ষণিকভাবে".
- `numbers_in(text) -> multiset[str]`: digit runs after `norm`, joining `1,00,000` and `5.5`; `%` and `শতাংশ` kept as part of the number; dates are removed first (they are checked as dates). English words one-twelve, fifteen, twenty, thirty, forty-five, sixty, ninety, hundred count as numbers.
- Word lists (English and Bangla) used by the checks below. Keep them in this one file, as tuples, so plan step 4 can tune them on the dev split only:
  - `NEGATION`: not, no, never, shall not, must not, may not, cannot, prohibited, forbidden, barred, refrain; না, নয়, নহে, নেই, নাই, যাবে না, পারবে না, নিষিদ্ধ, বিরত.
  - `DUTY_WORDS` per obligation type: MANDATORY (shall, must, required, have to, ensure; করতে হবে, হবে, বাধ্যতামূলক, নিশ্চিত, আবশ্যক); PROHIBITION (`NEGATION`); PERMISSION (may, allowed, permitted, can; পারবে, পারবেন, পারে, অনুমতি) with no negation within the next 2 words; REPORTING (submit, report, send, furnish; প্রেরণ, দাখিল, পাঠাতে, রিপোর্ট, অবহিত); APPROVAL (approval, approve, prior permission, consent; অনুমোদন, অনুমতি, সম্মতি); RECORD_RETENTION (preserve, maintain, retain, keep; সংরক্ষণ); DISCLOSURE (disclose, publish, display; প্রকাশ, প্রদর্শন); CONDITIONAL (if, where, in case, provided, subject to; যদি, ক্ষেত্রে, শর্তে); RECOMMENDATION (should, encouraged, advised; উৎসাহিত, পরামর্শ).
  - `CHANGE_WORDS` per link type: AMENDS (amend, amendment, modified, revised, substituted, inserted, deleted; সংশোধন, সংশোধিত, পরিবর্তন, সংযোজন, প্রতিস্থাপ); REPEALS (repeal, rescind, revoked, withdrawn, cancelled, ceases to have effect; রহিত, বাতিল, প্রত্যাহার); SUPERSEDES and REPLACES (supersede, in supersession of, replace, in place of; প্রতিস্থাপন, পরিবর্তে, স্থলে).
  - `EXEMPT_WORDS`: except, exempt, not applicable, shall not apply, excluding; ব্যতীত, ছাড়া, প্রযোজ্য নয়, অব্যাহতি.
  - `CLARIFY_WORDS`: clarify, clarification; স্পষ্টীকরণ, ব্যাখ্যা.

### 3.3 The checks (`claims/checks.py`)

Each check returns `PASS`, `FAIL`, `WAIT` (cannot decide yet) or `NOT_RUN`, plus a plain message for the review screen. "Evidence text" means the stored text of that field's evidence sentences.

| Check | Applies to | Pass rule | Plain message on fail |
|---|---|---|---|
| `HAS_EVIDENCE` | all | the claim's `quote` evidence has at least one known sentence | "This point does not say which sentence it comes from." |
| `QUOTE_FOUND` | all | `CitationValidator` result is `VERIFIED_EXACT` or `VERIFIED_NORMALIZED` for every fragment | "The quoted words are not on page N." |
| `PAGE_READ` | all | no evidence sentence is on a page whose `quality_status` is `NEEDS_HUMAN_REVIEW` or `PENDING_VISION` | "Page N has not been read cleanly yet." |
| `QUOTE_READING` | evidence sentences on image-read pages (chunk 4) | every such sentence's reading check is `CLEAN` or `NOT_NEEDED`. `WAITING` gives `WAIT`. | "The second reading of page N does not match ours." / "Part of page N could not be read clearly." |
| `DATES` | OBLIGATION (deadline, effective_date), DATE, and any date written in SUMMARY_POINT, KEY_CHANGE, EXEMPTION text | each date is in `dates_in(evidence text)`; an effective date equal to the circular's issue date also passes when the evidence has an `IMMEDIATE_EFFECT` phrase | "The date 31 December 2024 is not in the quoted sentences." |
| `NUMBERS` | text of SUMMARY_POINT, KEY_CHANGE, EXEMPTION; OBLIGATION title, description, penalty | every number in the text is in `numbers_in(evidence text)` (as a multiset member) | "The number 2.5% is not in the quoted sentences." |
| `DUTY_WORDING` | OBLIGATION | the quote has a word from `DUTY_WORDS[type]`; and if type is not PROHIBITION, CONDITIONAL or RECOMMENDATION, the quote has no strong prohibition phrase (shall not, must not, prohibited, যাবে না, নিষিদ্ধ) | "The point says this must be done, but the quote says it must not." (and similar per type) |
| `WHO` | OBLIGATION (`who`), APPLIES_TO (`entity`) | the value maps to one entity in 3.4 and one of that entity's aliases is in the `who` evidence or in the circular's addressee block (the first 8 sentences of page 1); a narrower entity also passes when the addressee says "all scheduled banks" / "সকল তফসিলি ব্যাংক" and the entity is a kind of scheduled bank | "Who must do this is not named in the circular." |
| `EXEMPT_WORDS` | EXEMPTION | the evidence has a word from `EXEMPT_WORDS` | "The quote does not state an exception." |
| `OVERCLAIM` | SUMMARY_POINT, KEY_CHANGE | if the text uses amend/repeal/replace/supersede words, the evidence has `CHANGE_WORDS` | "The point says a rule changed, but the quote does not." |
| `TARGET_NAMED` | LINK | some key from `relationships/linking.py::reference_keys(target_hint)` is among the keys of the quote text | "The other circular is not named in the quote." |
| `CHANGE_WORDS` | LINK with claimed type AMENDS, REPEALS, SUPERSEDES, REPLACES | the quote has a word from `CHANGE_WORDS[type]` | "The quote does not use words that change another rule." |
| `TARGET_FOUND` | same | the hint resolves to exactly one shared-library circular (`linking._unique_match`) | "The other circular is not in the library, or more than one matches." |
| `TARGET_OLDER` | same | target `publication_date` < this circular's | "The other circular is not older than this one." |
| `MEANING` | all | slot for plan step 6; always `NOT_RUN` for now and does not block | (none) |

**Link downgrade.** When a change-the-law link fails `CHANGE_WORDS`, `TARGET_FOUND` or `TARGET_OLDER`, its `shown_type` becomes `REFERENCES` (shown as "Mentions"), the failed results stay in `checks` for the reviewer, and the claim is judged on `HAS_EVIDENCE`, `QUOTE_FOUND`, `PAGE_READ`, `QUOTE_READING`, `TARGET_NAMED` only. CLARIFIES without `CLARIFY_WORDS`, and every RELATED_TO or IMPLEMENTS, are downgraded the same way. When a change-the-law link passes everything, `shown_type` stays `REFERENCES` until a person confirms it (4.2).

### 3.4 Entity list (`wording.ENTITIES`, canonical name → aliases, English and Bangla)

SCHEDULED_BANK (scheduled bank(s), all banks, তফসিলি ব্যাংক), STATE_OWNED_BANK, PRIVATE_COMMERCIAL_BANK, ISLAMIC_BANK (Islamic Shariah, ইসলামী শরীআহ), FOREIGN_BANK, SPECIALIZED_BANK, NBFI (non-bank financial institution, financial institution(s), আর্থিক প্রতিষ্ঠান), AUTHORIZED_DEALER (AD branch, authorised dealer, অনুমোদিত ডিলার), MONEY_CHANGER (মানি চেঞ্জার), PAYMENT_SERVICE_PROVIDER (PSP, PSO, payment system operator), MOBILE_FINANCIAL_SERVICE (MFS, মোবাইল আর্থিক সেবা), MICROFINANCE_INSTITUTION (MFI, ক্ষুদ্রঋণ), EXCHANGE_HOUSE. Old values from v2 (`SCHEDULED_COMMERCIAL_BANK`) map to SCHEDULED_BANK. The circular page labels come from one shared map (frontend `ENTITY_LABELS`, extended to every name here).

### 3.5 High-stakes

A claim is high-stakes (`is_high_stakes = True`) when any of: OBLIGATION of type MANDATORY, PROHIBITION or REPORTING; OBLIGATION with a penalty; any claim with a deadline or DATE (COMPLIANCE or REPORTING) later than today (Dhaka date, `compliance/rules.py::today_dhaka`); LINK whose claimed type is AMENDS, REPEALS, SUPERSEDES or REPLACES.

---

## 4. Per-claim status and hiding

### 4.1 Statuses (`AnalysisClaim.check_status`)

| Status | Meaning | Shown to customers? |
|---|---|---|
| `CHECKING` | some check gave `WAIT` (reading check queued) | No, a placeholder line |
| `PASSED` | every applicable check passed | Yes |
| `WAITING_FOR_PERSON` | in the review queue (`review_queue` = `REQUIRED` or `OPTIONAL`) | No, a placeholder line. Exception: a change-the-law LINK that passed all checks is shown as "Mentions" while it waits. |
| `NOT_SHOWN` | failed a check; no person is required | No, a placeholder line |
| `APPROVED` | a person approved it | Yes |
| `FIXED` | a person corrected and approved it | Yes |
| `REJECTED` | a person rejected it | Never; no placeholder either |

`verification_status` on `AnalysisClaim` stays as the quote result (unchanged meaning).

### 4.2 Routing after the checks (`claims/status.py::route(claim, doc)`)

A circular is **new** when its `publication_date` is within the last `CLAIM_NEW_CIRCULAR_DAYS` (default 365) days.

| Check result | High-stakes? | New circular? | Status | Queue |
|---|---|---|---|---|
| any `WAIT`, no `FAIL` | any | any | `CHECKING` | none |
| all pass, not a change-the-law link | any | any | `PASSED` | none |
| all pass, change-the-law link | yes | yes | `WAITING_FOR_PERSON` (shown as "Mentions") | `REQUIRED` |
| all pass, change-the-law link | yes | no | `WAITING_FOR_PERSON` (shown as "Mentions") | `OPTIONAL` |
| a `FAIL` | yes | yes, or the claim's own date is in the future | `WAITING_FOR_PERSON` | `REQUIRED` |
| a `FAIL` | otherwise | | `NOT_SHOWN` | `OPTIONAL` (a person may fix it by choice) |

An admin's "Ask for review" (circular page, per point, or "all points of this circular") sets `WAITING_FOR_PERSON` / `REQUIRED` and hides the point until decided.

### 4.3 How feature 5's publish rules map to claims

| Feature 5 rule | Now |
|---|---|
| A quote fails | That point fails `QUOTE_FOUND` and is hidden; the rest publishes. |
| Coverage below 95% | No whole-document hold. Readers see "Showing 12 of 14 points". A new circular with zero shown points is listed on the review screen ("Circulars with nothing to show"), with a re-run button. |
| Changes or kills older law | The link is shown only as "Mentions" and waits for a person. The target's in-force status changes only after a person confirms (4.5). |
| High impact | Removed (never filled). Replaced by high-stakes per point (3.5). |
| Pages missing | Analysis waits for every page (step 1). Points on pages a person must read are hidden (`PAGE_READ`). |
| Someone asks for review | "Ask for review" per point or per circular (admins). |
| "Machine verified" | Every shown point passed every check. Badge "Checked" when all points are shown, "Partly checked" otherwise. |
| "Human reviewed" | The point was approved or fixed by a person. Label "Checked by our team". |

Golden rule stays intact: nothing that failed or is unchecked reaches a customer; the only thing ever shown before a person decides a change-the-law link is the weaker, supported statement "this circular mentions X", with its exact quote.

### 4.4 Document status (`claims/status.py::document_status`)

Recomputed after every analysis, check run and decision, in the same transaction:
- any claim `WAITING_FOR_PERSON` with queue `REQUIRED` → `AWAITING_REVIEW` (passed points are still shown);
- else any claim `APPROVED`, `FIXED` or `REJECTED` → `PUBLISHED_HUMAN_REVIEWED`;
- else → `PUBLISHED_MACHINE_VERIFIED` (also when some points are hidden or still checking; the counts say so);
- never changes `WITHDRAWN`, `SUPERSEDED`, `EXTRACTION_FAILED`.
- `_announce_circular` runs only when the status before the analysis was not `EXTRACTED` (archive circulars never alert).
- `POST /documents/{id}/publish` no longer accepts `PUBLISHED_HUMAN_REVIEWED` (400: "Decide each point on the Points to check screen."). `WITHDRAWN`, `SUPERSEDED`, `REJECTED`, `NEEDS_REVISION` work as today.

### 4.5 Keeping obligations and links in step (`claims/status.py::sync_rows`)

- `Obligation.verification_status`: `VERIFIED` when its claim is shown, `REJECTED` when rejected, else `PENDING_REVIEW`. A FIXED claim writes its fields back to the obligation row.
- `DocumentRelationship.verification_status`: `VERIFIED` when the claim is shown with `shown_type` not a change type (it is then a plain mention), or when a person confirmed the change type; `REJECTED` when rejected; else `PENDING_REVIEW`. `relationship_type` keeps the claimed type; in-force code already reads only `VERIFIED` links, so a waiting change-the-law link no longer changes in-force status.
- **Customers** (non-superusers) get links from `relationships/status.py` and `graph.py` with `relationship_type` replaced by the claim's `shown_type` and only shown links included; admins see the real type and the waiting ones. `POST /relationships/{id}/review` calls the same decision function as the review screen (5.2), so both screens stay in step.
- `compliance/router.py::not_addable_reason`: a document in `AWAITING_REVIEW` no longer blocks; the obligation must be `VERIFIED`. Reason text for the rest: "This requirement is waiting for a check."

### 4.6 Re-analysis keeps decisions

`AnalysisClaim.fingerprint` = SHA-256 (internal only) of kind + sorted evidence sentence IDs + `norm`-ed fields. When a new run makes a claim whose fingerprint matches a claim of the previous analysis that is `APPROVED`, `FIXED` or `REJECTED`, copy its status, fields (for FIXED), reviewer, time and note, and set `carried_from_claim_id`. All other claims are routed fresh. This replaces `needs_re_review`.

---

## 5. Screens

### 5.1 Circular page (`components/CircularDetail.tsx`)

Reads only from `claimsStore` (`useDocClaims(doc.id)`), never from `structured_payload`.
- **Summary:** shown `SUMMARY_POINT`s as bullets, each with a small "Page 3" link that opens the page panel with the quote highlighted. The Purpose paragraph is removed.
- **What has changed:** shown `KEY_CHANGE`s, same pattern.
- **Requirements:** shown `OBLIGATION`s (title, type tag, description, Bangla quote with `lang="bn"`, page link, applies to, deadline). "In your register" and "Add to register" keep working through `obligation_id`.
- **Who it applies to / Exceptions:** shown `APPLIES_TO` and `EXEMPTION`s.
- **Dates:** issue date from the circular record; other dates from shown `DATE` claims.
- **Related circulars:** shown `LINK`s, labelled by `shown_type` ("Mentions", "Amends", ...).
- Each shown point has a quiet tag: "Checked against page 3" (PASSED) or "Checked by our team" (APPROVED, FIXED).
- **Placeholders**, one line per section with hidden points (counts by state, page numbers listed), always with the "Page N" link to the original:
  - waiting for a person: "1 requirement is waiting for our team to check it, usually within one working day. Until then, read page 3 of the original."
  - not shown: "1 point did not pass our checks, so it is not shown. Read page 3 of the original."
  - checking: "1 point is still being checked against the page image, about 4 minutes left. This page updates by itself." When paused: "... checking is paused until about 14:00, when today's free limit resets."
  - The page link on a placeholder opens the page panel with the hidden point's quoted lines highlighted (the existing yellow line highlight), but only when that point passed `QUOTE_FOUND` and `PAGE_READ` (the lines really are on the page). Then the line reads "... Read the highlighted lines on page 3 of the original." If the quote itself failed, the link opens the page with no highlight. The point's own wording is never shown. In `GET /documents/{id}/claims`, each `hidden[]` entry gains `quote_boxes` (empty when not allowed).
- Above the summary: "Showing 12 of 14 points." (only when some are hidden).
- **Admins** additionally see on each point its plain state ("Waiting for a check", "Not shown: date not in the quote") with "Review" (opens `/admin?tab=checks&point=<id>`) and "Ask for review" (hides it at once, optimistic). Header button "Ask for review of all points".

### 5.2 Review screen: admin tab `checks`, label "Points to check" (`components/ClaimReview.tsx`)

One point at a time. Tab badge = number in `REQUIRED`.

```
Desktop (two columns)                                      375 px (one column)
+------------------------------+------------------------+   [Filter: Needs a decision (3) | Optional (41)]
| 1 of 3  Needs a decision     | Page 3 image           |   Point card
| Requirement · Due 31 Dec 2026|  quote lines           |   Quote card
| "Banks must submit ..."      |  highlighted           |   [Show page 3]  (opens the page below, collapsible)
| Why it is here:              |                        |   Sticky bottom bar, 44 px buttons:
|  - The date 31 December 2026 |                        |   [Approve] [Fix] [Reject] [Skip]
|    is not in the quote.      |                        |
| Quote (page 3): "..."        |                        |
| Second reading said: "..."   |                        |
| [Approve A] [Fix F] [Reject R] [Skip →]               |
+------------------------------+------------------------+
```

- **Content:** circular reference and title (link to the circular), point kind in plain words, the point's fields, "Why it is here" = the failed checks' plain messages (or "It changes which rule is in force; a person confirms these." for a passed change-the-law link), the quote (Bangla with `lang="bn"`), and for a misread sentence "Second reading said: ..." (chunk 4). Page image via the existing `PagePanel` with `highlight.boxes` from the claim's citations.
- **Filters:** "Needs a decision" (`REQUIRED`, high-stakes first, then soonest deadline, then oldest) and "Optional" (`OPTIONAL`: NOT_SHOWN and archive links, newest circular first). A small line under the filters lists "Circulars with nothing to show" (4.3) with "Run analysis again".
- **Approve (A):** status `APPROVED`; for a change-the-law link also `shown_type` = claimed type and the link becomes `VERIFIED`.
- **Fix (F):** inline form for that kind's fields (text, title, description, type select, who select from 3.4, dates as date inputs) and a sentence picker (the cited page's sentences as checkable lines, current evidence ticked). On save the code checks run again on the new values and are shown; if any fails, saving needs the tick "I checked this against the page image". Saved as `FIXED`, old values kept in `original_fields`. Esc cancels; Ctrl+Enter saves. Bangla misreads link to the existing page-correction flow ("Fix the page reading").
- **Reject (R):** one-tap reasons ("Not in the circular", "Wrong details", "Not a requirement", "Other" with a text box). Status `REJECTED`.
- **Skip (→ or J), Back (← or K)**, **?** shows the key list. Keys do nothing while a text field has focus (except Esc and Ctrl+Enter).
- **Instant:** the decision moves to the next point on the keypress (the next 5 points and their page images are preloaded); the POST runs after. On failure the point comes back with a notice "Could not save; try again." On 409 (someone else decided it): "Someone else already decided this point." and move on.
- **Waiting text:** loading: "Loading the next point..." skeleton; empty: "Nothing needs a decision. New points appear here by themselves (checked every 15 seconds)."
- Every decision writes an audit event (`audit.service.record`, actions `claim.approve`, `claim.fix`, `claim.reject`, `claim.ask_review`).

### 5.3 Wording rules

Plain English, short sentences. Internal names never show; map them in one place (`frontend/services/claimWords.ts`). Kind labels: Summary point, Change, Requirement, Applies to, Exception, Date, Link, Clause.

---

## 6. Data model, endpoints, jobs, migration of old analyses

### 6.1 Schema (one Alembic revision `c7e9a1b3d5f8_claim_checks.py`, `down_revision = "b9d1f3a5c7e8"`)

`analysis_claims`, add: `kind` String(32) not null default `PROVISION` (index), `order_index` Integer default 0, `fields` JSON default `{}`, `evidence` JSON default `{}`, `checks` JSON default `[]`, `check_status` String(32) not null default `CHECKING` (index), `review_queue` String(16) null (index), `is_high_stakes` Boolean default false, `obligation_id` GUID FK `obligations.id` SET NULL, `relationship_id` GUID FK `document_relationships.id` SET NULL, `fingerprint` String(64) (index), `carried_from_claim_id` GUID null, `original_fields` JSON null, `reviewed_by` GUID FK `users.id` SET NULL, `reviewed_at` DateTime(tz), `review_note` Text, `reject_reason` String(64).

New table `quote_reading_checks` (model `QuoteReadingCheck`, `claims/models.py`): `id`, `created_at`, `updated_at`, `page_id` FK `document_pages.id` CASCADE (index), `sentence_id` String(16), `line_indexes` JSON, `page_text_sha` String(64), `status` String(16) (`WAITING`, `CLEAN`, `MISREAD`, `UNCLEAR`, `NOT_NEEDED`; index), `our_text` Text, `reads` JSON (list of `{kind: CROP|SHARP_CROP|PAGE, text}`; the model name is stored as an internal field and never sent to the frontend), `numbers_confirmed` JSON, `attempts` Integer default 0, `last_error` Text, `checked_at` DateTime(tz). Unique (`page_id`, `sentence_id`, `page_text_sha`).

Upgrade with `.venv\Scripts\python.exe -m alembic upgrade head` (the app's `create_all` does not add columns to existing tables). SQLite is shared with the page reader and import; adding columns is safe while they run.

Settings (`core/config.py`): `CLAIM_NEW_CIRCULAR_DAYS=365`, `QUOTE_CHECK_MODEL="gemini-3.5-flash"`, `QUOTE_TIEBREAK_MODEL="gemini-3.5-flash-lite"`, `QUOTE_CHECK_DPI=200`, `QUOTE_TIEBREAK_DPI=300`, `QUOTE_CHECK_MAX_EDIT_SHARE=0.03`, `QUOTE_CHECK_CROPS_PER_CALL=12`, `QUOTE_CHECK_MAX_ATTEMPTS=3`.

### 6.2 Endpoints

| Method and path | Who | Returns |
|---|---|---|
| `GET /api/v1/documents/{id}/claims` | anyone who can read the circular | `{state: NO_ANALYSIS|ANALYSING|READY, counts: {total, shown, checking, waiting_for_team, not_shown}, checking: {minutes_left, paused_until}, sections: {summary, changes, requirements, applies_to, exemptions, dates, links, clauses}, hidden: [{section, page_number, state}]}`. Section items: `{id, kind, fields, quote, page_number, quote_boxes, checked_by: CHECKS|TEAM, obligation_id?, link?: {target_document_id, target_reference, shown_type}}`. No `checks`, `fingerprint`, `evidence` IDs or model fields. |
| same with `?all=1` | superuser | every non-rejected claim with `status`, `review_queue`, `is_high_stakes`, `checks` (name, result, plain message) |
| `GET /api/v1/claims/review?queue=REQUIRED|OPTIONAL&limit=20&after=<cursor>` | superuser | review items: claim (as `?all=1`), circular `{id, reference_number, title}`, page `{id, page_number}`, `second_reading` text when MISREAD, page sentences for the fix picker (`[{sentence_id, text}]`) |
| `GET /api/v1/claims/review/counts` | superuser | `{required, optional, checking, empty_circulars: [{id, reference_number, title}]}` |
| `POST /api/v1/claims/{id}/approve` `{note?}` | superuser | updated claim + circular `counts` + document status |
| `POST /api/v1/claims/{id}/fix` `{fields, evidence_ids, confirm_checked}` | superuser | same; 400 with the plain check messages when checks fail and `confirm_checked` is false |
| `POST /api/v1/claims/{id}/reject` `{reason, note?}` | superuser | same |
| `POST /api/v1/claims/{id}/ask-review` and `POST /api/v1/documents/{id}/claims/ask-review` | superuser | same |

Decisions on a claim not in `CHECKING`, `WAITING_FOR_PERSON` or `NOT_SHOWN` (for approve/fix/reject) or not shown (for ask-review) return 409 with the current claim. Existing endpoints change: `GET /documents/{id}/analysis` returns `structured_payload`, `raw_model_response`, `model_name`, `prompt_version`, `tokens_used`, `estimated_cost_usd` only to superusers (others get them empty); `GET /documents/{id}/obligations` and `/relationships` return only shown rows to non-superusers.

### 6.3 Client store (`frontend/services/claimsStore.ts`)

Same pattern as `relationshipsStore.ts` and `workspaceStore.ts`: module state + `useSyncExternalStore`, `once()` load de-dup, epoch counter to drop stale answers, `BroadcastChannel("regwatch-claims")`, refresh on window focus and visibility.
- State: `byDoc[docId]` (the `/claims` view; admin view in `byDocAdmin`), `queue.REQUIRED|OPTIONAL` (items, cursor), `counts`, `busy[claimId]`, `notice`.
- `decide(claimId, action, body)`: at once remove from the queue, update `counts`, update the claim and its section counts in `byDoc`/`byDocAdmin` (shown or placeholder); POST; on success put the server copy in, then call `relationshipsStore.loadStatus` for the circular and the link target when the claim is a LINK; broadcast `{docId}`; on failure roll back and set `notice`.
- Polling: circular page every 5 s while `counts.checking > 0` or the analysis is running, every 30 s while `waiting_for_team > 0`, otherwise none. Review tab: counts every 15 s while the tab is open. Other tabs reload `byDoc[docId]` and counts on a broadcast.

### 6.4 Background hooks

- `AnalysisService._replace_analysis_results`: after saving rows, call `claims.build` → `claims.checks.run_code_checks` → `claims.reading.ensure_reading_checks` (adds `WAITING` rows for sentences on image-read pages; marks `NOT_NEEDED` for text-layer and human-corrected pages) → `claims.status.route` → `sync_rows` → `document_status`, all in the same commit. Code checks are fast and run inside the job, never in a web request.
- Reading checks (chunk 4) run in `claims/reading_jobs.py::process_pending_quote_checks(db, limit)`, called at the start of each batch by `VisionWorker` (`extraction/vision_jobs.py`) and by `backend/scripts/read_pages.py`, newest circular first, before any page of an older circular is read. When the last check of a claim finishes, that claim is re-routed and the document status recomputed.
- After a page correction (`PageCorrection` flow), every claim citing that page goes to `CHECKING`: its quote text is looked up in the new page text (exact or normalized); found → new sentence IDs and code checks again; not found → `NOT_SHOWN` with "The quoted words are no longer on page N after its reading was corrected." Corrected pages count as read by a person (`NOT_NEEDED`).
- `analysis/auto.py` unchanged: live circulars are analysed by themselves; archive (`EXTRACTED`) only on request.
- `analysis/auto.py::reading_status` gains `quote_checks_waiting` and folds them into `minutes_left`, so the circular page says one honest number.

### 6.5 Existing analyses (`backend/scripts/backfill_claims.py`)

For the latest analysis of every version (9 analyses, 7 circulars in `data/regwatch.db` as of 13 Nov):
- build claims from the v2 payload: obligations, links and provisions use their `quote_span_ids` as evidence for every field; `short_summary` and `key_changes` have no evidence, so they become `NOT_SHOWN` ("This point does not say which sentence it comes from."); applicability and dates from v2 become `NOT_SHOWN` the same way;
- run code checks, queue reading checks, route, sync rows, set document status;
- links of a change-the-law type that are `VERIFIED` with no `reviewed_by` go back to `PENDING_REVIEW` (their targets' in-force status changes back; the script prints each one in plain words);
- default is a dry run that prints, per circular, "X shown, Y waiting for a person, Z not shown, W checking"; `--apply` writes. Safe to run twice (it skips analyses that already have kinds other than `PROVISION`).
- After it, the live circulars can be re-run with v3 from the circular page ("Run analysis"; the prompt version is now part of the fingerprint, so it is not skipped as unchanged).

---

## 7. Bangla and scanned pages: check only the quoted sentences (`claims/reading.py`)

Applies to evidence sentences on pages with `extraction_method` `GEMINI_VISION` or `MANUAL_SUBSCRIPTION_READING` and `is_human_corrected = False`. Every other page is `NOT_NEEDED` (text layer, decision 6; or a person typed it).

1. **Lines to judge.** The sentence's `line_indexes` (from `SentenceIndex`). `our_text` = those lines of our page reading, joined by newlines. Judging whole lines is stricter than judging the sentence alone, on purpose.
2. **Numbers from the text layer (no model).** If `DocumentPage.native_text` has digit runs (Bijoy and legacy-font PDFs keep digits as plain digits), each 2+ digit number of `our_text` that appears in `native_text` is marked confirmed (`numbers_confirmed`).
3. **Second reading, from a crop.** Render the page with `vision.render_page_png(pdf, n, dpi=QUOTE_CHECK_DPI)`, crop the union of the lines' `box_2d` (0-1000 scale) plus 1.5% top and bottom, full width with 2% margins. Send up to `QUOTE_CHECK_CROPS_PER_CALL` crops of one page in one call to `QUOTE_CHECK_MODEL`, with this instruction: copy every line exactly as printed, in the original script; do not correct spelling, grammar or numbers; keep Bangla digits; write [illegible] for anything unclear; answer JSON `{"crops": [{"index": n, "lines": ["..."]}]}`. Use the existing key rotation, per-key gates and quota handling in `vision.py` (a busy, rate-limit or quota reply leaves the row `WAITING` and does not count as an attempt).
4. **Same reading?** `same_reading(a, b)` after `norm` and removing punctuation:
   - neither contains `[illegible]`;
   - the multisets of numbers are equal, except that a number of `a` confirmed by the text layer in step 2 counts as present in `b`;
   - the multisets of `NEGATION` words are equal;
   - the multisets of reference codes are equal (department codes from `InstitutionDepartment.code` and "no." / "নং" followed by digits);
   - character edit distance / length of `a` ≤ `QUOTE_CHECK_MAX_EDIT_SHARE` (3%; a small pure-Python Levenshtein, no new package).
   Same → `CLEAN`.
5. **Tie-break.** Otherwise crop again at `QUOTE_TIEBREAK_DPI` with only the lines (no padding) and read with `QUOTE_TIEBREAK_MODEL`, same instruction. Ours same as the third → `CLEAN`. Second and third the same as each other but not ours → `MISREAD` (the third reading is kept and shown to the reviewer as "Second reading said"). Else → `UNCLEAR`.
6. **No line boxes** (some hand readings): read the whole page with the strict instruction and locate the sentence in that reading with `difflib.SequenceMatcher` (best window of the same length ±20%), then step 4. No match → `UNCLEAR`.
7. **Failures:** after `QUOTE_CHECK_MAX_ATTEMPTS` real failures (not busy or quota) → `UNCLEAR`. A page whose text changes gets new rows (the old `page_text_sha` no longer matches).
8. **Cost on free tiers:** about one call per image-read page that has quoted sentences, plus one per page with a disagreement. The free Flash quota is small (about 17 calls a day per key), which is enough for about 10 new circulars a week; archive circulars are only checked when an admin runs their analysis.
9. A claim whose sentences are `MISREAD` or `UNCLEAR` fails `QUOTE_READING` and is routed by 4.2. The quote is never replaced by the second reading; only a person's page correction changes the page text.

The thresholds here (3%, the word lists, the crop margins) are starting values. Plan step 4 tunes them on the dev split only and scores once on test; until then they are provisional.

---

## 8. Build chunks (in order; check each before the next)

### Chunk 1: claims and code checks (backend only)

Files: `backend/app/modules/analysis/prompts.py`, `providers/mock.py`, `sentences.py` (new ID fields), `pipeline.py` (remove the step 4 gate; keep `ClaimValidationReport` for the coverage number), `service.py` (build, check, route, sync, document status, carry-over, fingerprint with prompt version, no alert for archive), `models.py` (new columns); new `backend/app/modules/claims/` with `__init__.py`, `models.py` (`QuoteReadingCheck`), `wording.py`, `build.py`, `checks.py`, `status.py`, `reading.py` (only `ensure_reading_checks`: rows `WAITING` / `NOT_NEEDED`, no calls yet); `backend/migrations/versions/c7e9a1b3d5f8_claim_checks.py`; `core/config.py` settings; `compliance/router.py::not_addable_reason`.

Behaviour: sections 2, 3, 4.1-4.2, 4.4-4.6, 6.1, 6.4 first bullet. Until chunk 4, sentences on image-read pages stay `WAITING`, so their claims are `CHECKING` (hidden): safe by design.

Tests (new `backend/app/tests/test_claim_checks.py`):
- `dates_in`: each format in 3.2, Bangla digits, Bangla month names, two-digit years, a Bangla-calendar date (not matched); immediate-effect rule.
- `numbers_in` and `NUMBERS`: "2.5%" vs "২.৫%", "1,00,000", a number word, a missing number fails.
- `DUTY_WORDING`: PROHIBITION with "যাবে না" passes; PERMISSION with "পারবে না" fails; MANDATORY with "shall not" fails.
- `WHO`: alias match, addressee "সকল তফসিলি ব্যাংক" covers ISLAMIC_BANK, unknown entity fails.
- Links: all four change checks pass → `WAITING_FOR_PERSON` and `shown_type` REFERENCES; missing change words → downgraded and `PASSED` as a mention; target not named → `NOT_SHOWN`; two library matches → downgraded; target newer → downgraded.
- Routing table 4.2, row by row, with a frozen Dhaka date (monkeypatch `today_dhaka`).
- Document status rules 4.4; archive analysis records no "new circular" alert; live analysis does.
- Carry-over: approve a claim, re-run with the same mock payload → still `APPROVED`; change the deadline → routed fresh.
- Obligation and link rows follow claim status (4.5); a change-the-law link is no longer `VERIFIED` without a person.
- `input_fingerprint` changes when `PROMPT_VERSION` changes.
- End to end through `AnalysisService.analyze_document_version` with the mock provider on an English fixture: expected count of claims per kind and status.
- Update old tests that assert the whole-document gate (`test_phase3_9_publication_gates.py`, `test_phase3_ai_pipeline.py`, `test_phase3_5_hardening.py`, `test_phase3_8_data_integrity.py`, `test_phase0_fixes.py`, `test_quote_ids_and_providers.py`, `test_phase4_experience_correction.py`, `test_alerts.py`, `test_documents_ingestion_api.py`): keep each test's safety intent (a bad quote is never shown) and assert it at claim level. List every changed assertion in your report.

Done when:
- `.venv\Scripts\python.exe -m alembic upgrade head` ends without error, and `.venv\Scripts\python.exe -m alembic current` prints `c7e9a1b3d5f8 (head)`.
- `.venv\Scripts\python.exe -m pytest backend/app/tests/test_claim_checks.py -q` passes all.
- Full `.venv\Scripts\python.exe -m pytest -q`: no new failures against the baseline; then `git checkout -- backend/app/tests/fixtures`.
- a search for vendor and model names in `backend/app/modules/claims` finds nothing (model names live only in `core/config.py`).

### Chunk 2: the checked view for customers, and the backfill

Files: `backend/app/modules/claims/router.py` (`GET /documents/{id}/claims`, mount in `main.py`), `analysis/router.py` (field stripping, filtered obligations and links, publish rule 4.4), `relationships/status.py`, `graph.py`, `router.py` (customer view of links, review through the shared decision function: add `claims/decide.py` with approve/reject only for now), `analysis/auto.py::reading_status` (`quote_checks_waiting`), `backend/scripts/backfill_claims.py`; frontend `services/api.ts` (types and fetchers), new `services/claimsStore.ts`, new `services/claimWords.ts`, `components/CircularDetail.tsx` (5.1), `components/LinksView.tsx` (labels from `shown_type` for customers).

Behaviour: sections 4.3, 4.5 (customer links), 5.1, 5.3, 6.2 (first two rows and the changes to old endpoints), 6.3, 6.5.

Tests (new `backend/app/tests/test_claims_view.py`):
- anonymous and bank user see only shown points; placeholders carry section, page and state only; superuser `?all=1` sees checks.
- customer JSON has none of these keys anywhere: `structured_payload`, `raw_model_response`, `model_name`, `fingerprint`, `checks`, `evidence`, `page_text_sha`, `reads`.
- `/obligations` and `/relationships` hide non-shown rows for non-superusers; a waiting change-the-law link appears to a customer as REFERENCES, to an admin as AMENDS.
- compliance: a shown obligation of an `AWAITING_REVIEW` circular can be added to a register; a hidden one gets "This requirement is waiting for a check."
- `POST /publish` with `PUBLISHED_HUMAN_REVIEWED` gives 400.
- backfill on a test database: dry run writes nothing; `--apply` builds claims; a second `--apply` changes nothing; an unreviewed AMENDS link goes back to `PENDING_REVIEW`.

Done when:
- the two new test files pass; full pytest has no new failures; `npm run build` and `npm run lint` pass.
- `.venv\Scripts\python.exe backend\scripts\backfill_claims.py` prints one plain line per circular; then `--apply` on `data/regwatch.db` (make a copy first: `data/regwatch.before-claims.db`).
- Browser, desktop and 375 px, signed out, on a backfilled circular: summary placeholder "did not pass our checks" with a working page link; requirements show only passed ones with "Checked against page N"; "Showing X of Y points" is right; no technical text anywhere; no sideways scroll.
- Browser, as admin: "Ask for review" on a shown requirement hides it at once on this tab and, within 5 s with no click, on a second tab signed out on the same circular; the "Showing X of Y" line updates on both.
- Run analysis (free tier, one English live circular, one call): the page says "Analysing ...", then redraws by itself with v3 points; a point still checking shows the "still being checked, about N minutes" line and turns into a shown point by itself (English pages have no reading checks, so this is quick).

### Chunk 3: the review screen

Files: `claims/router.py` (review list, counts, approve, fix, reject, ask-review), `claims/decide.py` (all actions, 409 rule, audit events, re-route, sync rows, document status in one commit), `relationships/router.py::review_relationship` (delegate to `decide`); frontend new `components/ClaimReview.tsx`, `app/admin/page.tsx` (tab `checks`, label "Points to check", `?tab=checks&point=<id>` opens that point), `claimsStore.ts` (queue, counts, `decide`, preloading), `CircularDetail.tsx` (admin state line, Review link), `AdminLinksPanel.tsx` (decisions go through `claimsStore.decide` so both screens agree).

Behaviour: sections 5.2 and 6.2 (review rows).

Notes from chunk 1 (must handle here):
- A new live circular that lands in `AWAITING_REVIEW` sends no "new circular" alert today. When a decision moves a circular that was never announced out of `AWAITING_REVIEW`, `decide` must call `_announce_circular` once (never for circulars whose status before analysis was `EXTRACTED`).
- Carry-over matches on the fingerprint of the model's original output. "Fix" must keep `fingerprint` unchanged (store edits in `fields`, old values in `original_fields`) so a fixed point carries over to the next run.
- Built in chunk 1: a decided claim is never re-routed; change-the-law link rows stay non-VERIFIED until a person confirms; `force_human_review` sends every would-be-shown point to `REQUIRED`.

Tests (new `backend/app/tests/test_claim_review.py`):
- approve, fix, reject, ask-review: status, `reviewed_by`, `reviewed_at`, audit event, obligation/link row sync, document status (last `REQUIRED` point decided → `PUBLISHED_HUMAN_REVIEWED`).
- approving a change-the-law link makes it `VERIFIED` with the claimed type, and the target's in-force status changes (`relationships/status.py::bulk_in_force`).
- fix with a failing check and no `confirm_checked` → 400 with plain messages; with it → `FIXED`, `original_fields` kept, fields written to the obligation.
- deciding twice → 409 with the current claim; non-superuser → 403; a bank user cannot see the queue.
- the old link review endpoint and the claim endpoint give the same end state.
- queue order: REQUIRED high-stakes first, then soonest deadline.

Done when:
- new tests pass; full pytest has no new failures; build and lint pass.
- Browser, desktop: open "Points to check"; A, F, R, J, K, ?, Esc, Ctrl+Enter all work; after A the next point and its highlighted page show at once (no spinner); the tab badge drops at once; the circular page open in a second tab shows the point within a second (broadcast) and its "Showing X of Y" line updates; a link approval changes the in-force badge on the target circular's page without a reload.
- Two admins (two browsers): both open the same point; the second gets "Someone else already decided this point." and moves on.
- 375 px: one column, sticky 44 px buttons, page image opens below and closes, no sideways scroll; the fix form is usable with the on-screen keyboard.
- Turn the network off in devtools, press A: the point comes back with "Could not save; try again."

### Chunk 4: Bangla quoted-sentence checks

Files: `claims/reading.py` (crop, batch call, `same_reading`, tie-break, whole-page fallback), new `claims/reading_jobs.py`, `extraction/vision.py` (a small helper to send several images in one call, reusing key rotation, gates and quota marks; no change to page reading), `extraction/vision_jobs.py` and `backend/scripts/read_pages.py` (call `process_pending_quote_checks` first in each batch), the page-correction flow (6.4 third bullet), `analysis/auto.py::reading_status` (paused states cover quote checks), `ClaimReview.tsx` ("Second reading said", "Fix the page reading").

Behaviour: section 7 and the 6.4 hooks.

Tests (new `backend/app/tests/test_quote_reading.py`, with `httpx.MockTransport` fakes, no network):
- same reading → `CLEAN`; claim goes `CHECKING` → `PASSED` and the document status is recomputed.
- a number differs but the text layer confirms ours → `CLEAN`.
- a dropped "না" → tie-break; third agrees with ours → `CLEAN`; second and third agree against ours → `MISREAD` with the third reading stored; all differ → `UNCLEAR`.
- `[illegible]` → not same; edit share just under and just over 3%.
- busy and quota replies → stays `WAITING`, `attempts` unchanged; 3 real failures → `UNCLEAR`.
- text-layer page and human-corrected page → `NOT_NEEDED`, no call made.
- one call per page for up to 12 crops (count calls on the fake).
- page correction re-routes claims on that page (found → re-checked; gone → `NOT_SHOWN`).
- no Gemini call is ever made inside a web request (patch the sender to fail when called from the router).

Done when:
- new tests pass; full pytest has no new failures; build and lint pass.
- The page reader runs the new code: restart it (`schtasks /End /TN RegWatchPageReader` then `schtasks /Run /TN RegWatchPageReader`; if Windows refuses, ask the user to run those two lines) and `.venv\Scripts\python.exe backend\scripts\read_pages.py --status` still prints page counts.
- Live, free tier, one Bangla circular already in the library with all pages read: run its analysis as admin. The circular page shows "N points are still being checked against the page image, about M minutes left" and fills in by itself with no click; `data/page_reader.log` shows the quote checks; the number of reading calls is at most (image pages with quotes) × 2. Note the counts of CLEAN / MISREAD / UNCLEAR in your report.
- The same circular at 375 px: Bangla quotes render in the Bangla font, no sideways scroll.

After chunk 4, the main session (not the builder) records in `DECISIONS.md` that decision 10's page-level two-reader rule is replaced by section 7, with the thresholds marked provisional until plan step 4 scores them.

---

## 9. Decisions made in this spec

1. **Order of chunks: code checks, customer view, review screen, Bangla.** Until chunk 4 lands, quoted sentences on image-read pages wait and their points stay hidden, which is safe.
2. **"New circular" = published in the last 365 days, or the point's own date is still ahead.** The plan says archive points are hidden, not queued; the archive also holds recent circulars, so a date rule is clearer than "where it came from".
3. **Change-the-law links are shown as "Mentions X" while they wait for a person.** "This circular mentions X" is true and quoted; only the stronger "amends X" needs a person. The target's in-force status changes only after confirmation.
4. **Summary points and key changes publish on code checks alone until plan step 6 adds the meaning check.** They now carry their own quotes and pass date, number and over-claim checks; the `MEANING` slot is ready. (Product owner to confirm; see the report.)
5. **A duty-type mismatch fails the point now.** The plan sends it to the meaning check, which is not built yet; failing is the safe default.
6. **Purpose, background, detailed summary and impact are dropped from the screen.** They have no evidence; impact returns as cited lines in plan step 7.
7. **Circular details (department, number, date) are not shown from the analysis.** The header already uses the listing record, an independent source, so no check is needed.
8. **Only admins can "Ask for review".** Letting any reader hide a point would let one user remove content for everyone; a customer "report a problem" can come later.
9. **The whole-document "publish" decision is retired.** People decide point by point; the old button would publish points no one checked.
10. **The second reading uses Gemini 3.5 Flash on crops, the tie-break uses Flash-Lite on sharper crops, and crops of one page share one call.** These are the free models that already work on our keys; batching keeps within the small free Flash quota. A different-company reader is a plan step 4/6 measurement, not a guess now.
11. **Whole printed lines are compared, not the sentence alone.** Line boxes exist per line; judging the full lines is stricter and avoids cutting words.
12. **3% edit share plus exact numbers, negations and reference codes.** 06_VERDICT measured 4-7% error on whole pages; short crops should do better, and the exact-token rule catches the errors that change meaning. Tuned later on dev only.
13. **Re-analysis keeps a person's decision when the point is unchanged** (same kind, evidence and fields). Re-checking the whole circular after every re-run would bring back the backlog this plan removes.
14. **The prompt version is part of the "unchanged" fingerprint,** so v3 can run on circulars analysed with v2.
15. **Old v2 summaries and applicability lines are hidden by the backfill,** because they have no evidence; a re-run with v3 brings them back checked.
16. **Archive circulars analysed on request never send a "new circular" alert.**
