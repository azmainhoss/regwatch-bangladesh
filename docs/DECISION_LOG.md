# Architecture Decision Log (ADR)
## RegWatch Bangladesh Platform

### ADR 001: Modular Monolith vs Microservices
- **Date:** 2026-11-05
- **Status:** Accepted
- **Context:** The platform requires complex data integrity across institutions, documents, versions, pages, provisions, obligations, and organizational compliance items.
- **Decision:** Build as a Modular Monolith in Python/FastAPI with strict domain separation.
- **Rationale:** Microservices introduce distributed transactions, network latency, and operational overhead that would harm transactional consistency between document versions and obligations. Modules can be isolated or extracted later if specific services (like OCR workers) require independent scaling.

---

### ADR 002: Dual Ingestion Architecture (Automated + Manual Dropzone)
- **Date:** 2026-11-05
- **Status:** Accepted
- **Context:** Live testing against `bb.org.bd` confirmed an active Imperva/TSPD bot challenge. Our security and compliance guidelines strictly forbid circumventing CAPTCHAs or anti-bot protections.
- **Decision:** Build a dual ingestion architecture:
  1. An automated connector interface that runs with polite backoffs in authorized/whitelisted environments.
  2. A first-class Admin/API/Folder Manual Dropzone and batch ingestion engine that accepts verified official PDFs directly, computing SHA-256 hashes, deduplicating, and running identical extraction and AI pipelines.
- **Rationale:** Ensures 100% operational availability without violating anti-bot guidelines or creating brittle scrapers.

---

### ADR 003: Page-Level Invariant & Traceability
- **Date:** 2026-11-05
- **Status:** Accepted
- **Context:** Legal and banking compliance requires that any regulatory assertion cite the exact page and paragraph of the official circular.
- **Decision:** Store extracted text strictly page-by-page in `document_pages`. Every extracted provision, obligation, and relationship links back to a `page_id`. AI extraction must include verbatim quotes that pass deterministic validation against the stored page text.
- **Rationale:** Prevents hallucinated compliance claims and provides banking audit teams with ironclad proof.

---

### ADR 004: Dual-Dialect Database Compatibility (PostgreSQL + SQLite)
- **Date:** 2026-11-05
- **Status:** Accepted
- **Context:** Production environments require PostgreSQL 16 with `pgvector` and JSONB, while local developers and quick test runners benefit from zero-dependency lightweight SQLite execution.
- **Decision:** Implement SQLAlchemy 2.0 models using dialect-agnostic column types (e.g. JSON/JSONB abstraction, UUID string/native UUID abstraction, GUID type) that seamlessly run on both SQLite and PostgreSQL without code alteration.
- **Rationale:** Enables instant local testing and CI/CD test runs while preserving enterprise PostgreSQL capabilities in production.

---

### ADR 005: Bangla Font & Encoding Handling
- **Date:** 2026-11-05
- **Status:** Accepted
- **Context:** Older Bangladesh Bank circulars (pre-2015 and some scanned recent circulars) use legacy ANSI/Bijoy encoding (e.g. SutonnyMJ font) where characters appear garbled in standard UTF-8 readers.
- **Decision:** Include `bijoy2unicode` conversion and Tesseract OCR with Bangla (`ben`) and English (`eng`) language models. The extraction pipeline automatically detects ANSI byte patterns and normalizes them to Unicode UTF-8.
- **Rationale:** Ensures historical circulars are fully searchable and analyzable.

---

### ADR 006: Strict Server-Side Multi-Tenant Isolation
- **Date:** 2026-11-05
- **Status:** Accepted
- **Context:** Phase 1 audit revealed that compliance registers, tasks, and audit evidence lacked server-side authorization checks, making customer workspaces vulnerable to cross-tenant IDOR attacks.
- **Decision:** Implement `get_org_membership` FastAPI dependency enforcing active membership and role validation on every organization-scoped request. Customer audit evidence files are physically isolated at `storage/evidence/{org_id}/{task_id}/` with path-traversal prevention. Public circulars remain immutable platform-wide in `storage/originals/`.
- **Rationale:** Banking regulations demand strict tenant boundaries; no organization may inspect or mutate another organization's compliance evidence or register items under any circumstance.

---

