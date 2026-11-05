# AI Intelligence Specification
## Multi-Stage Regulatory Intelligence Engine

### 1. Design Principles
1. **Multi-Stage Processing:** We deliberately avoid "single mega-prompts". Breaking analysis into discrete stages guarantees schema compliance, prevents context exhaustion, and enables independent auditing of each inference step.
2. **Provider Agnostic:** The engine abstracts LLM calls through a unified `BaseAIProvider` interface. Implementations support Google Gemini, OpenAI, Anthropic, or Local/Mock models for testing.
3. **Structured Outputs:** All stages output strictly validated Pydantic models. Unstructured free-form answers are rejected.
4. **Citation Validation Guardrail:** Any extracted obligation or relationship claim MUST include an exact string quotation and page reference. A deterministic citation validator verifies that the quotation exists on the claimed page of `document_pages`. If the excerpt cannot be verified, the claim is flagged with `CITATION_UNVERIFIED`.

---

### 2. The 7 Processing Stages

#### Stage 1: Document Classification & Metadata Verification
- **Input:** First 2 pages and last page of the document.
- **Output:** Institution, department, reference number, publication date, effective date, document type (Circular, Circular Letter, Guideline), primary language (bn, en, mixed).

#### Stage 2: Executive Summary & Context
- **Input:** Full document text (cleaned).
- **Output:**
  - Executive summary (2-3 paragraphs).
  - Regulatory objective/purpose.
  - Historical background.
  - Core changes compared to existing regime.
  - Affected operational domains (Credit, Capital Adequacy, FX, AML, IT).

#### Stage 3: Provision Segmentation
- **Input:** Page-by-page text.
- **Output:** List of discrete provisions/clauses:
  - Provision number (e.g., `Para 2(iv)`, `Section 4.1`).
  - Heading.
  - Verbatim text.
  - Page number.

#### Stage 4: Obligation Extraction
- **Input:** Extracted provisions.
- **Output:** Categorized obligations:
  - Obligation Type: `MANDATORY`, `CONDITIONAL`, `PROHIBITION`, `PERMISSION`, `RECOMMENDATION`, `REPORTING`, `RECORD_RETENTION`, `APPROVAL`, `DISCLOSURE`.
  - Plain-English requirement description.
  - Verbatim supporting text.
  - Exact page number.
  - Applicability criteria (e.g., "All Scheduled Commercial Banks", "Islamic Banks only", "AD Branches").
  - Explicit compliance deadline (or `NULL` if not specified).
  - Inferred responsible department (e.g., "Treasury", "Risk Management Unit"). Marked clearly with `is_inferred: true`.

#### Stage 5: Regulatory Relationship Discovery
- **Input:** Document title, reference number, text passages containing keywords (`amends`, `supersedes`, `repeals`, `in continuation of`, `in supersession of`, `clarification of`, `cites`).
- **Output:**
  - Relationship Type: `AMENDS`, `REPEALS`, `SUPERSEDES`, `REPLACES`, `CLARIFIES`, `REFERENCES`, `IMPLEMENTS`.
  - Target reference string (e.g., `BRPD Circular No. 04 dated 18 February 2024`).
  - Supporting excerpt from document.
  - Source page number.
  - Confidence score.

#### Stage 6: Impact Assessment
- **Input:** Summary and obligations.
- **Output:**
  - Entity-level operational impact breakdown (Core Banking, Risk Rating, Liquidity ratios, Board governance).
  - Financial impact classification (Direct capital charge, Provisioning cost, Operational expense, Neutral).

#### Stage 7: Deterministic Citation Validation
- **Input:** Generated obligations, relationships, and raw `document_pages`.
- **Validation Rule:**
  $$\text{Coverage} = \frac{\sum \text{Verified Quotes}}{\text{Total Claims}}$$
- Computes `citation_coverage_score` (0.0 to 1.0).
- If coverage < 0.85, the document publication status is held in `AWAITING_REVIEW`.
