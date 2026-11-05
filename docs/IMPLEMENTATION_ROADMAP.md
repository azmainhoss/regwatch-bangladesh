# Implementation Roadmap
## RegWatch Bangladesh Platform

### Phase Overview & Milestones

| Phase | Title | Scope & Key Deliverables | Status |
|---|---|---|---|
| **Phase 0** | Workspace Audit & Planning | Workspace inspection, external source research (BB), architecture, PRD, database schema, threat model, decision log. | **COMPLETE & VERIFIED** |
| **Phase 1** | Project Foundation & Security Remediation | Modular monolith structure, SQLAlchemy 2.0 + Alembic, dual storage engine (`originals/` & `evidence/`), strict multi-tenant isolation (`get_org_membership`), JWT auth, upload validation (magic bytes, 50MB ceiling, PyMuPDF validation). | **COMPLETE & VERIFIED** |
| **Phase 2** | Bangladesh Bank Source Monitoring & Ingestion | Verified source discovery, `BaseSourceConnector`, `BangladeshBankConnector`, Imperva WAF telemetry, SHA-256 deduplication gate, document versioning, `source_discoveries` review queue, Next.js live monitoring UI. | **COMPLETE & VERIFIED** |
| **Phase 3** | Document Extraction Engine | PyMuPDF page-by-page extraction, Tesseract OCR for scanned pages, Bangla Bijoy-to-Unicode conversion, table extraction, quality metrics. | **IN PROGRESS (Core Ingestion & Extraction Verified)** |
| **Phase 4** | AI Intelligence Engine | Multi-stage pipeline (Classification, Summary, Provisions, Obligations, Relationships, Impact, Citation Validation), human review queue. | **QUEUED** |
| **Phase 5** | Professional Workspace | Public landing, regulatory dashboard, feed filters, document reader with side-by-side original PDF, relationship explorer, grounded Q&A. | **QUEUED (Feed & PDF Stream Verified)** |
| **Phase 6** | Organization Workspace | Multi-tenant orgs, departments, RBAC, compliance registers, obligation-to-task assignment, evidence upload, review sign-offs. | **QUEUED (Multi-Tenant Core Verified)** |
| **Phase 7** | Production Hardening | Security audits, rate limiting, Docker images, automated backup policies, performance benchmarks. | **QUEUED** |
