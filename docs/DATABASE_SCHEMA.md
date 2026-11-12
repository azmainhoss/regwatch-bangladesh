# Database Schema Specification
## Relational Schema for RegWatch Bangladesh

### 1. Architectural Design Principles
- **Primary Keys:** UUID v4 across all tables for distributed generation, tamper-resistance, and secure client-side references.
- **Audit Columns:** Every table includes `created_at` (TIMESTAMPTZ) and `updated_at` (TIMESTAMPTZ).
- **Immutability:** `document_versions`, `document_pages`, `analysis_runs`, `analysis_claims`, `audit_events`, and `task_events` are append-only.
- **Tenant Isolation:** All compliance, task, and evidence tables include an `organization_id` column with foreign key constraints, composite indexes `(organization_id, id)`, and tenant-filtering guards.
- **Bilingual Support:** Text columns use UTF-8 encoding. Bangla text is stored natively in Unicode.

---

### 2. Entity Groups & Table Definitions

#### 2.1 Regulatory Foundation
1. **`institutions`**
   - `id`: UUID (PK)
   - `code`: VARCHAR(32) UNIQUE (e.g. `BB`, `NBR`, `BSEC`, `IDRA`)
   - `name`: VARCHAR(255) NOT NULL
   - `name_bn`: VARCHAR(255)
   - `website_url`: VARCHAR(512)
   - `is_active`: BOOLEAN DEFAULT true
   - `created_at`, `updated_at`

2. **`institution_departments`**
   - `id`: UUID (PK)
   - `institution_id`: UUID (FK -> institutions.id)
   - `code`: VARCHAR(64) NOT NULL (e.g. `BRPD`, `DOS`, `DBI`, `FEPD`, `PSD`, `SFD`)
   - `name`: VARCHAR(255) NOT NULL
   - `name_bn`: VARCHAR(255)
   - `created_at`, `updated_at`
   - Unique constraint: `(institution_id, code)`

3. **`sources`**
   - `id`: UUID (PK)
   - `institution_id`: UUID (FK -> institutions.id)
   - `department_id`: UUID (FK -> institution_departments.id, NULLABLE)
   - `name`: VARCHAR(255) NOT NULL
   - `source_type`: VARCHAR(64) NOT NULL (`WEB_CRAWLER`, `MANUAL_UPLOAD`, `API_FEED`)
   - `monitoring_method`: VARCHAR(64) DEFAULT 'WEB_CRAWLER'
   - `base_url`: VARCHAR(512)
   - `polling_frequency_minutes`: INTEGER DEFAULT 60
   - `config`: JSONB (selector paths, rate limits, headers, pagination rules)
   - `is_active`: BOOLEAN DEFAULT true
   - `last_checked_at`: TIMESTAMPTZ
   - `last_attempted_run_at`: TIMESTAMPTZ
   - `last_successful_run_at`: TIMESTAMPTZ
   - `last_discovered_publication_at`: TIMESTAMPTZ
   - `last_error`: TEXT
   - `access_restriction_status`: VARCHAR(32) DEFAULT 'ACCESSIBLE'
   - `created_at`, `updated_at`

4. **`source_runs`**
   - `id`: UUID (PK)
   - `source_id`: UUID (FK -> sources.id)
   - `run_type`: VARCHAR(32) (`SCHEDULED`, `MANUAL_TRIGGER`, `DIRECT_UPLOAD`)
   - `status`: VARCHAR(32) (`STARTED`, `COMPLETED`, `FAILED`, `CANCELLED`, `RESTRICTED`)
   - `pages_inspected`: INTEGER DEFAULT 0
   - `candidate_links_discovered`: INTEGER DEFAULT 0
   - `valid_documents_discovered`: INTEGER DEFAULT 0
   - `downloads_attempted`: INTEGER DEFAULT 0
   - `downloads_successful`: INTEGER DEFAULT 0
   - `duplicate_count`: INTEGER DEFAULT 0
   - `discovered_count`: INTEGER DEFAULT 0
   - `downloaded_count`: INTEGER DEFAULT 0
   - `access_restricted`: BOOLEAN DEFAULT false
   - `access_restriction_details`: JSONB
   - `retry_count`: INTEGER DEFAULT 0
   - `error_count`: INTEGER DEFAULT 0
   - `error_log`: TEXT
   - `started_at`, `completed_at`

5. **`source_discoveries`**
   - `id`: UUID (PK)
   - `source_run_id`: UUID (FK -> source_runs.id)
   - `document_id`: UUID (FK -> documents.id, NULLABLE)
   - `source_url`: VARCHAR(1024) NOT NULL
   - `file_url`: VARCHAR(1024)
   - `title`: TEXT
   - `department_code`: VARCHAR(64)
   - `reference_number`: VARCHAR(128)
   - `publication_date`: DATE
   - `discovered_metadata`: JSONB
   - `rejection_reason`: TEXT
   - `status`: VARCHAR(32) (`DISCOVERED`, `VALIDATED`, `DUPLICATE`, `RESTRICTED`, `COMPLETED`, `REJECTED`)
   - `created_at`

