# 07: Publishing with almost no human review, safely

Written 2026-11-13. Research only: no app code, database or running job was changed.
Scratch scripts and their outputs: `research/07_scratch/`.

---

## Verdict (plain words)

**Build this:** check and publish each **claim** on its own, not each whole document.
A claim is one thing the app says: one obligation, one deadline, one "this amends X", one summary line.
Every claim must pass a ladder of automatic checks. A claim that fails is **hidden** (the reader sees "not checked yet, read the original"), not sent to a person.
A person is needed only when a failed claim is both **new** and **high-stakes**: a live deadline, a must / must-not duty, or a change to which rule is in force.

**Expected share that needs a person:**

| | Today's rules (as decided) | This plan, at launch | This plan, after measured relaxing |
|---|---|---|---|
| Archive (about 4,800 circulars) | about 80-85% (about 3,900 circulars) | 0% blocking; about 300-600 claims audited once as a sample | 0% blocking; a small monthly sample |
| New circulars (about 10 a week) | about 60-90% (6-9 a week) | about 30-50% (3-5 a week), mostly "changes older law" | about 5-10% (under 1 a week) |

These plan numbers are estimates from small samples and outside studies. The build list below measures them on the locked test split before anything goes live.

**Safety level (proposed default):** at most **1 wrong claim in 100** published claims overall, and at most **1 in 200** for high-stakes claims, each shown with 95% confidence by a random audit.
In practice: audit 300 random published claims and find none wrong, and the overall target is proven. High-stakes claims need 600 with none wrong.
If a weekly audit pushes a claim type over its target, that type goes back to "hold" by itself.

**Free now vs paid later:** everything here runs on free tiers. A paid model mainly buys speed and a verifier from a **different** company (errors that do not repeat each other). Rough paid cost: about $3-5 a month for new circulars and about $150-400 once for the archive.

---

## 1. What sends a document to a person today

### Rules in the code (`analysis/pipeline.py`, `citations.py`, `sentences.py`, `service.py`)
A finished analysis goes to `AWAITING_REVIEW` when any of these is true:

1. **A quote's sentence IDs are unknown** (`apply_quote_ids` problems).
2. **A quote is not exact or normalized-exact on its cited page** (fuzzy, wrong page, missing).
3. **Citation coverage is under 95%, or the analysis has zero items.**
4. **A relationship is AMENDS, REPEALS, SUPERSEDES or REPLACES.**
5. **`impact_assessment.overall_impact_severity` is HIGH.**
6. **Someone forced review** (`force_human_review`).
7. **The circular was human-published before and its analysis changed** (`service.py`, `needs_re_review`).

A person can then publish only if coverage is 100% and every claim is verified (`review_and_publish_analysis`). So a person can't publish a circular with even one bad item. They can only re-run it.

### Rules that are decided but not in the code
- **Missing or unread pages.** `extraction/quality.py` computes `requires_human_review` (missing pages, failed pages, low quality), but nothing reads it. The pipeline analyses whatever text exists. 2 of the 7 circulars analysed so far ran with unread Bangla pages: zero items, so rule 3 held them, but only by luck. If the English pages had produced items, the circular would have published with its Bangla pages unread.
- **The two-reader check on Bangla pages (DECISIONS.md 10).** "Read with Flash-Lite and Flash; if the two disagree by more than 2%, a person checks the page." Only Flash-Lite reading is built.

### Rules that no longer do anything
- **Rule 5 is dead.** The v2 prompt never asks for `overall_impact_severity`, so it is always empty. None of the 9 stored analyses has it.
- **Rules 1-2 now almost never fire.** Since quotes are copied from sentence IDs, they are word for word by construction. In the 9 stored analyses, 0 quotes failed. The check is still worth keeping, but it no longer catches the errors that matter (below).

### What the current checks miss
The quote proves the sentence exists. It does not prove the claim **says what the sentence says**. Nothing checks:
- the deadline, effective date, penalty, "who must do it" or obligation type against the quote;
- numbers and rates in the English description;
- that an "AMENDS" quote really contains amending words and names the target;
- the summary, key changes, applicability and impact text (free text, no quote at all);
- whether the Bangla reading of the quoted sentence is right. The quote matches **our reading** word for word, not the paper. Readings have 4-7% character errors (06_VERDICT.md);
- missed obligations. The same circular analysed 3 times gave 5, 5 and 3 obligations, and one run dropped a REFERENCES link.