### ADR 007: Anti-Bot Telemetry and Human-in-the-Loop Discovery Review
- **Date:** 2026-11-05
- **Status:** Accepted
- **Context:** Bangladesh Bank protects its portal with Imperva WAF / TSPD JavaScript challenges. Scraping or bypassing CAPTCHAs violates ethical standards, terms of service, and system guidelines.
- **Decision:** Detect Imperva TSPD signatures (`bobcmn`, "What code is in the image?", support ID extraction), Cloudflare challenges, and rate limits deterministically. Mark the run as `RESTRICTED`, log diagnostics without bypassing, and record discovered items into a `source_discoveries` review queue. Operators can review candidate links, approve and trigger automated ingestion, or upload files directly.
- **Rationale:** Ensures complete legal and ethical compliance while providing operators with full visibility into source accessibility and candidate publications.

---

### ADR 008: Layout-Aware Clause Hierarchy & Dual Table Extraction
- **Date:** 2026-11-05
- **Status:** Accepted
- **Context:** Central bank circulars present critical financial data (provisioning schedules, CAR ratios) in tables and structure obligations across nested numbered clauses (`1.`, `1.1`, `1.2(a)`). Flattening these into unformatted prose destroys regulatory meaning.
- **Decision:** Implement `LayoutAwareExtractor` to preserve clause-subclause trees and `TableExtractor` with dual strategies: vector line grid extraction (pdfplumber) and ASCII text-aligned rule grid parsing.
- **Rationale:** Preserves financial thresholds, percentages, and clause hierarchies for precise compliance mapping.

---

### ADR 009: Mandatory Deterministic Citation Validation
- **Date:** 2026-11-05
- **Status:** Accepted
- **Context:** LLMs are prone to hallucinating or subtly misquoting regulatory text, creating catastrophic legal liability in banking compliance.
- **Decision:** Make Stage 9 (Citation Validation) a non-negotiable deterministic gate. Every generated claim, provision, obligation, and relationship quotation is verified against the stored page text via exact, normalized, and high-confidence fuzzy matching. Any unverified quote blocks automated publication and flags the document for human review.
- **Rationale:** Financial compliance cannot rely on self-reported LLM confidence; only cryptographic and verbatim page grounding guarantees evidentiary integrity.

---

### ADR 010: Idempotent Migration Chain & Clean Database Baseline
- **Date:** 2026-11-05
- **Status:** Accepted
- **Context:** Fresh database initialization previously failed during `alembic upgrade head` because the initial migration `29119fb58419` was an empty stub (`pass`), causing subsequent migrations that altered tables (`982a64deb81e` and `0755184b9d4f`) to fail on clean installations.
- **Decision:** Initialize all baseline declarative tables via `Base.metadata.create_all(bind)` in `29119fb58419`, and inspect existing schema columns dynamically (`insp.get_columns(...)`) before issuing column additions or table creations in subsequent revisions.
- **Rationale:** Guarantees that any developer, CI test pipeline, or fresh production deployment can run `alembic upgrade head` from a zero-byte database to the latest schema without errors, while maintaining full idempotency on existing populated databases.

---

### ADR 011: Discrete Citation Verification States & Strict Publication Gates
- **Date:** 2026-11-05
- **Status:** Accepted
- **Context:** Audit in Phase 3.5 revealed that high-confidence fuzzy matches ($\ge 0.85$) were previously treated as verified (`is_verified = True`), potentially allowing subtle hallucinations, paraphrasing, or altered regulatory provisions to pass as verified law. Furthermore, quotes appearing on pages other than the cited page were not flagged with page misattribution.
- **Decision:** 
  1. Introduce discrete citation verification states: `VERIFIED_EXACT`, `VERIFIED_NORMALIZED`, `CANDIDATE_FUZZY`, `WRONG_PAGE`, `SOURCE_MISSING`, `UNVERIFIED`, and `HUMAN_CONFIRMED`.
  2. Classified quotes with fuzzy similarity ($\ge 0.85$) are strictly marked as `CANDIDATE_FUZZY` with `is_verified = False` and require human confirmation.
  3. Detect quotes appearing on different pages of the same document and flag them as `WRONG_PAGE`.
  4. Enforce strict deterministic publication gates: automated publication is blocked if any unverified quote, wrong page citation, or candidate fuzzy citation exists on obligations, or if the document introduces legal alterations (`AMENDS`, `REPEALS`, `SUPERSEDES`, `REPLACES`) or high regulatory impact.
- **Rationale:** Regulatory compliance in banking cannot tolerate paraphrasing as verified quotation. A candidate fuzzy match is a hypothesis requiring human verification. This eliminates legal exposure and ensures strict institutional provenance.

