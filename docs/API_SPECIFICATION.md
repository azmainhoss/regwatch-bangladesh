# API Specification (OpenAPI / REST)
## RegWatch Bangladesh Platform

All endpoints are prefixed with `/api/v1` and follow standard HTTP response status codes.
Requests and responses use standard JSON with snake_case keys. Timestamps are formatted as ISO-8601 strings with timezone (`YYYY-MM-DDTHH:MM:SSZ`).

---

### 1. System & Health
- `GET /health` -> `{ status: "ok", version: "1.0.0", timestamp: string }`
- `GET /health/db` -> `{ status: "healthy", database: "connected", latency_ms: number }`

---

### 2. Identity & Access Management
- `POST /auth/register`
  - Body: `{ email, password, full_name, phone_number? }`
  - Response: `201 Created` with User object and tokens.
- `POST /auth/login`
  - Body: Form-encoded or JSON `{ email, password }`
  - Response: `{ access_token, token_type: "bearer", expires_in: 86400, user }`
- `GET /auth/me`
  - Headers: `Authorization: Bearer <token>`
  - Response: User details and associated organizations/roles.

---

### 3. Regulatory Institutions & Sources
- `GET /institutions` -> List of regulatory institutions (e.g. Bangladesh Bank, NBR, BSEC).
- `GET /institutions/{id}` -> Specific institution details with active departments.
- `GET /institutions/{id}/departments` -> List of departments (e.g. BRPD, DOS, FEPD, PSD).
- `GET /sources` -> List of configured crawling / manual ingestion sources.
- `GET /sources/{id}` -> Source details including access restriction status and last run.
- `POST /sources` -> Create a new source connector definition.
- `PATCH /sources/{id}` -> Toggle source active status or update polling parameters.
- `POST /sources/{id}/trigger` -> Trigger an immediate asynchronous ingestion discovery run.
- `GET /sources/runs` -> List of historical source runs with status, discovered counts, and WAF restriction details.
- `GET /sources/runs/{run_id}` -> Granular run statistics and diagnostic logs.
- `GET /sources/discoveries` -> Discovery review queue filtering by status (`DISCOVERED`, `VALIDATED`, `DUPLICATE`, `RESTRICTED`, `COMPLETED`, `REJECTED`).
- `POST /sources/discoveries/{discovery_id}/approve` -> Approve candidate and trigger ingestion pipeline.
- `POST /sources/discoveries/{discovery_id}/reject` -> Reject candidate with operator justification.

---

### 4. Document Ingestion & Management
- `POST /documents/upload` (Multipart Form, Authenticated)
  - Headers: `Authorization: Bearer <token>`
  - Constraints: Enforces magic bytes (`%PDF-`), 50MB file size ceiling, and PyMuPDF structure validation.
  - Fields: `file` (PDF), `institution_code`, `department_code?`, `reference_number?`, `title`, `publication_date`, `source_url?`
  - Behavior: Computes SHA-256, verifies duplicate status, stores in `originals/`, creates document and version records, schedules extraction job.
  - Response: `201 Created` with Document, Version, and page count.
- `GET /documents`
  - Query params: `institution_id`, `department_id`, `document_type`, `year`, `search`, `publication_status`, `page`, `page_size`
  - Response: Paginated list of regulatory documents with version info and metadata.
- `GET /documents/{id}`
  - Detailed document payload with active version, publication status, executive summary, key provisions, obligations count, and relationship links.
- `GET /documents/{id}/versions/{version_id}/pages`
  - List of pages with extracted text, OCR confidence, table presence, and bounding boxes.
- `GET /documents/{id}/versions/{version_id}/pages/{page_no}`
  - Specific page text and extraction details.
- `GET /documents/{id}/pdf`
  - Securely streams the original immutable PDF file from storage with range request support for the PDF viewer.

---

### 5. Compliance & Multi-Tenant Organization Workspace
- Headers Required: `Authorization: Bearer <token>` and `X-Organization-Id: <org_uuid>`
- Authorization: Enforced by `get_org_membership` dependency. Requests without valid membership in the targeted organization are rejected with `403 Forbidden`.
- `POST /organizations` -> Create a new organization tenant (caller assigned `ADMIN` role).
- `GET /organizations/my` -> List all organizations the authenticated user belongs to.
- `GET /compliance/registers` -> List compliance registers belonging strictly to the specified tenant.
- `POST /compliance/registers` -> Create new compliance register scoped to the tenant.
- `POST /compliance/tasks` -> Create a compliance task under a register.
- `POST /compliance/tasks/{id}/evidence` (Multipart) -> Submit task evidence file. Evidence is physically isolated at `storage/evidence/{org_id}/{task_id}/`.
- `GET /compliance/tasks/{task_id}/evidence` -> List all uploaded evidence records for the task.
- `GET /compliance/evidence/{evidence_id}/download` -> Securely download the evidence file, validating tenant ownership. Cross-tenant access returns `404 Not Found`.

---

### 5. Extraction & Processing Engine
- `POST /documents/{id}/extract`
  - Manually trigger or re-run page extraction (e.g., after upgrading OCR engine or Bangla font conversion).
- `GET /extraction/review-queue`
  - Admin endpoint listing documents with low OCR confidence or flagged extraction warnings.
- `POST /extraction/pages/{page_id}/correct`
  - Human editor override to correct garbled OCR text or missing section headers.

---

### 6. AI Intelligence & Analysis
- `POST /documents/{id}/analyze`
  - Executes the multi-stage AI analysis pipeline (Classification -> Executive Summary -> Provisions -> Obligations -> Relationships -> Citation Validation).
- `GET /documents/{id}/analysis`
  - Full structured analysis JSON with confidence scores and claim citations.
- `POST /documents/{id}/publish`
  - Transition document from `AWAITING_REVIEW` to `PUBLISHED_HUMAN_REVIEWED` or `PUBLISHED_MACHINE_PROCESSED`.

---

### 7. Regulatory Relationships & Network Graph
- `GET /documents/{id}/relationships`
  - Returns directed edges (AMENDS, SUPERSEDES, REPEALS, CLARIFIES, REFERENCES) connecting this document to earlier and later publications.
- `GET /relationships/graph`
  - Filtered sub-graph for visualization (nodes = documents, edges = relationships).

---

### 8. Compliance & Organization Workspace
- `GET /compliance/registers` -> List registers for the caller's organization.
- `POST /compliance/registers` -> Create new compliance register.
- `POST /compliance/items` -> Map an obligation to an organization's compliance item.
- `GET /compliance/items` -> List compliance items with status, assigned department, and deadlines.
- `POST /compliance/tasks` -> Create a compliance task under an item.
- `POST /compliance/tasks/{id}/evidence` (Multipart) -> Submit evidence document/file.
- `POST /compliance/tasks/{id}/review` -> Approve or reject evidence with comments.
- `GET /compliance/dashboard/summary` -> High-level compliance stats: compliant vs overdue vs pending items by department.

---

### 9. Research & Assistant (Grounding Required)
- `POST /research/query`
  - Body: `{ query: string, filter_institutions?: string[], filter_years?: number[] }`
  - Response: Grounded response with explicit `citations: [{ document_id, title, reference_number, page_number, verbatim_excerpt }]`.