### How much of the archive each rule would catch (estimates)
Sources: the full listing (4,818 titles) and the 130-circular research sample (random 100 plus recent 30), script `07_scratch/gate_shares.py`. Bangla text in the sample is partly converter output, so the Bangla counts are lower bounds.

| Rule | Archive (random 100) | Recent (2025-26) |
|---|---|---|
| Has at least one Bangla or scanned page (needs image reading) | 83% | 76% |
| Every page is Bangla or scanned | 69% | 66% |
| Text has explicit change-the-law words (amend, repeal, supersede, in place of, সংশোধন, রহিত, বাতিল, প্রতিস্থাপ...) | 34-37% | 52-66% |
| Title has change words (all 4,818 titles) | 9.7% | 9.9% (2020s) |
| Cites another circular at all | 87% | 79% |
| Has deadline wording plus a date | 31% | 38% |
| Has penalty wording | 27% | 24% |
| Longer than 12 pages | 5% | 17% |

Local analyses (9 runs, 7 circulars, all English): 3 of the 5 circulars with items had AMENDS, REPEALS or SUPERSEDES, so rule 4 held them.

**The two-reader page rule is the biggest driver.** On the 60 Bangla pages both models read (`07_scratch/read_agreement.py`):
- pages where the two readings are within 2%: 47% by my measure (06_VERDICT.md measured 19 of 60, 32%);
- Bangla sentences read the same by both models: 42% exactly, 51% after ignoring spaces and punctuation;
- numbers found in both readings: 85%.

A Bangla circular has about 2.6 image-read pages on average. At 32-47% of pages passing, only about 5-14% of Bangla circulars would get every page through.

**Total under today's decided rules:** about 0.83 x 0.9 (Bangla circulars held for reading) + 0.17 x 0.4 (English circulars held for changing law) ≈ **80-85% of the archive, about 3,900 circulars**. At 10-15 minutes each, that is 650-1,000 hours of checking. New circulars: about 60-90% held.

---

## 2. What 2026 research and products say

**1. Two models that agree are right far more often, but not always.**
- A May 2026 study auto-accepted fields where two different-company vision models gave the same answer: over 73% of fields at first, over 85% at scale. Final word error was 0.3%.
- Its two leftover errors were the dangerous kind: both models made the **same** mistake on a faint mark, so nothing flagged it (arXiv 2605.25781).

**2. Errors repeat across models, especially within one company.**
- Models from the same maker share mistakes (Kim et al., ICML 2025).
- A July 2026 audit found high self-agreement is a weak signal. GPT-4.1 answers with 80%+ self-agreement were wrong 48% of the time on hard questions. Models from two different vendors gave the same wrong answer more often than chance (arXiv 2607.08065).
- A May 2026 paper found nine judges giving only about two votes' worth of independent signal (arXiv 2605.29800).
- **Lesson:** Flash-Lite checked by Flash is weaker than it looks. Use a checker from another family where possible, and lean on checks that don't use a model at all.

**3. Checks without a model and narrow verifiers do most of the work.**
- GUIDE (VLDB 2026 workshop) extracts rules from 120 real enterprise documents. It uses schema checks, then a model judge scoring each item, then routes only weak items to people.
- **Result:** 71.4% of rules auto-approved, 28.6% to a person, and hallucination down from 15.7% (one-pass) to 3.2%.
- The judge was validated against 300 expert labels (precision 0.94).

**4. A cheap verifier first, then the expensive one only when unsure.**
- A Sept 2026 paper on claim checking found a cheap checker matched a frontier model's accuracy, and a cascade cost about two-thirds less.
- But the cheap checker let through more unsupported claims: 23% against 14% (arXiv 2610.20634).
- **Lesson:** measure what a verifier lets through, not just its accuracy.

**5. Statistical guarantees exist, with limits.**
- Conformal risk control sets an abstain threshold so the error rate stays under a target, using a held-out calibration set.
- A June 2026 paper shows that ordinary "skip when unsure" rules miss their target by 7.5-12.5 points. It also gives a quick test: if the model's base error is above the target, a minimum share must be held, whatever you do (arXiv 2606.29054).
- **Lesson:** set thresholds on held-out data, and expect some holding unless the base error is already low.

