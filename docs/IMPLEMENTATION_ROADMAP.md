# Implementation Roadmap
## RegWatch Bangladesh Platform

### Phase Overview & Milestones

| Phase | Title | Scope & Key Deliverables | Status |
|---|---|---|---|
| **Phase 0** | Workspace Audit & Planning | Workspace inspection, external source research (BB), architecture, PRD, database schema, threat model, decision log. | **COMPLETE & VERIFIED** |
| **Phase 1** | Project Foundation & Security Remediation | Modular monolith structure, SQLAlchemy 2.0 + Alembic, dual storage engine (`originals/` & `evidence/`), strict multi-tenant isolation (`get_org_membership`), JWT auth, upload validation (magic bytes, 50MB ceiling, PyMuPDF validation). | **COMPLETE & VERIFIED** |
| **Phase 2** | Bangladesh Bank Source Monitoring & Ingestion | Verified source discovery, `BaseSourceConnector`, `BangladeshBankConnector`, Imperva WAF telemetry, SHA-256 deduplication gate, document versioning, `source_discoveries` review queue, Next.js live monitoring UI. | **COMPLETE & VERIFIED** |
| **Phase 3A** | Advanced Document Extraction Engine | PyMuPDF native extraction, Tesseract OCR with English & Bengali (`ben.traineddata`) language support, legacy Bijoy-to-Unicode conversion, layout hierarchy extraction, structured table extraction (pdfplumber & ASCII grids), deterministic quality scoring (`DocumentCompletenessReport`), Gold Corpus benchmark. | **COMPLETE & VERIFIED** |
| **Phase 3B** | AI Regulatory Intelligence Engine | Multi-stage pipeline (Classification, Executive Summary, Provision Hierarchy, Mandatory Obligations, Applicability, Deadlines, Relationships, Impact), `BaseAIProvider` abstraction (Mock & Gemini), mandatory deterministic citation validation (`CitationValidator`), risk-based publication state machine, grounded research assistant with prompt injection defenses. | **COMPLETE & VERIFIED** |
| **Phase 4** | Professional & Organization Workspaces | Interactive regulatory dashboard, obligation-to-compliance register mapping, task management, audit trail, regulatory network graph explorer. | **QUEUED (Core Engine & APIs Verified)** |
| **Phase 5** | Production Hardening | Security audits, rate limiting, Docker images, automated backup policies, performance benchmarks. | **QUEUED** |