6. **`documents`**
   - `id`: UUID (PK)
   - `institution_id`: UUID (FK -> institutions.id)
   - `department_id`: UUID (FK -> institution_departments.id, NULLABLE)
   - `reference_number`: VARCHAR(128) (e.g. `BRPD Circular No. 15/2024`)
   - `title`: TEXT NOT NULL
   - `title_bn`: TEXT
   - `document_type`: VARCHAR(64) NOT NULL (`CIRCULAR`, `CIRCULAR_LETTER`, `GUIDELINE`, `NOTIFICATION`, `POLICY`, `ORDER`)
   - `publication_date`: DATE NOT NULL
   - `effective_date`: DATE
   - `source_url`: VARCHAR(1024)
   - `current_version_id`: UUID (FK -> document_versions.id, NULLABLE initially)
   - `publication_status`: VARCHAR(64) NOT NULL (`DISCOVERED`, `EXTRACTED`, `ANALYZING`, `AWAITING_REVIEW`, `PUBLISHED_MACHINE_PROCESSED`, `PUBLISHED_HUMAN_REVIEWED`, `SUPERSEDED`, `WITHDRAWN`)
   - `created_at`, `updated_at`

7. **`document_versions`**
   - `id`: UUID (PK)
   - `document_id`: UUID (FK -> documents.id)
   - `version_number`: INTEGER NOT NULL DEFAULT 1
   - `file_sha256`: VARCHAR(64) NOT NULL
   - `file_size_bytes`: BIGINT NOT NULL
   - `file_mime_type`: VARCHAR(64) DEFAULT 'application/pdf'
   - `storage_path`: VARCHAR(512) NOT NULL
   - `page_count`: INTEGER NOT NULL DEFAULT 0
   - `language`: VARCHAR(16) DEFAULT 'en' (`en`, `bn`, `mixed`)
   - `is_scanned`: BOOLEAN DEFAULT false
   - `created_at`
   - Unique constraint: `(document_id, version_number)`

8. **`document_pages`**
   - `id`: UUID (PK)
   - `document_version_id`: UUID (FK -> document_versions.id)
   - `page_number`: INTEGER NOT NULL
   - `raw_text`: TEXT NOT NULL
   - `cleaned_text`: TEXT
   - `extraction_method`: VARCHAR(32) NOT NULL (`TEXT_LAYER`, `GEMINI_VISION`, `MANUAL_SUBSCRIPTION_READING`, `HUMAN_CORRECTED`)
   - `quality_status`: `SUCCESS_NATIVE`, `SUCCESS_VISION`, `SUCCESS_VISION_MANUAL`, `PENDING_VISION`, `NEEDS_HUMAN_REVIEW`
   - `line_boxes`: JSON, one `{text, box_2d: [ymin, xmin, ymax, xmax]}` per line on a 0-1000 page scale
   - `vision_attempts`, `vision_error`: failed page-image reading jobs on this page
   - `ocr_confidence`: FLOAT
   - `has_tables`: BOOLEAN DEFAULT false
   - `extracted_tables`: JSONB
   - `page_image_path`: VARCHAR(512)
   - `created_at`
   - Unique constraint: `(document_version_id, page_number)`

9. **`provisions`**
   - `id`: UUID (PK)
   - `document_version_id`: UUID (FK -> document_versions.id)
   - `page_id`: UUID (FK -> document_pages.id)
   - `provision_number`: VARCHAR(64) (e.g. `Section 3.1`, `Clause 5(b)`)
   - `heading`: TEXT
   - `verbatim_text`: TEXT NOT NULL
   - `parent_provision_id`: UUID (FK -> provisions.id, NULLABLE)
   - `order_index`: INTEGER NOT NULL
   - `created_at`

10. **`document_relationships`**
    - `id`: UUID (PK)
    - `source_document_id`: UUID (FK -> documents.id)
    - `target_document_id`: UUID (FK -> documents.id, NULLABLE if target not yet in library)
    - `target_reference_hint`: VARCHAR(255) (e.g. `BRPD Circular No. 04/2019`)
    - `relationship_type`: VARCHAR(32) NOT NULL (`AMENDS`, `REPEALS`, `SUPERSEDES`, `REPLACES`, `CLARIFIES`, `REFERENCES`, `IMPLEMENTS`, `RELATED_TO`)
    - `source_provision_id`: UUID (FK -> provisions.id, NULLABLE)
    - `source_page_id`: UUID (FK -> document_pages.id, NULLABLE)
    - `supporting_quote`: TEXT NOT NULL
    - `confidence`: FLOAT NOT NULL DEFAULT 1.0
    - `detection_method`: VARCHAR(32) NOT NULL (`DETERMINISTIC_REGEX`, `AI_INFERRED`, `MANUAL_ENTRY`)
    - `verification_status`: VARCHAR(32) NOT NULL (`PENDING_REVIEW`, `VERIFIED`, `REJECTED`)
    - `reviewed_by`: UUID (FK -> users.id, NULLABLE)
    - `reviewed_at`: TIMESTAMPTZ
    - `created_at`