**6. Audit a sample instead of checking everything.**
- A small random human audit gives an honest error bound (exact binomial bound, below).
- Prediction-powered inference (May-June 2026 papers and the GLIDE library) blends a few human labels with many verifier labels. You get a narrower bound with no bias, as long as the human sample is random.

**7. Image reading hides meaning errors that character-error rates miss.**
- A Sept 2026 study of vision models reading old documents found low error rates hiding "normalised" spellings, invented text and swapped names or dates (arXiv 2607.24077).
- An Amazon study (v2, Sept 2026) found general vision models **rewrite** unclear words instead of copying them. Telling the model not to correct reduced this by 30-50% (arXiv 2607.21617).
- **Lesson:** for Bangla, check the specific sentences and numbers a claim rests on.

**8. Regtech vendors still keep experts in the loop, but on suggestions, not everything.**
- Compliance.ai ("expert in the loop"), CUBE and Corlytics describe a model suggesting obligations and analysts confirming them (vendor pages, 2026).
- None publishes an error rate. A measured, published error rate would set RegWatch apart from RegAlert and the big vendors.

---

## 3. The plan

### 3.1 Four ideas that cut human review
1. **Judge claims, not documents.** One weak claim hides that claim only. The rest of the circular publishes. This keeps the golden rule ("nothing unsupported is published") and removes the all-or-nothing hold.
2. **Hide instead of hold for the archive.** Old circulars have no live deadlines. A hidden claim there costs little, because the reader still gets the original page with highlights. No person is needed.
3. **Every field must point at its evidence.** Today only the quote has sentence IDs. Add evidence IDs for the deadline, effective date, "who", penalty, and each number. Code then checks the value against those sentences.
4. **Verify only what is shown.** For Bangla, re-check the sentences that claims quote, not whole pages. Most page-level disagreement sits in text no claim uses.

### 3.2 The check ladder
Each check says what it catches. A claim publishes only if every check that applies to it passes.

**Level 0: input is complete (code, no model).**
- **Rule:** analyse only when every page has text: no PENDING_VISION or NEEDS_HUMAN_REVIEW pages, page count matches the PDF, no missing page numbers.
- **What happens otherwise:** the circular waits and retries. A person sees it only if page reading keeps failing (vision_jobs already sends a page to a person after repeated failures).
- **Catches:** analyses built on missing pages, which today slip through.

**Level 1: the Bangla reading of each quoted sentence (cheap, mostly free).**
- **Numbers check (free, no model):** for Bijoy and legacy-font pages, the PDF text layer stores digits as plain digits. On the sample, 72% (Bijoy) and 81% (other legacy) of the reading's 2+ digit numbers were also in the text layer (`07_scratch/bijoy_numbers.py`). A number found in both is confirmed by a second, unrelated source.
- **Second read:** for each quoted Bangla sentence, crop its lines (line boxes already exist) and read the crop again with a second model. Tell it to copy exactly and never correct.
- **Tie-break:** if the reads differ in a number, date, reference or negation word, or by more than a small margin, read a sharper crop a third time. Two of three must agree.
- **Otherwise:** the claim is hidden.
- **Catches:** misread numbers, dates, circular numbers and dropped "not". These are the reading errors that change meaning.
- **Replaces:** the page-level 2% rule of DECISIONS.md 10.

**Level 2: field checks in code (no model).**
- **Dates:** every date field (deadline, effective date, issue date) must appear in its evidence sentences, after normalising formats, Bangla digits, Bangla month names and "with immediate effect".
- **Numbers:** every number, rate or amount in the English description must appear in the evidence.
- **Duty type vs wording:**
  - must-not needs a negation word (not, shall not, prohibited, না, যাবে না, নিষিদ্ধ);
  - may needs a permission word (may, পারবে);
  - report needs a submit or report word (submit, report, প্রেরণ, দাখিল);
  - approval needs an approval word (অনুমোদন, approval).
  A mismatch goes to Level 3, not straight to hiding.
