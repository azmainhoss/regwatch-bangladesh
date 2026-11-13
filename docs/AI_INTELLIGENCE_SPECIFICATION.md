# AI Intelligence Specification
## Multi-Stage Regulatory Intelligence Engine & Citation Grounding

### 1. Design Principles
1. **Multi-Stage Processing:** We deliberately avoid "single mega-prompts". Breaking analysis into discrete stages guarantees schema compliance, prevents context exhaustion, and enables independent auditing of each inference step.
2. **Provider Agnostic Architecture (`BaseAIProvider`):** The engine abstracts LLM calls through a unified provider interface. Implementations support Google Gemini (`GeminiAIProvider`), OpenAI-compatible APIs, or deterministic local models (`MockAIProvider`) for testing.
3. **Structured Outputs:** All stages output strictly validated Pydantic models. Unstructured free-form answers are rejected.
4. **Mandatory Deterministic Citation Validation:** Any extracted obligation or relationship claim MUST include an exact string quotation and page reference. `CitationValidator` deterministically verifies that the quotation exists on the claimed page of `document_pages`. If the excerpt cannot be verified, the claim is flagged with `UNVERIFIED` and publication is withheld.
5. **Prompt Injection Defense:** Untrusted document text is enclosed inside inert `<regulatory_document_content>` delimiters with system-level instruction boundaries prohibiting command execution.

---

### 2. Multi-Stage Pipeline Stages (Stages 1 - 10)

#### Stage 1: Document Classification & Metadata Extraction
- **Input:** Document pages.
- **Output:** Category (Circular, Circular Letter, Guideline, Notification, Policy, Directive, Instruction, Notice, Order), institution, department, reference number, publication date, language, regulatory topic.

#### Stage 2: Executive Summary & Context
- **Output:**
  - Executive summary (concise overview).
  - Regulatory objective/purpose.
  - Historical background and statutory powers.
  - Core changes compared to existing regime.
  - Affected stakeholders and operational domains.

#### Stage 3: Provision and Clause Extraction
- **Output:** Hierarchical clause tree:
  - Provision number (e.g. `1.`, `1.1`, `1.2(a)`).
  - Heading.
  - Verbatim text.
  - Page number.
  - Parent clause relationship.

#### Stage 4: Regulatory Obligation Extraction
- **Output:** Categorized obligations:
  - Obligation Type: `MANDATORY`, `CONDITIONAL`, `PROHIBITION`, `PERMISSION`, `RECOMMENDATION`, `REPORTING`, `RECORD_RETENTION`, `APPROVAL`, `DISCLOSURE`.
  - Detailed requirement description.
  - Verbatim supporting quotation.
  - Page number and clause reference.
  - Responsible entity (e.g. Scheduled Commercial Banks, NBFIs).
  - Explicit compliance deadline (or `NULL` if not specified).
  - Required evidence and statutory sanctions.

#### Stage 5: Applicability Analysis
- **Output:** Covered institutions, universal vs specialized rules, explicit exemptions, conditional applicability rules.

#### Stage 6: Deadline and Effective-Date Extraction
- **Output:** Publication date, effective date, compliance deadline, reporting frequency, trigger events.

#### Stage 7: Regulatory Relationship Discovery
- **Input:** Document text citing earlier circulars (`amends`, `supersedes`, `repeals`, `in continuation of`).
- **Output:** Relationship type (`AMENDS`, `REPEALS`, `SUPERSEDES`, `REPLACES`, `CLARIFIES`, `REFERENCES`), target circular hint, verbatim supporting quote, page number, confidence.
- **Strict Rule:** Never infer legal amendment from semantic similarity alone! Explicit citation language is strictly required.

#### Stage 8: Business & Regulatory Impact Assessment
- **Output:** Breakdown across Banking Operations, Credit, Compliance, Risk Management, Technology, and Governance.

#### Stage 9: Deterministic Citation Validation (Phase 3.5 Hardened)
- **Input:** All claims, provisions, obligations, and relationships against stored `document_pages`.
- **Validation Rule:**
  $$\text{Coverage} = \frac{\sum \text{Verified Quotes (Exact + Normalized)}}{\text{Total Claims}}$$
- Evaluates against discrete canonical verification states:
  - `VERIFIED_EXACT`: Exact character-for-character substring match on the cited page.
  - `VERIFIED_NORMALIZED`: Match found after whitespace collapsing and case folding. Retains exact quote and notes applied normalization operations.
  - `CANDIDATE_FUZZY`: Approximate match ($\ge 0.85$). **Crucial Rule:** Treated strictly as a candidate for human review; does NOT count as a verified citation and blocks automated publication.
  - `WRONG_PAGE`: Quote exists in the document but appears on a different page than cited. Blocks automated publication.
  - `SOURCE_MISSING`: Cited page does not exist in the document.
  - `UNVERIFIED`: Quote cannot be located anywhere in the document.
  - `HUMAN_CONFIRMED`: Certified by an authorized human compliance reviewer.

#### Stage 10: Consolidated Intelligence Record & Publication Check
- Aggregates validated results, stores token usage, latency, and estimated cost.
- **Deterministic Publication Gates:**
  A document is placed in `AWAITING_REVIEW` if:
  1. Any `UNVERIFIED`, `WRONG_PAGE`, or `CANDIDATE_FUZZY` claims exist on obligations.
  2. Citation coverage score is below 95%.
  3. Circular has legal alteration semantics (`AMENDS`, `REPEALS`, `SUPERSEDES`, `REPLACES`).
  4. Overall impact assessment is `HIGH`.
  5. Document completeness report indicates missing or non-contiguous pages.
  6. `force_human_review` was requested.
- Only if all 6 publication gates pass does a document receive `PUBLISHED_MACHINE_VERIFIED`.

---

### 3. Publication State Machine & Human Review Workflow
- **`ANALYZING`**: Pipeline in flight with 5-minute timeout lock preventing duplicate processing.
- **`EXTRACTION_FAILED`**: Text extraction or OCR failed; blocks publishing directly.
- **`AWAITING_REVIEW`**: Held for human review due to legal alterations, high impact, or unverified claims.
- **`PUBLISHED_MACHINE_VERIFIED`**: Deterministically passed 100% of citation and publication gates.
- **`PUBLISHED_HUMAN_REVIEWED`**: Verified and approved by an authenticated superuser or compliance head.
- **`CORRECTED`**: Human corrections applied with full audit trail.
- **`WITHDRAWN` / `SUPERSEDED`**: Terminal or superseded states; cannot be transitioned directly to published.
