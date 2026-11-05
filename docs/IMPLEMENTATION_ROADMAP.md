# Implementation Roadmap
## RegWatch Bangladesh Platform

### Phase Overview & Milestones

| Phase | Title | Scope & Key Deliverables | Status |
|---|---|---|---|
| **Phase 0** | Workspace Audit & Planning | Workspace inspection, external source research (BB), architecture, PRD, database schema, threat model, decision log. | **COMPLETE & VERIFIED** |
| **Phase 1** | Project Foundation | Directory structure, settings, database layer (SQLAlchemy + Alembic), storage engine (originals & evidence), health endpoints, basic auth scaffolding, admin shell. | **IN PROGRESS** |
| **Phase 2** | Bangladesh Bank Connector | Verified source discovery, abstract connector, crawler, SHA-256 deduplication gate, document versioning, manual dropzone pipeline. | **QUEUED** |
| **Phase 3** | Document Extraction Engine | PyMuPDF page-by-page extraction, Tesseract OCR for scanned pages, Bangla Bijoy-to-Unicode conversion, table extraction, quality metrics. | **QUEUED** |
| **Phase 4** | AI Intelligence Engine | Multi-stage pipeline (Classification, Summary, Provisions, Obligations, Relationships, Impact, Citation Validation), human review queue. | **QUEUED** |
| **Phase 5** | Professional Workspace | Public landing, regulatory dashboard, feed filters, document reader with side-by-side original PDF, relationship explorer, grounded Q&A. | **QUEUED** |
| **Phase 6** | Organization Workspace | Multi-tenant orgs, departments, RBAC, compliance registers, obligation-to-task assignment, evidence upload, review sign-offs. | **QUEUED** |
| **Phase 7** | Production Hardening | Security audits, rate limiting, Docker images, automated backup policies, performance benchmarks. | **QUEUED** |