- **"Who must do it":** must match the circular's addressee line or a scope sentence. Use a fixed entity list (the gold spec's list).
- **Change-the-law claims (AMENDS, REPEALS, SUPERSEDES, REPLACES):** all four must hold.
  - The evidence contains an explicit change phrase from a fixed English and Bangla list.
  - The target reference is in the same evidence text.
  - The reference resolves to exactly one library circular (`relationships/linking.py` already refuses guesses).
  - The target's date is earlier than the source's.
  Otherwise the claim is downgraded to "refers to X" (REFERENCES), which is harmless and still shows the quote.
- **Circular details:** department, number and date must match the bb.org.bd listing row the file came from. The listing is a second, independent source.
- **Catches:** wrong deadlines, invented numbers, flipped duty types, "amends" guessed from similarity, wrong circular numbers.

**Level 3: an independent verifier model (one call per circular).**
- **The question:** for each claim, the verifier gets the evidence sentences (plus one sentence either side) and the claim's fields. It answers per field: supported / not supported / unclear.
- **Rule:** only "supported" on every field passes.
- **Which model:** a different model family from the extractor where possible. Free: Gemma 4 through the Gemini API (too slow for page images, but the verifier sends short text), or a free OpenRouter or SambaNova model. Fallback: a different Gemini tier with a different prompt. Paid: another vendor (an OpenAI mini model, or Sonnet from the third vendor the user named), because errors repeat less across companies.
- **Bangla claims:** the verifier compares the English description with the Bangla quote. The screen always shows the Bangla quote next to the English line.
- **Catches:** meaning errors code can't see: wrong condition, wrong scope, a duty that is really background text, an English summary that overstates the source.

**Level 4: summary and free text.**
- **Rule:** the summary, key changes and impact lines are written as short bullets. Each bullet cites sentence IDs and goes through Levels 2-3 like any claim. A bullet that fails is dropped, not shown.
- **Impact:** say only what the circular says ("applies to all scheduled banks", "deadline 31 Dec 2024"). No guessed "HIGH impact". Any severity tag is computed by code from verified facts, for example: has a deadline, applies to all banks, names a penalty.

**Level 5: missed items (recall).**
- **Rule:** code marks every sentence with duty wording (shall, must, should, may not, করতে হবে, বাধ্যতামূলক, যাবে না...) that no obligation cites. A second short call asks: "is this a duty?" New items go through the same ladder.
- **Screen:** never claim "complete". Say "N obligations found", with the full text one tap away.

**Level 6: random audit (the safety proof, below).**

### 3.3 What still needs a person, and why
Only these cases, and only for **new** circulars (archive claims are hidden instead):
1. **A failed high-stakes claim:** a deadline still in the future, a must / must-not / report duty, or a penalty. Hiding it could make a bank miss a duty, so a person decides within a day.
2. **A change to which rule is in force:** marking another circular as repealed or replaced.
   - At launch: always a person.
   - After the test split shows these claims meet the high-stakes target: automatic when all Level 2 checks and the verifier pass, and the circular says it in so many words.
   - A partial amendment never marks the target as out of force.
3. **Page reading that keeps failing** after retries (already in vision_jobs).
4. **A tripwire:** the audit finds a claim type over its target. That type goes back to "hold" until fixed and re-measured.
5. **Anyone presses "ask for review".**

### 3.4 Expected share for a person, with reasoning
- **Archive:** 0 blocking, because failed claims are hidden.
  - How much gets hidden is unknown until measured. Outside studies route 12-29% of items for a check (Double Triangle 12-14%, GUIDE 28.6%).
  - Expect **10-25% of claims hidden at first**, more on Bangla circulars.
  - A person can later fix hidden claims on the most-used master circulars, by choice, not as a blocker.
- **New circulars at launch:** about half contain change-the-law wording (52-66% of recent ones), and those go to a person at first. Add about 10-20% with a failed high-stakes claim: **about 30-50%**.
- **After relaxing:** change-the-law claims go automatic once measured safe. Then a circular needs a person only for a failed high-stakes claim after the tie-break and verifier. With 10-25% of claims failing at first and falling as rules improve, and only the high-stakes subset routed: **about 5-10% of new circulars**. That is under one a week, and under an hour of founder time including the audit.

### 3.5 Safety target and how it is checked
**Wrong claim** means any shown claim where any of these is true:
- the evidence does not say it;
- a field (date, who, type, number, target) is wrong;
- a Bangla quote differs from the paper in a way that changes meaning;
- a summary bullet overstates the source.
A missed obligation is counted separately as recall. It is not a wrong claim, but it is reported.

