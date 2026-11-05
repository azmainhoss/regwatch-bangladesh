# Security Architecture & Data Protection
## RegWatch Bangladesh Platform

### 1. Threat Model & Key Security Requirements
Financial institutions in Bangladesh adhere to strict confidentiality and supervisory guidelines (e.g. BB Guidelines on ICT Security for Banks and NBFIs). The platform handles both public regulatory documents and sensitive internal customer compliance artifacts (audit notes, internal policy evidence, and remediation tasks).

---

### 2. Core Security Controls

#### 2.1 Multi-Tenant Isolation
- **Organization Boundary:** Every customer belongs to an `organization`.
- All compliance registers, items, tasks, uploaded evidence files, and internal discussions carry an immutable `organization_id`.
- Database queries for tenant-scoped operations enforce `WHERE organization_id = :current_org_id` at the repository/service layer.
- PostgreSQL Row-Level Security (RLS) policies are configured for production environments to enforce isolation at the database engine level.

#### 2.2 Storage Isolation
- Storage is partitioned into two physically distinct namespaces:
  1. `originals/`: Public regulatory documents downloaded from official authorities. Read-only to tenants.
  2. `evidence/`: Private customer evidence submissions. Path includes tenant hash: `evidence/{org_id}/{task_id}/{file_hash}`. Files are served exclusively through short-lived signed URLs or authenticated proxy streams that verify user organization membership and role permissions.

#### 2.3 Authentication & Authorization
- **Passwords:** Hashed with `bcrypt` (work factor 12).
- **Sessions:** Stateless JSON Web Tokens (JWT) signed with HMAC-SHA256 or asymmetric RS256, carrying user ID, organization ID, and role.
- **Role-Based Access Control (RBAC):**
  - `SUPERADMIN`: Platform operator (manages sources, reviews AI claims, approves publications).
  - `ORG_ADMIN`: Organization account owner (manages members, departments, registers).
  - `COMPLIANCE_HEAD`: Chief Compliance Officer (assigns tasks, approves task reviews).
  - `DEPARTMENT_LEAD`: Department supervisor (submits evidence, delegates tasks).
  - `ANALYST`: Officer (reads circulars, completes assigned tasks, uploads evidence).
  - `AUDITOR`: Read-only access to compliance registers, tasks, evidence, and audit logs.

#### 2.4 Audit Logging
- Security-relevant events (authentication failures, permission changes, publication status changes, task reviews, evidence uploads) are recorded in an append-only `audit_events` table capturing actor, action, timestamp, IP address, and payload diffs (`before_state`, `after_state`).

#### 2.5 Input Sanitization & Anti-Abuse
- Strict Pydantic models validate all incoming payloads.
- Uploaded files undergo MIME type verification (magic bytes) and file size limits (50 MB default).
- Automated crawler adheres to polite crawling etiquette (minimum 3s backoff, robots.txt compliance, standard user-agent identification).
