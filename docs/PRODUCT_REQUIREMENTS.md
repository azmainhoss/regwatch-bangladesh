# Product Requirements Document (PRD)
## Bangladesh Regulatory Intelligence & Compliance SaaS (RegWatch Bangladesh)

### 1. Executive Summary
Financial institutions in Bangladesh (scheduled commercial banks, non-bank financial institutions [NBFIs], payment system operators [PSOs], and microfinance institutions) operate under an intensive regulatory regime led by Bangladesh Bank (the central bank). Regulatory instructions are issued in the form of Master Circulars, Circulars, Circular Letters, Guidelines, and Operating Directives across multiple departments (Banking Regulation and Policy Department [BRPD], Department of Off-site Supervision [DOS], Department of Banking Inspection [DBI], Foreign Exchange Policy Department [FEPD], Payment Systems Department [PSD], Sustainable Finance Department [SFD], and others).

Currently, compliance and legal teams must:
- Manually check websites daily.
- Manually interpret cross-referencing circulars that modify, supersede, or clarify earlier instructions going back decades.
- Manually track deadlines, reporting requirements, and compliance obligations across multiple internal departments.
- Risk punitive sanctions, financial fines, and supervisory ratings downgrades under the Bank Company Act, 1991 (amended 2023) due to missed circular amendments.

**RegWatch Bangladesh** solves this by providing:
1. Automated discovery and immutable preservation of official regulatory publications.
2. Page-level extraction supporting bilingual (Bangla and English) text and tabular schedules.
3. Multi-stage AI intelligence extracting executive summaries, key provisions, specific obligations, affected entities, and deadlines.
4. Deterministic and AI-assisted relationship graph tracking amendments, supersessions, repeals, and cross-references.
5. Dual-workspace product model:
   - **Professional Workspace**: For research, feed filtering, comparison, and cross-circular search.
   - **Organization Workspace**: For banks/NBFIs with compliance registers, obligation assignment, task management, evidence collection, and audit trails.
   - **Admin Console**: For regulatory editors to monitor ingestion, verify extraction, approve AI claims, and review publications.

---

### 2. Core Value Proposition & The Traceability Invariant
> **The Central Invariant:** Every regulatory insight, summary, obligation, and relationship claim MUST be grounded in and traceable to an official source document, original checksum, and specific page or provision number. No fabricated or ungrounded claims are ever published.

---

### 3. User Personas & Workspaces

#### Persona 1: Chief Compliance Officer (CCO) / Head of Regulatory Affairs
- **Needs:** Comprehensive oversight of upcoming deadlines, open compliance obligations across bank divisions (Credit, Treasury, AML, IT, Operations), board-level compliance reports.
- **Primary Workspace:** Organization Workspace (Compliance Registers, Dashboards, Task Sign-offs).

#### Persona 2: Compliance Officer / Regulatory Analyst
- **Needs:** Instant notification when BRPD/DOS/FEPD issues a circular, side-by-side comparison with superseded circulars, extracting action items and drafting task assignments.
- **Primary Workspace:** Professional Workspace & Organization Workspace.

#### Persona 3: Legal Counsel / Banking Law Practitioner
- **Needs:** Historical trace of regulatory instruments, finding the exact wording of an amended clause, exploring legal relationship chains.
- **Primary Workspace:** Professional Workspace (Relationship Explorer, Research Assistant).

#### Persona 4: Platform Regulatory Editor / Admin
- **Needs:** Monitoring ingestion runs, checking OCR confidence, correcting extracted metadata, reviewing AI-extracted obligations before public release.
- **Primary Workspace:** Admin Console.

---

### 4. Functional Scope by Release Phase
- **Initial Release:** Bangladesh Bank (scheduled banks, NBFIs, foreign exchange dealers, payment systems).
- **Subsequent Expansion:** National Board of Revenue (NBR), Bangladesh Securities and Exchange Commission (BSEC), Insurance Development and Regulatory Authority (IDRA), Financial Reporting Council (FRC).