11. **`obligations`**
    - `id`: UUID (PK)
    - `document_version_id`: UUID (FK -> document_versions.id)
    - `provision_id`: UUID (FK -> provisions.id, NULLABLE)
    - `page_id`: UUID (FK -> document_pages.id)
    - `obligation_type`: VARCHAR(32) NOT NULL (`MANDATORY`, `CONDITIONAL`, `PROHIBITION`, `PERMISSION`, `RECOMMENDATION`, `REPORTING`, `RECORD_RETENTION`, `APPROVAL`, `DISCLOSURE`)
    - `title`: TEXT NOT NULL
    - `requirement_description`: TEXT NOT NULL
    - `supporting_text`: TEXT NOT NULL
    - `applicability_summary`: TEXT NOT NULL
    - `explicit_deadline`: DATE
    - `deadline_description`: TEXT
    - `frequency`: VARCHAR(32) (`ONE_TIME`, `DAILY`, `WEEKLY`, `MONTHLY`, `QUARTERLY`, `BI_ANNUAL`, `ANNUAL`, `EVENT_DRIVEN`)
    - `inferable_responsible_dept`: VARCHAR(128)
    - `is_inferred`: BOOLEAN DEFAULT true
    - `verification_status`: VARCHAR(32) NOT NULL (`PENDING_REVIEW`, `VERIFIED`, `REJECTED`)
    - `created_at`, `updated_at`

12. **`obligation_applicability`**
    - `id`: UUID (PK)
    - `obligation_id`: UUID (FK -> obligations.id)
    - `entity_type`: VARCHAR(64) NOT NULL (`SCHEDULED_COMMERCIAL_BANK`, `ISLAMIC_BANK`, `NBFI`, `FOREIGN_BANK`, `PAYMENT_SERVICE_PROVIDER`, `MOBILE_FINANCIAL_SERVICE`)
    - `conditions`: TEXT
    - `is_exempt`: BOOLEAN DEFAULT false
    - `created_at`

13. **`document_analyses`**
    - `id`: UUID (PK)
    - `document_version_id`: UUID (FK -> document_versions.id)
    - `executive_summary`: TEXT NOT NULL
    - `purpose`: TEXT
    - `background`: TEXT
    - `key_changes`: JSONB NOT NULL
    - `impact_summary`: JSONB NOT NULL
    - `model_name`: VARCHAR(64) NOT NULL
    - `prompt_version`: VARCHAR(32) NOT NULL
    - `structured_payload`: JSONB NOT NULL
    - `citation_coverage_score`: FLOAT NOT NULL
    - `created_at`

---

#### 2.2 Identity and Organizations
14. **`users`**
    - `id`: UUID (PK)
    - `email`: VARCHAR(255) UNIQUE NOT NULL
    - `hashed_password`: VARCHAR(255) NOT NULL
    - `full_name`: VARCHAR(255) NOT NULL
    - `phone_number`: VARCHAR(32)
    - `is_active`: BOOLEAN DEFAULT true
    - `is_superuser`: BOOLEAN DEFAULT false
    - `created_at`, `updated_at`

15. **`user_profiles`**
    - `id`: UUID (PK)
    - `user_id`: UUID UNIQUE (FK -> users.id)
    - `designation`: VARCHAR(128)
    - `bio`: TEXT
    - `preferences`: JSONB
    - `created_at`, `updated_at`

16. **`organizations`**
    - `id`: UUID (PK)
    - `name`: VARCHAR(255) NOT NULL
    - `entity_type`: VARCHAR(64) NOT NULL (`COMMERCIAL_BANK`, `ISLAMIC_BANK`, `NBFI`, `LAW_FIRM`, `CONSULTING_FIRM`, `OTHER`)
    - `registration_number`: VARCHAR(128)
    - `license_number`: VARCHAR(128)
    - `is_active`: BOOLEAN DEFAULT true
    - `created_at`, `updated_at`

17. **`departments`**
    - `id`: UUID (PK)
    - `organization_id`: UUID (FK -> organizations.id)
    - `name`: VARCHAR(128) NOT NULL (e.g. `Credit Risk`, `Treasury & Markets`, `AML / CFT Division`, `ICT & Core Banking`)
    - `head_user_id`: UUID (FK -> users.id, NULLABLE)
    - `created_at`, `updated_at`
    - Unique constraint: `(organization_id, name)`