**Default targets:**
- all claims: wrong rate at most 1%;
- high-stakes claims (future deadlines, must / must-not / report duties, penalties, in-force changes): at most 0.5%.

**How to prove it (one-sided 95% exact binomial bound, `07_scratch/bounds.py`):**

| Claims audited | 0 wrong found | 1 wrong | 2 wrong | 3 wrong |
|---|---|---|---|---|
| 100 | ≤ 2.95% | ≤ 4.66% | ≤ 6.16% | ≤ 7.57% |
| 300 | ≤ 0.99% | ≤ 1.57% | ≤ 2.08% | ≤ 2.56% |
| 600 | ≤ 0.50% | ≤ 0.79% | ≤ 1.05% | ≤ 1.29% |
| 1,000 | ≤ 0.30% | ≤ 0.47% | ≤ 0.63% | ≤ 0.77% |

- **To prove 1%:** 299 claims with 0 wrong, 473 with 1 wrong, or 628 with 2 wrong.
- **To prove 0.5%:** 598 with 0 wrong, or 947 with 1 wrong.
- **What this means for the test split:**
  - 90 test circulars give roughly 700-1,000 checkable claims, which is enough to prove 1% overall if errors are rare.
  - High-stakes claims are fewer (about 3-4 per circular, so 300-350). Proving 0.5% for them needs about 100-150 more circulars.
  - Draw those from the archive as a second locked test set. There are 4,800 to choose from.
- **Live:**
  - Every week, audit a random sample of claims published that week: about 20-30, stratified so high-stakes claims are over-sampled. Each takes about a minute with the highlighted page image.
  - Keep a rolling bound. If the bound for a claim type goes over its target, that type is held automatically.
  - Prediction-powered inference can narrow the bound by also using the verifier's labels on all claims. The human sample must stay random.
- **Never report numbers from data used for tuning.** Every human decision and audit result goes into the dev pool, never into a test set.

