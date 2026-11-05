# System Architecture Document
## RegWatch Bangladesh Platform

### 1. Architectural Style: Modular Monolith
The platform is designed as a **Modular Monolith** with strict domain boundaries. It avoids premature microservices complexity while maintaining clean separation of concerns, independent testability, and clear dependency graphs.

```mermaid
graph TD
    subgraph Clients
        PW["Professional Workspace (Next.js)"]
        OW["Organization Workspace (Next.js)"]
        AC["Admin Console (Next.js)"]
    end

    subgraph API Gateway / Transport
        F莊["FastAPI REST / OpenAPI"]
        AUTH["Auth & JWT Middleware"]
        TENANT["Tenant Isolation & RLS Context"]
    end

    subgraph Core Modules
        ID["Identity & Auth"]
        ORG["Organizations & Departments"]
        INST["Institutions & Departments"]
        SRC["Sources & Ingestion Engine"]
        DOC["Document Repository & Versioning"]
        EXT["Extraction Engine (PyMuPDF / OCR)"]
        AI["AI Intelligence Pipeline (Multi-stage)"]
        REL["Relationship Engine & Graph"]
        OBL["Obligations Engine"]
        COMP["Compliance Engine (Registers, Tasks, Evidence)"]
        SRCH["Search & Research Engine"]
        AUD["Audit Logger"]
    end

    subgraph Storage & Persistence
        PG[(PostgreSQL + pgvector / JSONB)]
        OBJ["Object Storage (S3 / Local Namespace)"]
        REDIS[(Redis Cache / Broker)]
    end

    PW --> F莊
    OW --> F莊
    AC --> F莊
    F莊 --> AUTH --> TENANT
    TENANT --> Core Modules
    SRC --> OBJ
    DOC --> OBJ
    DOC --> PG
    EXT --> PG
    AI --> PG
    REL --> PG
    OBL --> PG
    COMP --> PG
    AUD --> PG
    SRCH --> PG
```

---

### 2. Domain Module Boundaries

| Module | Responsibility | Dependencies |
|---|---|---|
| `identity` | User auth, password hashing, session tokens, MFA | None |
| `organizations` | Tenant orgs, memberships, roles, permissions | `identity` |
| `institutions` | Regulatory bodies (BB, NBR, BSEC) and internal depts | None |
| `sources` | Source registry, crawl configuration, crawler health | `institutions` |
| `ingestion` | Ingestion jobs, downloaders, deduplication (SHA-256) | `sources`, `institutions` |
| `documents` | Document entities, immutable versions, metadata | `institutions`, `ingestion` |
| `extraction` | Page-level text extraction, OCR, table detection | `documents` |
| `analysis` | Multi-stage AI processing, executive summary, claims | `extraction`, `documents` |
| `provisions` | Clause/provision segmentation and numbering | `documents`, `extraction` |
| `relationships`| Legal relations (AMENDS, SUPERSEDES, REPEALS, etc.) | `documents`, `provisions` |
| `obligations` | Mandatory/conditional requirements, deadlines, entities| `provisions`, `documents` |
| `compliance` | Registers, compliance items, tasks, evidence, reviews | `organizations`, `obligations`|
| `search` | Hybrid full-text (trigram) + vector similarity retrieval| `documents`, `obligations` |
| `research` | Grounded Q&A assistant with strict page citations | `search`, `documents` |
| `notifications`| Email/in-app alert delivery on publication events | `organizations`, `documents` |
| `audit` | Append-only security and regulatory audit events | All modules |

---

### 3. Traceability & Immutability Architecture
1. **Raw Document Immutability:** Once a PDF is downloaded or submitted, its SHA-256 hash is computed. The file is placed into the `originals/` object storage namespace with read-only permissions. Files are never overwritten or deleted during re-extraction or re-analysis.
2. **Page-by-Page Extraction:** Extracted text is stored in `document_pages` with explicit `page_number`, `extraction_method` (DIRECT_PDF, OCR, BIJOY_CONVERTED), confidence metrics, and bounding boxes where available.
3. **Claim Citation Model:** AI outputs do not store ungrounded text. Every obligation and relationship record links back to a `source_page_id` and specific text passage.
