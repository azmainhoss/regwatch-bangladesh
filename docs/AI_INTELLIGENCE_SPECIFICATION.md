# AI Intelligence Specification
## Multi-Stage Regulatory Intelligence Engine & Citation Grounding

### 1. Design Principles
1. **Multi-Stage Processing:** We deliberately avoid "single mega-prompts". Breaking analysis into discrete stages guarantees schema compliance, prevents context exhaustion, and enables independent auditing of each inference step.
2. **Provider Agnostic Architecture (`BaseAIProvider`):** The engine abstracts LLM calls through a unified provider interface. Implementations support Google Gemini (`GeminiAIProvider`), OpenAI, Anthropic, or deterministic local models (`MockAIProvider`) for testing.
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

#### Stage 9: Deterministic Citation Validation
- **Input:** All claims, provisions, obligations, and relationships against stored `document_pages`.
- **Validation Rule:**
  $$\text{Coverage} = \frac{\sum \text{Verified Quotes}}{\text{Total Claims}}$$
- Evaluates exact substring matching, whitespace-normalized matching, and high-confidence fuzzy matching (>= 0.92).
- Flags any unlocated quote as `UNVERIFIED`.

#### Stage 10: Consolidated Intelligence Record & Publication Check
- Aggregates validated results, stores token usage, latency, and estimated cost.
- Sets publication status: `PUBLISHED_MACHINE_PROCESSED` (if coverage >= 95% and zero unverified claims) or `AWAITING_REVIEW`.

---

### 3. Publication State Machine & Human Review Workflow
- **`PROCESSING`**: Analysis in flight.
- **`EXTRACTION_FAILED`**: Text extraction or OCR failed.
- **`AWAITING_REVIEW`**: High-impact circular, amendment/repeal detected, or unverified claims present.
- **`PUBLISHED_MACHINE_PROCESSED`**: Deterministically passed 100% citation coverage.
- **`PUBLISHED_HUMAN_REVIEWED`**: Verified and approved by a compliance officer or regulatory research editor.
- **`CORRECTED`**: Human corrections applied to page text or obligations.