18. **`organization_members`**
    - `id`: UUID (PK)
    - `organization_id`: UUID (FK -> organizations.id)
    - `user_id`: UUID (FK -> users.id)
    - `department_id`: UUID (FK -> departments.id, NULLABLE)
    - `role`: VARCHAR(32) NOT NULL (`ORG_ADMIN`, `COMPLIANCE_HEAD`, `DEPARTMENT_LEAD`, `ANALYST`, `AUDITOR`, `VIEWER`)
    - `status`: VARCHAR(32) NOT NULL (`ACTIVE`, `INVITED`, `SUSPENDED`)
    - `created_at`, `updated_at`
    - Unique constraint: `(organization_id, user_id)`

19. **`roles`**, **`permissions`**, **`role_permissions`**
    - Granular RBAC supporting custom enterprise permission sets.

---

#### 2.3 Compliance and Operational Workflows
20. **`compliance_registers`**
    - `id`: UUID (PK)
    - `organization_id`: UUID (FK -> organizations.id)
    - `title`: VARCHAR(255) NOT NULL (e.g. `BRPD 2024 Master Register`, `Credit & Classification Register`)
    - `description`: TEXT
    - `is_active`: BOOLEAN DEFAULT true
    - `created_at`, `updated_at`

21. **`compliance_items`**
    - `id`: UUID (PK)
    - `register_id`: UUID (FK -> compliance_registers.id)
    - `obligation_id`: UUID (FK -> obligations.id)
    - `organization_id`: UUID (FK -> organizations.id)
    - `internal_code`: VARCHAR(64)
    - `department_id`: UUID (FK -> departments.id, NULLABLE)
    - `assigned_lead_id`: UUID (FK -> users.id, NULLABLE)
    - `status`: VARCHAR(32) NOT NULL (`NOT_STARTED`, `IN_PROGRESS`, `EVIDENCE_SUBMITTED`, `COMPLIANT`, `OVERDUE`, `EXEMPTED`)
    - `internal_deadline`: DATE
    - `created_at`, `updated_at`

22. **`compliance_tasks`**
    - `id`: UUID (PK)
    - `compliance_item_id`: UUID (FK -> compliance_items.id)
    - `organization_id`: UUID (FK -> organizations.id)
    - `title`: VARCHAR(255) NOT NULL
    - `description`: TEXT
    - `assigned_to_user_id`: UUID (FK -> users.id, NULLABLE)
    - `due_date`: DATE NOT NULL
    - `priority`: VARCHAR(16) NOT NULL (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
    - `status`: VARCHAR(32) NOT NULL (`PENDING`, `IN_PROGRESS`, `SUBMITTED`, `APPROVED`, `REJECTED`)
    - `created_at`, `updated_at`

23. **`task_evidence`**
    - `id`: UUID (PK)
    - `task_id`: UUID (FK -> compliance_tasks.id)
    - `organization_id`: UUID (FK -> organizations.id)
    - `submitted_by_user_id`: UUID (FK -> users.id)
    - `file_sha256`: VARCHAR(64) NOT NULL
    - `storage_path`: VARCHAR(512) NOT NULL
    - `original_filename`: VARCHAR(255) NOT NULL
    - `file_size_bytes`: BIGINT NOT NULL
    - `notes`: TEXT
    - `created_at`

24. **`task_reviews`**
    - `id`: UUID (PK)
    - `task_id`: UUID (FK -> compliance_tasks.id)
    - `reviewer_user_id`: UUID (FK -> users.id)
    - `decision`: VARCHAR(32) NOT NULL (`APPROVED`, `CHANGES_REQUESTED`, `REJECTED`)
    - `comments`: TEXT NOT NULL
    - `created_at`

25. **`task_events`**
    - `id`: UUID (PK)
    - `task_id`: UUID (FK -> compliance_tasks.id)
    - `actor_user_id`: UUID (FK -> users.id)
    - `event_type`: VARCHAR(64) NOT NULL
    - `event_payload`: JSONB
    - `created_at`

---

#### 2.4 Audit & Processing Metadata
26. **`audit_events`**
    - `id`: UUID (PK)
    - `organization_id`: UUID (NULLABLE for system events)
    - `actor_user_id`: UUID (NULLABLE for background jobs)
    - `action`: VARCHAR(128) NOT NULL
    - `entity_type`: VARCHAR(64) NOT NULL
    - `entity_id`: UUID NOT NULL
    - `before_state`: JSONB
    - `after_state`: JSONB
    - `ip_address`: VARCHAR(45)
    - `user_agent`: TEXT
    - `created_at`

27. **`analysis_claims`** & **`claim_citations`**
    - Fine-grained claim tracking tying AI assertions to specific text slices in `document_pages`.