### 3.6 Rolling it out safely
1. **Gold first.** Build the dev 40 and test 90 analysis gold as already planned (`E:\regwatch-research\gold\analysis\` is still empty). Add one label per gold item: high-stakes or not.
2. **Shadow mode on dev.** Run the extractor and every check. Publish nothing. Measure on dev:
   - share of claims hidden;
   - share of wrong claims each level catches;
   - wrong claims that get through.
3. **Error injection on dev.** Take correct claims and break them on purpose: shift a date, drop a "not", swap AMENDS for REFERENCES, change a number, swap the entity. This measures each check's catch rate without needing new gold, and shows which check is weak.
4. **Tune on dev only:** the trigger lists, tie-break margins, verifier prompt and thresholds. Use autoresearch, per DECISIONS.md's rules.
5. **Score once on test.** For each claim type, report the wrong-claim bound. Switch on auto-publish only for types under target, in this order:
   1. circular details;
   2. "refers to" links;
   3. obligations without deadlines;
   4. deadlines;
   5. change-the-law claims;
   6. in-force changes.
6. **Archive run** after the test verdict. Failed claims are hidden. Then audit 300 random published archive claims (about 5 hours) to confirm the bound on the real archive mix.
7. **Live** with the weekly audit and the tripwire. Any change of model or prompt means a fresh test run before it goes live. Keep a second locked test set for this; once used for a decision, it joins dev.

### 3.7 Decisions to revisit (with reasons)
- **DECISIONS.md 10, "two readings within 2% per page, else a person".** Replace it with Level 1 (check quoted sentences and numbers only).
  - The page rule would send about half to two-thirds of Bangla pages to a person: about 7,500-10,000 archive pages.
  - Most of those pages' differences are in text no claim uses.
  - It also isn't built yet, so nothing is lost.
- **The pipeline's "any AMENDS / REPEALS / SUPERSEDES → person" rule.** Replace it with the Level 2 change-the-law checks plus the verifier. Keep a person only for in-force changes until the test split proves them.
- **The HIGH-impact rule.** Remove it (it is dead code), or replace it with a code-computed tag from verified facts.
- **Whole-document publication status.** Add per-claim status: shown, hidden, or waiting for a person. Let a reviewer approve or fix one claim. Today a person can't publish a circular unless every item is already verified.
- **Golden-rule wording for Bangla (the project's rules file).** "Quotes must appear word for word on the cited page" is met against our reading, not the paper. Suggested wording: "...word for word in our reading of the page, and that sentence's reading was confirmed by an independent second read." The page image highlight stays.
- **DECISIONS.md 8 (free first) and 12 (paid at the end):** no change. This plan works on free tiers.

### 3.8 Free now vs paid later
**Free now:**
- Level 0, Level 2, Level 5's sentence marking and the audit maths: plain code.
- Level 1's Bijoy number check: plain code.
- Level 1 crop re-reads: a few small calls per Bangla circular.
- The Level 3 verifier: one short call per circular. Gemma 4 or another free model; quality to be measured.
- **Archive call budget:** about 4,800 x (1 extraction + 1 verifier + 1-3 re-reads) ≈ 15,000-25,000 calls. That is about 4-7 days on the 8 free keys once page reading is done. Run it after the reader finishes, so it never takes the reader's quota.

**What paid changes:**
1. A verifier from another company, so errors repeat less.
2. Speed and no 503 waits.
3. Private bank uploads off the free tier (already planned).

**Rough cost** (list prices from third-party trackers, Oct-Nov 2026; check the official pages before buying):

| Item | Model | Per circular | New (about 43 a month) | Archive once (4,800) |
|---|---|---|---|---|
| Extraction | Gemini 3.5 Flash ($1.50 in / $9 out per million tokens) | about $0.05 | about $2 | about $240 (about half with batch, if 3.5 Flash has a batch rate) |
| Verifier | Flash-Lite ($0.30 / $2.50) | about $0.006 | about $0.30 | about $30 |
| Verifier, other vendor | GPT-5 mini (about $0.25 / $2) | about $0.005 | about $0.25 | about $25 |
| Verifier, other vendor | Sonnet (about $3 / $15) | about $0.04 | about $2 | about $190 |
| Crop re-reads | Flash-Lite | about $0.002 | about $0.10 | about $10 |

Assumes about 10,000 input and 4,000 output tokens per extraction, and 6,000 in and 1,500 out per verifier call.

---

## 4. Build list, by value
1. **Input-complete gate (Level 0).** Don't analyse until every page is read. It closes a real hole and is about an hour of work.
2. **Evidence IDs for every field, plus the Level 2 code checks:** dates, numbers, duty wording, change-the-law triggers with target resolution, and the listing cross-check. One prompt and schema change, then plain code. This catches most meaning errors for free.
3. **Per-claim status and "hide, don't hold".** Includes a reviewer screen to approve or fix one claim, and the high-stakes routing rule for new circulars. This is what removes the archive backlog.
4. **Gold for dev 40 and test 90 (already planned), the shadow scoring harness and error injection.** Without these, no rule can be relaxed.
5. **Level 1 for Bangla:** the Bijoy text-layer number check, crop re-reads of quoted sentences and the 2-of-3 tie-break. Replaces the page-level 2% rule.
6. **The Level 3 verifier,** one call per circular, from another family where possible. Measure what it lets through on dev.
7. **Summary and impact as cited bullets (Level 4).** Drop the model-guessed severity.
8. **Missed-duty check (Level 5).**
9. **One scored run on test.** Switch on auto-publish per claim type in the order in 3.6, and write the verdict into 06_VERDICT.md and DECISIONS.md.
10. **The weekly random audit, the tripwire and the log of human decisions** (feeds dev only).

---

## 5. What is not settled yet
- **The real hide rate and wrong-claim rate.** They need the analysis gold, which doesn't exist yet (`gold/analysis` is empty). The plan's shares are estimates.
- **Whether crop re-reads of Bangla sentences agree much more often than whole-page reads.** Expected, because short crops leave less room for drift, but not yet measured.
- **Whether a free verifier from another family (Gemma 4 or others) is fast and good enough.** It needs a dev-split run of at most a few dozen calls.
- **Measurement differences.** The page-agreement figure differs between 06_VERDICT.md (32%) and this note (47%) because the two count differences differently. Either way, about half or more of Bangla pages fail the page rule.
- **Paid prices** come from third-party trackers. Check each vendor's own pricing page before buying.
- **Data used.** The keyword counts in section 1 used body text from both dev and test circulars. They are only descriptive counts: nothing was tuned on them, and no gold was read.

---

## 6. Sources

### Outside sources (all 2026 unless marked)
- Double Triangle Annotation: two-model consensus, auto-accept and its correlated-error failures. arXiv 2605.25781, 25 May 2026. https://arxiv.org/html/2605.25781
- GUIDE: governed extraction with layered checks and selective human review (71.4% auto-approved). VLDB 2026 DASHSys workshop. https://www.vldb.org/2026/Workshops/VLDB-Workshops-2026/DASHSys/DASHSys26_34.pdf
- Confidence-gated verifier cascade for claim checking. arXiv 2610.20634, 30 Sep 2026. https://alphaxiv.org/abs/2610.20634v1
- When can conformal risk control certify LLM outputs (structured extraction). arXiv 2606.29054, 27 Jun 2026. https://arxiv.org/pdf/2606.29054
- Geometry-calibrated conformal abstention. arXiv 2604.27914, Apr 2026. https://www.alphaxiv.org/abs/2604.27914
- CGRiC, compositional risk certification for structured outputs. ICML 2026. https://icml.cc/virtual/2026/poster/64542
- When LLMs agree, are they right? Self-consistency and cross-model agreement as confidence. arXiv 2607.08065, v2 28 Jul 2026. https://www.alphaxiv.org/abs/2607.08065
- Nine judges, two effective votes: correlated errors in LLM judge panels. arXiv 2605.29800, May 2026. https://arxiv.org/pdf/2605.29800
- LLMs as a jury: cross-model consensus. arXiv 2607.10139, Jul 2026. https://www.alphaxiv.org/abs/2607.10139
- Correlated errors in large language models (background, ICML 2025). https://arxiv.org/html/2506.07962v1
- Lightweight claim verifier with uncertainty gating. arXiv 2604.11036, Apr 2026. https://arxiv.org/html/2604.11036v1
- Structured groundedness scoring with an abstain channel (GSAR). arXiv 2604.23366, Apr 2026. https://arxiv.org/html/2604.23366
- Calibrated confidence for tabular extraction (multi-format agreement). arXiv 2604.12491, Apr 2026. https://arxiv.org/html/2604.12491v1
- PRECISE: prediction-powered evaluation with few human labels. arXiv 2606.05308, Jun 2026. https://arxiv.org/html/2606.05308
- GLIDE library for prediction-powered inference. arXiv 2605.31278, May 2026. https://arxiv.org/pdf/2605.31278 and https://glide-py.readthedocs.io/en/latest/tutorials/ppi/
- When low CER is not enough: hallucinations in vision OCR. arXiv 2607.24077, v3 17 Sep 2026. https://arxiv.org/pdf/2607.24077
- Do VLMs read or rewrite? arXiv 2607.21617, v2 2 Sep 2026. https://www.alphaxiv.org/abs/2607.21617
- Regtech vendors' human-review layers (vendor-written comparison, 2026). https://www.vixio.com/blog/platforms-that-combine-ai-and-human-expertise-for-regulatory-intelligence and https://vixio.com/blog/best-ai-tools-for-regulatory-compliance
- Gemini 3.5 Flash-Lite and Flash list prices (third-party trackers, Oct-Nov 2026; official page https://ai.google.dev/gemini-api/docs/pricing). https://pricepertoken.com/pricing-page/model/google-gemini-3.5-flash-lite and https://evolink.ai/blog/gemini-3-5-flash-pricing-guide
- GPT-5 mini and Sonnet list prices (third-party comparison, Jun 2026). https://devtk.ai/en/blog/ai-api-pricing-comparison-2026

### Local measurements (this note, read-only)
- `research/07_scratch/gate_shares.py`: rule shares on the listing and the 130-circular sample.
- `research/07_scratch/read_agreement.py`: Flash-Lite vs Flash agreement on Bangla pages (pages, sentences, numbers).
- `research/07_scratch/bijoy_numbers.py`: Bijoy text-layer numbers vs image reading.
- `research/07_scratch/analyses.py` and `db_stats.py`: the 9 stored analyses and page states in `data/regwatch.db`, opened read-only.
- `research/07_scratch/bounds.py`: audit sample sizes and bounds.
