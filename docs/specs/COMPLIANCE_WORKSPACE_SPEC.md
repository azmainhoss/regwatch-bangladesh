# Compliance workspace: build spec

Status: ready to build. Written 2026-11-13.
Scope: feature 9 ("Compliance workspace for each bank") in the business-purpose file at the repo root, on the existing FastAPI backend and Next.js frontend.
Read the business-purpose file at the repo root (golden rule, personas) and `DECISIONS.md` before you start. This spec does not change any decided item there.

---

## 0. Ground rules for the builder (read first)

1. **Instant, up-to-date UI is the top priority.** After any tap, save or change, every screen that shows that data must show the new state at once. That includes the screen you go back to. Never show old data until a refresh. Section 8 says how: one shared client store, optimistic updates, rollback on failure.
2. **Test every touched control in a real browser**, at desktop width and at phone width (375 px). Check that the control reacts at once and that every other screen showing the same data has already changed when you open it.
3. **Add tests** (section 9). No new pytest failures. The baseline is 271 pass, 6 fail, 1 error (7 old known failures). After every pytest run, run `git checkout -- backend/app/tests/fixtures` (one old test rewrites a fixture PDF).
4. `npm run build` and `npm run lint` (in `frontend/`) must pass.
5. Keep code, comments, UI text, docs and test names free of any mention of how the analysis is produced (no tool or vendor names). Say "the analysis" when you mean the obligation extraction step.
6. Do not commit or push.
7. Never send requests to bb.org.bd. Never print secrets or keys.
8. Golden rule (from the business-purpose file): every register item must point back to the official document, its SHA-256 fingerprint, and the exact page, with the exact quote. Never change a register item silently when the circular changes. Flag it for a person.
9. Plain English in UI text. Short sentences.

---

## 1. Gap analysis

### 1.1 What already exists

| Area | File | What is there |
|---|---|---|
| Org models | `backend/app/modules/organizations/models.py` | `Organization`, `Department` (unique name per org, `head_user_id`), `OrganizationMember` (role, status ACTIVE/INVITED/SUSPENDED, `department_id`). |
| Org membership check | `backend/app/modules/organizations/deps.py` | `get_org_membership`: 404 for missing org, 403 "Cross-tenant access forbidden" for non-members. **Superusers get a synthetic ORG_ADMIN membership in any org.** |
| Org endpoints | `backend/app/modules/organizations/router.py` | `POST /organizations` (creator becomes ORG_ADMIN), `GET /organizations`, `GET /organizations/{id}`, `POST /organizations/{id}/members` (by `user_id`), `GET /organizations/{id}/members` (returns ids only, no names). |
| Compliance models | `backend/app/modules/compliance/models.py` | `ComplianceRegister`, `ComplianceItem` (status stored, incl. OVERDUE; `obligation_id` FK **ondelete RESTRICT**), `ComplianceTask` (priority, status PENDING/IN_PROGRESS/SUBMITTED/APPROVED/REJECTED), `TaskEvidence` (sha256, storage path, size), `TaskReview`, `TaskEvent`. |
| Compliance endpoints | `backend/app/modules/compliance/router.py` (prefix `/organizations/{organization_id}/compliance`) | `POST/GET /registers`, `POST/GET /items`, `POST/GET /tasks`, `POST/GET /tasks/{id}/evidence`, `GET /tasks/{id}/evidence/{eid}/download`, `POST /tasks/{id}/reviews`. Org checks on every referenced id. Only shared-library obligations may be linked. |
| Audit model | `backend/app/modules/audit/models.py` | `AuditEvent` (org id, actor, action, entity, before/after JSON, ip, user agent). Only the relationships router writes it today. Compliance writes none. |
| Storage | `backend/app/core/storage.py` | `storage_service.store_file(namespace, prefix, content, ext)` returns (path, sha256, size). Content-addressed, path guard against `..`. Evidence goes under `evidence/{org_id}/{task_id}/..`. No static mount serves `storage/` (checked `backend/app/main.py`). |
| In-force status | `backend/app/modules/relationships/status.py` | `bulk_in_force(db, doc_ids, user)` returns IN_FORCE / AMENDED / REPLACED / REPEALED plus the circular that did it, from VERIFIED links only, in one query. |
| Obligations | `backend/app/modules/obligations/models.py`, written by `backend/app/modules/analysis/service.py` (`_persist_analysis`, around line 168) | Per document version. `verification_status` VERIFIED or PENDING_REVIEW. `supporting_text` is the exact quote; `page_id`, `quote_span_ids`, `quote_boxes` locate it. |
| Document access | `backend/app/modules/documents/access.py` | Shared library = `owner_user_id IS NULL`. Private uploads are owner-only. |
| Frontend store pattern | `frontend/services/relationshipsStore.ts` | Module-level state + `useSyncExternalStore`, `once()` de-dup of loads, `epoch` guard against stale loads, optimistic apply + rollback + notice. |
| Frontend UI kit | `frontend/components/ui.tsx`, `frontend/app/globals.css`, `frontend/components/StatusBadge.tsx`, `frontend/components/PagePanel.tsx` | `Notice`, `Modal` (bottom sheet on phones), `ModalHeader`, `SkeletonLine`, `EmptyState`; CSS classes `.btn .btn-primary .btn-secondary .btn-ghost .btn-danger .field .field-label .meta .panel .quote .refno .section-title`; `Tag` and tones; `PagePanel` shows a page image with the quote marked. |
| Seed | `backend/scripts/seed.py` | Demo org "ABC Bank PLC" with three departments and a COMPLIANCE_HEAD user. |

### 1.2 What is wrong or missing (must be added or fixed)

**Backend bugs and risks in existing code**
1. **Re-analysis will break once a register item exists.** `_persist_analysis` deletes all obligations of the version, but `compliance_items.obligation_id` is `ondelete="RESTRICT"`. On PostgreSQL the delete fails. On SQLite (tests) foreign keys are not enforced, so the item silently points at nothing. Fix: items keep a full snapshot of the obligation (section 2), and `obligation_id` becomes nullable with `ondelete="SET NULL"`.
2. Items can be created from PENDING_REVIEW obligations and from unpublished circulars. Golden-rule breach. Fix: only VERIFIED obligations of the current version of a published, shared-library circular.
3. `POST /items` and `POST /tasks` accept any `status` from the client (an item can be created as COMPLIANT). Fix: ignore client status on create.
4. OVERDUE is a stored status nobody ever sets. Fix: derive it (section 5).
5. `POST /tasks/{id}/reviews` lets a person approve evidence they uploaded. Fix: block self-review (section 5.4). It also accepts any `decision` string and does not check the task is SUBMITTED.
6. Evidence upload: whole file read into memory, extension copied from the user's filename, no type check, `Content-Disposition` built from the raw filename (header injection risk), served as `application/octet-stream` with no `nosniff`. Fix in section 7.
7. Superusers get into every bank's workspace through the synthetic membership. This breaks "one bank never sees another bank's data" for platform staff. Default fix: no bypass on compliance and member routes (see decision D1).
8. Role names are inconsistent: the router uses `COMPLIANCE_OFFICER`, the schema comment does not list it, and nothing validates role strings. Fix: one role enum (section 4).
9. No compliance action writes an `AuditEvent`.

**Missing backend endpoints**
- Departments: list, create, rename, set head, delete.
- Members: add by email, change role/department/status, list with names and emails.
- "My organizations and my role" for the workspace picker.
- Registers: detail, update/archive, create from a circular.
- Items: add from a circular (bulk, snapshot), detail, update (department, lead, internal deadline, notes), status changes, sign-off, acknowledge a source change.
- Tasks: update (title, assignee, due date, priority, status), cancel.
- Evidence: withdraw.
- Org audit log and per-entity history.
- Board report (JSON for the print page, CSV download).
- Delta loading (`updated_since`) for cheap background refresh.

**Missing frontend**
- Everything. No workspace screens exist. `AppHeader` has no workspace link. `CircularDetail` has no "Add to register" button.

### 1.3 Old tests that assert behaviour this spec changes

Update these deliberately (do not delete them). Keep what they guard (isolation), change only the setup:
- `backend/app/tests/test_multi_tenant_security.py::test_strict_multi_tenant_isolation`: creates an item from a PENDING_REVIEW obligation on an unpublished document, sends `"status": "IN_PROGRESS"`, uploads non-PDF bytes named `.pdf`, and the uploader approves their own evidence. New setup: use the factory option below for a verified, published obligation; evidence content starts with `%PDF-`; a second member with role REVIEWER approves.
- `backend/app/tests/test_phase0_fixes.py::test_compliance_task_cannot_be_assigned_outside_org`: same obligation setup change.
- `backend/app/tests/factories.py::make_obligation`: add keyword arguments `verified: bool = False, doc_status: str = "EXTRACTED"`. When `verified=True` set `verification_status="VERIFIED"`, give the document `publication_status=doc_status` (use `"PUBLISHED_MACHINE_PROCESSED"`), and set `document.current_version_id` to the version. Defaults keep old callers unchanged.
- `test_phase3_6_pilot_readiness.py` (register role test, cross-org evidence test) must keep passing unchanged. They override `get_current_user`, so the new membership dependency must still depend on `get_current_user`.

---

## 2. Data model changes

All new columns are nullable or have defaults, so old rows stay valid. Tests build tables from the models with `Base.metadata.create_all`, so models and migration must match exactly.

### 2.1 Roles (no table change)

`OrganizationMember.role` allowed values (validate in schemas with a `Literal`):
`ORG_ADMIN, COMPLIANCE_HEAD, COMPLIANCE_OFFICER, DEPARTMENT_LEAD, REVIEWER, ANALYST, AUDITOR, VIEWER`.
`REVIEWER` is new. Update the comment in `organizations/models.py` and `schemas.py`.

### 2.2 `compliance_items` (model `ComplianceItem`)

Change:
- `obligation_id`: `nullable=True`, `ForeignKey("obligations.id", ondelete="SET NULL")`. It is only a hint now. The snapshot below is the record.
- `status` allowed values: `NOT_STARTED, IN_PROGRESS, EVIDENCE_SUBMITTED, COMPLIANT, EXEMPTED`. OVERDUE is never stored.

Add (snapshot, copied once when the item is created, never changed afterwards):

| Column | Type | From |
|---|---|---|
| `source_document_id` | GUID, FK documents.id ondelete RESTRICT, nullable, index | obligation's document |
| `source_version_id` | GUID, FK document_versions.id ondelete RESTRICT, nullable | obligation.document_version_id |
| `source_file_sha256` | String(64), nullable | document_versions.file_sha256 (the fingerprint) |
| `source_reference_number` | String(128), nullable | documents.reference_number |
| `source_title` | Text, nullable | documents.title |
| `source_publication_date` | Date, nullable | documents.publication_date |
| `source_page_number` | Integer, nullable | document_pages.page_number of obligation.page_id |
| `source_quote` | Text, nullable | obligation.supporting_text, copied exactly, no trimming |
| `source_quote_span_ids` | JSON, nullable | obligation.quote_span_ids |
| `source_quote_boxes` | JSON, nullable | obligation.quote_boxes |
| `source_key` | String(64), nullable | sha256 of `f"{source_version_id}|{source_page_number}|{source_quote}"` (dedupe key) |
| `obligation_title` | Text, nullable | obligation.title |
| `requirement_description` | Text, nullable | obligation.requirement_description |
| `obligation_type` | String(32), nullable | obligation.obligation_type |
| `applicability_summary` | Text, nullable | obligation.applicability_summary |
| `regulatory_deadline` | Date, nullable | obligation.explicit_deadline |
| `deadline_description` | Text, nullable | obligation.deadline_description |
| `frequency` | String(32), nullable | obligation.frequency |

Add (workflow):

| Column | Type | Meaning |
|---|---|---|
| `notes` | Text, nullable | Free internal notes |
| `exemption_reason` | Text, nullable | Required when status is EXEMPTED |
| `submitted_for_signoff_by_user_id` | GUID FK users SET NULL, nullable | Who sent it for sign-off |
| `submitted_for_signoff_at` | DateTime(tz), nullable | |
| `signed_off_by_user_id` | GUID FK users SET NULL, nullable | Who approved it as COMPLIANT |
| `signed_off_at` | DateTime(tz), nullable | |
| `source_ack_signature` | String(255), nullable | Source state a person last accepted (section 6.3) |
| `source_ack_at` | DateTime(tz), nullable | |
| `source_ack_by_user_id` | GUID FK users SET NULL, nullable | |
| `source_ack_note` | Text, nullable | |
| `lock_version` | Integer, not null, default 1, server_default "1" | Bumped on every change. Used for conflict checks. |

Constraint: `UniqueConstraint("register_id", "source_key", name="uq_register_item_source")`. (Rows with NULL `source_key` do not collide.)
Index: `ix_compliance_items_org_updated` on (`organization_id`, `updated_at`).

### 2.3 New table `compliance_item_reviews` (model `ComplianceItemReview`, in `compliance/models.py`)

| Column | Type |
|---|---|
| `id`, `created_at`, `updated_at` | from `Base` |
| `item_id` | GUID FK compliance_items.id CASCADE, index |
| `organization_id` | GUID FK organizations.id CASCADE, index |
| `reviewer_user_id` | GUID FK users.id RESTRICT |
| `decision` | String(32): `APPROVED` or `REJECTED` |
| `comments` | Text, not null |

Add-only. No update or delete endpoint.

### 2.4 `compliance_tasks`

- `status` allowed values: `PENDING, IN_PROGRESS, SUBMITTED, APPROVED, REJECTED, CANCELLED` (CANCELLED is new).
- `priority` allowed values: `LOW, MEDIUM, HIGH, CRITICAL` (validate).
- Add `cancelled_reason` Text nullable.
- Add `lock_version` Integer not null default 1.
- Index `ix_compliance_tasks_org_updated` on (`organization_id`, `updated_at`).

### 2.5 `task_evidence`

Add `mime_type` String(128) nullable, `withdrawn_at` DateTime(tz) nullable, `withdrawn_by_user_id` GUID FK users SET NULL nullable.

### 2.6 `task_reviews`

Add `organization_id` GUID nullable, index (backfill from the task). Add `evidence_ids` JSON nullable (ids of the non-withdrawn evidence the reviewer saw). Allowed `decision`: `APPROVED, CHANGES_REQUESTED, REJECTED`.

### 2.7 `audit_events`

Add index `ix_audit_events_org_created` on (`organization_id`, `created_at`). No column changes.

### 2.8 Alembic migration

File: `backend/migrations/versions/a3c5e7f9b1d4_compliance_workspace.py`
`revision = "a3c5e7f9b1d4"`, `down_revision = "f1b3d5a7c9e2"` (verified: `f1b3d5a7c9e2_page_correction_history.py` is the current head; it revises `e7a9c1d3f5b6`).

Copy the style of `f1b3d5a7c9e2`: `_columns(table)` and `_has_table(name)` helpers so the migration is safe to re-run, `GUID = backend.app.database.base.GUID`, and `op.batch_alter_table` on SQLite.

`upgrade()` in this order:
1. Add every new column from 2.2, 2.4, 2.5, 2.6 that is not already there.
2. `compliance_items.obligation_id`: make nullable and change the FK to `ondelete="SET NULL"`. On SQLite use `batch_alter_table("compliance_items", recreate="always")`. On PostgreSQL find the FK name with `sa.inspect(bind).get_foreign_keys("compliance_items")`, drop it, create `fk_compliance_items_obligation_id_obligations` with `ondelete="SET NULL"`.
3. Backfill the snapshot for existing items whose obligation still exists: one `UPDATE ... FROM` (PostgreSQL) or a Python loop over `SELECT` rows (SQLite; simpler, and the table is small). Join obligations → document_versions → documents, and document_pages for the page number. Compute `source_key` in Python.
4. Dedupe before the unique constraint: for any (`register_id`, `source_key`) seen twice, append `":" + id` to the later rows' `source_key`.
5. `UPDATE compliance_items SET status='IN_PROGRESS' WHERE status='OVERDUE'`.
6. Backfill `task_reviews.organization_id` from `compliance_tasks.organization_id`.
7. Create `compliance_item_reviews` with its indexes.
8. Create the unique constraint and the three indexes.

`downgrade()` reverses: drop the table, constraint, indexes and added columns; restore `obligation_id` NOT NULL with RESTRICT only if no row has NULL (otherwise raise a clear error).

Check it: copy the dev database (`data/regwatch.db`) to the scratch folder, point `DATABASE_URL` and `SYNC_DATABASE_URL` at the copy, run `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` from the repo root (`alembic.ini` is there). All three must succeed.

---

## 3. Endpoints

Prefix for all: `/api/v1`. Org routes keep the path `organizations/{organization_id}/...`.

### 3.1 Shared rules for every endpoint below

- **Membership dependency.** Add `get_workspace_membership` in `organizations/deps.py`. It depends on `get_current_user` (so test overrides keep working). Same 404/403 behaviour and the same "Cross-tenant access forbidden" message as `get_org_membership`, but **no superuser bypass** (decision D1) and the member must be ACTIVE. Use it on every compliance route and every new org route. Keep `get_org_membership` for the old `GET /organizations/{id}` only.
- **Isolation.** Every query filters by `organization_id` from the path. Every id in the path or body (register, item, task, evidence, department, user, review) is loaded and checked to belong to that org. A wrong-org id returns **404** (never reveal that it exists). Non-members get **403** at the org level. Never accept `organization_id` in a body.
- **Permission checks** use one helper module, `backend/app/modules/compliance/permissions.py` (section 4). Return 403 with a plain message.
- **Audit.** New helper `backend/app/modules/audit/service.py`:
  `record(db, *, organization_id, actor_user_id, action, entity_type, entity_id, before=None, after=None, request=None)`. It adds an `AuditEvent` in the same transaction (no separate commit) and fills `ip_address` from `request.client.host` and `user_agent` from the header. `before`/`after` hold only the fields that changed. Every write below calls it once per entity changed.
- **Conflicts.** PATCH and status endpoints accept an optional `lock_version`. If given and it does not match, return **409** with body `{"detail": "...", "current": <full Read object>}`. Every write bumps `lock_version` by 1.
- **Write responses** always return the full updated objects with derived fields, so the client store can replace them in one step. When a task write also changes its item, return both (`TaskWriteResult`).
- **Dates.** "Today" is the date in `Asia/Dhaka` (`settings.MONITOR_TIMEZONE`). Add `today_dhaka()` in `compliance/rules.py`. Responses that use it include `as_of` (the date used).
- **Validation.** Use `Literal` types for every enum. Strings stripped. Title 1–255 chars. Comments/reasons 1–2000 chars where required.

### 3.2 Shared response shapes (new, in `compliance/schemas.py` and `organizations/schemas.py`)

`UserMini`: `id, full_name, email`.

`MemberRead`: `id, organization_id, user: UserMini, role, department_id, status, created_at`.

`DepartmentRead` (exists): add `head: UserMini | null`, `member_count`, `open_item_count`.

`MyOrg`: `id, name, entity_type, role, department_id`.

`MeInOrg`: `membership: MemberRead, permissions: { manage_members, manage_departments, manage_registers, add_items, edit_any_item, exempt_and_reopen, sign_off_items, review_tasks, view_audit_log, export_report, download_evidence }` (booleans from the matrix, org-wide; per-item rules are applied on top in the client and the server).

`SourceRef` (inside an item):
`document_id, version_id, reference_number, title, publication_date, page_number, quote, quote_span_ids, quote_boxes, file_sha256, page_link` (string `"/?doc={document_id}&version={version_id}&page={page_number}"`), `in_force_status` (IN_FORCE/AMENDED/REPLACED/REPEALED), `in_force_by: {id, reference_number, title} | null`, `current_version_id`, `is_withdrawn`.

`SourceChange`: `kind` (one of `AMENDED, REPLACED, REPEALED, NEW_VERSION, WITHDRAWN`), `by: {id, reference_number, title} | null`, `detail` (one plain sentence, e.g. "BRPD Circular 12/2026 amends this circular.").

`ItemRead`:
`id, organization_id, register_id, internal_code, obligation_id, obligation_title, requirement_description, obligation_type, applicability_summary, frequency, regulatory_deadline, deadline_description, internal_deadline, effective_deadline` (internal else regulatory), `status` (stored), `display_status` (status, or OVERDUE), `is_overdue, days_left` (int or null, negative when overdue), `department_id, assigned_lead: UserMini|null, notes, exemption_reason, submitted_for_signoff_by: UserMini|null, submitted_for_signoff_at, signed_off_by: UserMini|null, signed_off_at, source: SourceRef, source_change: SourceChange|null, task_counts: {total, open, submitted, approved, overdue}, evidence_count, lock_version, created_at, updated_at`.

`TaskRead`: existing fields plus `assigned_to: UserMini|null, is_overdue, days_left, cancelled_reason, evidence_count, lock_version, updated_at`.

`EvidenceRead`: existing fields plus `mime_type, submitted_by: UserMini, withdrawn_at, withdrawn_by: UserMini|null`. Never include `storage_path`.

`TaskReviewRead`: existing plus `reviewer: UserMini, evidence_ids`.

`ItemReviewRead`: `id, item_id, reviewer: UserMini, decision, comments, created_at`.

`TaskWriteResult`: `task: TaskRead, item: ItemRead`.

`AuditRead`: `id, action, entity_type, entity_id, actor: UserMini|null, before, after, created_at`. (No ip or user agent in the API.)

`RegisterRead`: existing plus `item_counts: {total, not_started, in_progress, evidence_submitted, compliant, exempted, overdue, flagged}`, `source_document_ids` (distinct).

### 3.3 Organization and member endpoints (`organizations/router.py`)

| # | Method, path | Body / query | Response | Who | Audit action |
|---|---|---|---|---|---|
| O1 | GET `/organizations/mine` | – | `List[MyOrg]` (ACTIVE memberships only, no superuser listing) | any signed-in user | – |
| O2 | GET `/organizations/{org}/me` | – | `MeInOrg` | member | – |
| O3 | GET `/organizations/{org}/members` (change) | – | `List[MemberRead]` (with names, emails) | member | – |
| O4 | POST `/organizations/{org}/members/by-email` | `{email, role, department_id?}` | `MemberRead` 201. 404 "No RegWatch account uses that email. Ask them to sign up first." 400 if already a member. | ORG_ADMIN; COMPLIANCE_HEAD (cannot grant ORG_ADMIN) | MEMBER_ADDED |
| O5 | PATCH `/organizations/{org}/members/{member_id}` | `{role?, department_id?, status? (ACTIVE/SUSPENDED)}` | `MemberRead` | ORG_ADMIN; COMPLIANCE_HEAD for non-admin members, cannot grant ORG_ADMIN | MEMBER_UPDATED |
| O6 | GET `/organizations/{org}/departments` | – | `List[DepartmentRead]` | member | – |
| O7 | POST `/organizations/{org}/departments` | `{name, head_user_id?}` | `DepartmentRead` 201; 409 on duplicate name | ORG_ADMIN, COMPLIANCE_HEAD | DEPARTMENT_CREATED |
| O8 | PATCH `/organizations/{org}/departments/{dept_id}` | `{name?, head_user_id?}` | `DepartmentRead` | ORG_ADMIN, COMPLIANCE_HEAD | DEPARTMENT_UPDATED |
| O9 | DELETE `/organizations/{org}/departments/{dept_id}` | – | 204; 409 "Move its items first" if any item uses it | ORG_ADMIN | DEPARTMENT_DELETED |

Rules: O5 must refuse to leave the org with no ACTIVE ORG_ADMIN (400). `head_user_id` and member `department_id` must belong to the org. Keep the old `POST /members` (by user_id) working, but add the same role validation and audit.

### 3.4 Register endpoints (`compliance/router.py`)

| # | Method, path | Body / query | Response | Who | Audit |
|---|---|---|---|---|---|
| R1 | GET `/registers` (change) | `include_archived=false` | `List[RegisterRead]` | member | – |
| R2 | POST `/registers` (keep) | `{title, description?}` | `RegisterRead` 201 | ORG_ADMIN, COMPLIANCE_HEAD, COMPLIANCE_OFFICER | REGISTER_CREATED |
| R3 | GET `/registers/{rid}` | – | `RegisterRead` | member | – |
| R4 | PATCH `/registers/{rid}` | `{title?, description?, is_active?}` (`is_active=false` = archive) | `RegisterRead` | as R2 | REGISTER_UPDATED |
| R5 | POST `/registers/from-document` | `{document_id, title?, obligation_ids?}` | `{register: RegisterRead, items: List[ItemRead], skipped: List[{obligation_id, reason}]}` 201 | as R2 | REGISTER_CREATED + ITEM_ADDED per item |

R5 creates a register titled `title` or `"{reference_number}: {document title}"` (cut to 255) and adds items as in I1. No register delete endpoint: archive instead (registers hold audit history).

### 3.5 Item endpoints

| # | Method, path | Body / query | Response | Who | Audit |
|---|---|---|---|---|---|
| I0 | GET `/documents/{document_id}/addable-obligations` | – | `{document: {id, reference_number, title, publication_status, in_force_status, in_force_by, current_version_id}, obligations: [{id, title, obligation_type, page_number, quote, regulatory_deadline, verification_status, addable: bool, reason_not_addable, already_in_register_ids}]}` | member | – |
| I1 | POST `/registers/{rid}/items/from-document` | `{document_id, obligation_ids?: [..]}` (omitted = all addable) | `{items: List[ItemRead], skipped: [...]}` 201 | ORG_ADMIN, COMPLIANCE_HEAD, COMPLIANCE_OFFICER | ITEM_ADDED per item |
| I2 | POST `/items` (keep, changed) | `{register_id, obligation_id, internal_code?, department_id?, assigned_lead_id?, internal_deadline?}`; `status` ignored | `ItemRead` 201 | as I1 | ITEM_ADDED |
| I3 | GET `/items` (change) | `register_id?, display_status?, department_id?, lead_id?, overdue?: bool, flagged?: bool, due_before?: date, q?: str (title/quote/ref), updated_since?: datetime, limit (default 500, max 2000), offset` | `{items: List[ItemRead], total, as_of}` | member | – |
| I4 | GET `/items/{iid}` | – | `{item: ItemRead, tasks: List[TaskRead], evidence: List[EvidenceRead], task_reviews: List[TaskReviewRead], item_reviews: List[ItemReviewRead]}` | member | – |
| I5 | PATCH `/items/{iid}` | `{department_id?, assigned_lead_id?, internal_deadline?, internal_code?, notes?, lock_version?}` (explicit `null` clears) | `ItemRead` | ORG_ADMIN, COMPLIANCE_HEAD, COMPLIANCE_OFFICER; DEPARTMENT_LEAD only for items of their own department, cannot move the item to another department, may only pick a lead from their own department | ITEM_UPDATED |
| I6 | POST `/items/{iid}/status` | `{to: IN_PROGRESS | EVIDENCE_SUBMITTED | EXEMPTED | NOT_STARTED, reason?, lock_version?}` | `ItemRead` | section 5.2 table | ITEM_STATUS_CHANGED |
| I7 | POST `/items/{iid}/signoff` | `{decision: APPROVED | REJECTED, comments}` | `{item: ItemRead, review: ItemReviewRead}` 201 | ORG_ADMIN, COMPLIANCE_HEAD, REVIEWER, never self (5.4) | ITEM_SIGNED_OFF |
| I8 | POST `/items/{iid}/acknowledge-source-change` | `{note}` (required) | `ItemRead` | ORG_ADMIN, COMPLIANCE_HEAD, COMPLIANCE_OFFICER | ITEM_SOURCE_CHANGE_ACKNOWLEDGED (before/after = old and new signature, plus the `SourceChange`) |
| I9 | POST `/items/{iid}/reopen` | `{reason}` | `ItemRead` (COMPLIANT → IN_PROGRESS; clears signed_off_*) | ORG_ADMIN, COMPLIANCE_HEAD | ITEM_STATUS_CHANGED |

I0 is under `/organizations/{org}/compliance/documents/{document_id}/addable-obligations`. It only works for shared-library documents (`owner_user_id IS NULL`); anything else is 404.

The derived fields (`display_status`, `source_change`, counts) are computed in one place: `compliance/rules.py` + a loader `compliance/service.py::load_items(db, org_id, filters)` that fetches items, then in bulk: users, the source documents, `bulk_in_force(db, source_doc_ids, user=None)` (shared-library links only, so one user's private upload never changes a bank's register), task counts (one grouped query) and evidence counts (one grouped query). No per-item queries. `overdue`, `display_status` and `due_before` filters are applied in SQL on `effective_deadline` (`coalesce(internal_deadline, regulatory_deadline)`). `flagged` is applied after the bulk in-force step.

### 3.6 Task endpoints

| # | Method, path | Body / query | Response | Who | Audit |
|---|---|---|---|---|---|
| T1 | POST `/tasks` (keep, changed) | `{compliance_item_id, title, description?, assigned_to_user_id?, due_date, priority}`; `status` ignored, always PENDING | `TaskWriteResult` 201 | ORG_ADMIN, COMPLIANCE_HEAD, COMPLIANCE_OFFICER; DEPARTMENT_LEAD for own-department items; item lead for their item. 400 if item is COMPLIANT or EXEMPTED ("Reopen it first"). | TASK_CREATED (+ ITEM_STATUS_CHANGED if the item moved) |
| T2 | GET `/tasks` (change) | `item_id?, assignee?: "me" or user id, status?, overdue?: bool, awaiting_review?: bool, updated_since?, limit, offset` | `{tasks: List[TaskRead], total, as_of}` | member | – |
| T3 | PATCH `/tasks/{tid}` | `{title?, description?, assigned_to_user_id?, due_date?, priority?, status?: PENDING | IN_PROGRESS, lock_version?}` | `TaskWriteResult` | editors as T1; the assignee may only change `status` (PENDING ↔ IN_PROGRESS) | TASK_UPDATED / TASK_STATUS_CHANGED |
| T4 | POST `/tasks/{tid}/cancel` | `{reason}` | `TaskWriteResult` | editors as T1; not allowed when APPROVED | TASK_STATUS_CHANGED |
| T5 | POST `/tasks/{tid}/evidence` (keep, hardened) | multipart `file`, `notes?` | `{evidence: EvidenceRead, task: TaskRead, item: ItemRead}` 201 | editors as T1, the task assignee, the item lead. Not when task is APPROVED or CANCELLED, or item is COMPLIANT/EXEMPTED. | EVIDENCE_UPLOADED (filename, sha256, size, mime) |
| T6 | GET `/tasks/{tid}/evidence` (keep) | – | `List[EvidenceRead]` (withdrawn included, marked) | member | – |
| T7 | GET `/tasks/{tid}/evidence/{eid}/download` (keep, hardened) | – | file stream | every role except VIEWER | EVIDENCE_DOWNLOADED |
| T8 | POST `/tasks/{tid}/evidence/{eid}/withdraw` | `{reason}` | `{evidence, task, item}` | the uploader only, while the task is not APPROVED | EVIDENCE_WITHDRAWN |
| T9 | POST `/tasks/{tid}/reviews` (keep, hardened) | `{decision: APPROVED | CHANGES_REQUESTED | REJECTED, comments}` | `{review: TaskReviewRead, task: TaskRead, item: ItemRead}` 201 | ORG_ADMIN, COMPLIANCE_HEAD, REVIEWER; DEPARTMENT_LEAD for own-department items. Never self (5.4). Task must be SUBMITTED (else 409). | TASK_REVIEWED |

### 3.7 Audit, report

| # | Method, path | Query | Response | Who | Audit |
|---|---|---|---|---|---|
| A1 | GET `/audit` | `entity_type?, entity_id?, actor_id?, action?, before?: datetime (paging), limit (default 100, max 500)` | `{events: List[AuditRead], next_before}` | ORG_ADMIN, COMPLIANCE_HEAD, REVIEWER, AUDITOR for the whole log; any member when `entity_id` is an item or task of this org (item history). With `entity_id` = an item, also include events for that item's tasks and evidence. | – |
| A2 | GET `/report` | `register_id?, format: json | csv` | json: `{organization, generated_at, as_of, generated_by, totals, by_department: [{department_id, name, total, open, overdue, evidence_submitted, compliant, exempted}], overdue_items: List[ItemRead], upcoming_items (next 30 days): List[ItemRead], flagged_items: List[ItemRead], items: List[ItemRead]}`. csv: one row per item. | every member | REPORT_EXPORTED (format, register_id) |

CSV columns (in this order): Register, Internal code, Obligation, Circular reference, Circular title, Page, Exact quote, File SHA-256, Department, Lead, Regulatory deadline, Internal deadline, Status (display), Days left, Open tasks, Evidence files, Signed off by, Signed off at, Source change. UTF-8 with BOM (so Excel shows Bangla). `Content-Disposition: attachment; filename="regwatch-report-YYYY-MM-DD.csv"`. To stop spreadsheet formula injection, prefix any cell that starts with `=`, `+`, `-`, `@`, tab or carriage return with a single quote `'`.

PDF: no server PDF. The report screen is a print-ready page; "Print or save as PDF" calls `window.print()` (decision D4).

---

## 4. Roles and permissions

Mapping of the roles asked for to stored roles:
- org admin → `ORG_ADMIN`
- CCO / head of compliance → `COMPLIANCE_HEAD` (also a reviewer)
- compliance officer → `COMPLIANCE_OFFICER`
- department lead → `DEPARTMENT_LEAD` (scoped to `membership.department_id`)
- reviewer → `REVIEWER` (new)
- department staff → `ANALYST` (works on tasks assigned to them)
- internal audit → `AUDITOR` (read all, audit log, downloads; no changes)
- viewer (board member, read only) → `VIEWER`

"Own department" means `item.department_id == membership.department_id` and the latter is not null.
"Item lead" means `item.assigned_lead_id == user.id`. "Assignee" means `task.assigned_to_user_id == user.id`.

| Action | ORG_ADMIN | COMPLIANCE_HEAD | COMPLIANCE_OFFICER | DEPARTMENT_LEAD | REVIEWER | ANALYST | AUDITOR | VIEWER |
|---|---|---|---|---|---|---|---|---|
| See registers, items, tasks, evidence list, item history | yes | yes | yes | yes | yes | yes | yes | yes |
| Download evidence | yes | yes | yes | yes | yes | yes | yes | no |
| Whole-org audit log | yes | yes | no | no | yes | no | yes | no |
| Board report and CSV | yes | yes | yes | yes | yes | yes | yes | yes |
| Add/edit members | yes | yes (not ORG_ADMIN) | no | no | no | no | no | no |
| Departments create/rename | yes | yes | no | no | no | no | no | no |
| Department delete | yes | no | no | no | no | no | no | no |
| Create/edit/archive registers | yes | yes | yes | no | no | no | no | no |
| Add items from a circular | yes | yes | yes | no | no | no | no | no |
| Edit item (dept, lead, deadline, notes) | yes | yes | yes | own dept | no | no | no | no |
| Start item / send for sign-off | yes | yes | yes | own dept | no | item lead | no | no |
| Exempt, un-exempt, reopen COMPLIANT | yes | yes | no | no | no | no | no | no |
| Sign off item (COMPLIANT) | yes* | yes* | no | no | yes* | no | no | no |
| Acknowledge source change | yes | yes | yes | no | no | no | no | no |
| Create/edit/cancel tasks | yes | yes | yes | own dept | no | item lead | no | no |
| Change own task status | yes | yes | yes | yes | yes | assignee | no | no |
| Upload evidence | yes | yes | yes | own dept | no | assignee or item lead | no | no |
| Withdraw evidence | uploader only, before approval (any role) |||||||
| Review task evidence | yes* | yes* | no | own dept* | yes* | no | no | no |

`*` = never on work they were involved in (5.4).

Put the matrix in `backend/app/modules/compliance/permissions.py` as plain functions (`can_edit_item(m, item)`, `can_review_task(m, task, item, evidence)`, ...). Mirror it in `frontend/services/workspaceRules.ts` so controls are hidden or disabled before the user taps them. The server is the final check; a 403 rolls the optimistic change back (section 8).

---

## 5. Status rules

### 5.1 Overdue is derived, not stored

Rule: an item is overdue when `status` is NOT_STARTED or IN_PROGRESS, `effective_deadline` is set, and `effective_deadline < today in Asia/Dhaka`. Then `display_status = "OVERDUE"`. A task is overdue when its status is PENDING, IN_PROGRESS or REJECTED and `due_date < today`.

EVIDENCE_SUBMITTED, COMPLIANT and EXEMPTED items are never overdue. (The bank has done its part; the deadline still shows in red when it has passed.)

Why derived:
- It is always right, including the minute after midnight, with no job to run. The only scheduler runs in one process and is switched off in tests and in some setups.
- Editing a deadline flips overdue at once on the server and in the browser with the same rule, no extra write.
- No fake "status changed" rows flood the audit trail every night.
- SQL can still filter on it (`coalesce(internal_deadline, regulatory_deadline) < :today`).

The browser computes the same rule from the store (`workspaceRules.ts::isItemOverdue(item, today)`) so a deadline edit or a status change redraws the badge instantly. The store sets a timer for the next Dhaka midnight and recomputes.

### 5.2 Item states

Stored states: NOT_STARTED, IN_PROGRESS, EVIDENCE_SUBMITTED, COMPLIANT, EXEMPTED.

| From → to | How | Who | Conditions |
|---|---|---|---|
| NOT_STARTED → IN_PROGRESS | I6 `to=IN_PROGRESS`, or automatic when a task is created, a task moves to IN_PROGRESS, or evidence is uploaded | I6: "Start item" row in section 4 | – |
| IN_PROGRESS → EVIDENCE_SUBMITTED | I6 `to=EVIDENCE_SUBMITTED` ("Send for sign-off") | "Start item / send for sign-off" row | At least one task that is not CANCELLED; every such task is APPROVED; at least one non-withdrawn evidence file on the item. Sets `submitted_for_signoff_*`. Else 409 with the reason in plain words. |
| EVIDENCE_SUBMITTED → COMPLIANT | I7 `decision=APPROVED` | sign-off row | Not self (5.4). Sets `signed_off_*`. |
| EVIDENCE_SUBMITTED → IN_PROGRESS | I7 `decision=REJECTED` (comments required), or automatic when a task is added, or a task is reopened | sign-off row | Clears `submitted_for_signoff_*`. |
| COMPLIANT → IN_PROGRESS | I9 reopen, reason required | ORG_ADMIN, COMPLIANCE_HEAD | Clears `signed_off_*`. |
| any except COMPLIANT → EXEMPTED | I6 `to=EXEMPTED`, `reason` required | ORG_ADMIN, COMPLIANCE_HEAD | Stores `exemption_reason`. Open tasks stay as they are. |
| EXEMPTED → NOT_STARTED | I6 `to=NOT_STARTED` ("Remove exemption") | ORG_ADMIN, COMPLIANCE_HEAD | Clears `exemption_reason`. Item then moves to IN_PROGRESS automatically if it has any non-cancelled task. |

Anything else returns 409 "This item cannot move from X to Y." Every automatic move is written to the audit log with the actor who caused it and `after.reason = "automatic: <cause>"`.

### 5.3 Task states

| From → to | How |
|---|---|
| PENDING ↔ IN_PROGRESS | T3 `status` |
| PENDING, IN_PROGRESS, REJECTED → SUBMITTED | automatic on evidence upload (T5) |
| SUBMITTED → APPROVED | T9 APPROVED |
| SUBMITTED → IN_PROGRESS | T9 CHANGES_REQUESTED |
| SUBMITTED → REJECTED | T9 REJECTED (evidence not acceptable; new evidence needed) |
| SUBMITTED → IN_PROGRESS | automatic when every evidence file of the task is withdrawn |
| any except APPROVED → CANCELLED | T4 with reason |

Comments are required for CHANGES_REQUESTED and REJECTED, optional (may be empty string) for APPROVED. After T9, if the item was EVIDENCE_SUBMITTED and the task is no longer APPROVED, the item goes back to IN_PROGRESS automatically.

### 5.4 Nobody reviews their own work

- **Task review (T9):** refused with 403 "You cannot review evidence you uploaded." when the reviewer uploaded any non-withdrawn evidence on that task, or is the task's assignee.
- **Item sign-off (I7):** refused with 403 "You cannot sign off an item you worked on." when the reviewer sent the item for sign-off, or uploaded any non-withdrawn evidence on any task of the item.
- This applies to ORG_ADMIN and COMPLIANCE_HEAD too. There is no override.
- The client hides the approve buttons in these cases and shows a short line: "You uploaded evidence here, so another reviewer must decide."

---

## 6. Registers from circulars

### 6.1 What can be added

An obligation is addable only when all are true:
1. Its document is in the shared library (`owner_user_id IS NULL`).
2. The document's `publication_status` starts with `PUBLISHED` (PUBLISHED_MACHINE_PROCESSED or PUBLISHED_HUMAN_REVIEWED).
3. The obligation belongs to the document's `current_version_id`.
4. `verification_status == "VERIFIED"`.

Otherwise I0 returns it with `addable=false` and a plain `reason_not_addable`: "Awaiting quote check", "Circular not published yet", "Older version of this circular", "Private upload". I1 and I2 refuse it (I1 lists it in `skipped`; I2 returns 400 with that reason).

If the circular itself is AMENDED, REPLACED or REPEALED, I0 still allows adding, but returns `in_force_status` and `in_force_by`. The UI shows a warning with a link to the newer circular (section 8, "Add to register" modal).

### 6.2 What an item keeps

On creation, copy the snapshot columns in 2.2 from the obligation, its version, document and page. The quote is copied exactly. Never edit snapshot columns afterwards, not even through PATCH. If the same obligation (same `source_key`) is already in the register, skip it (`skipped: "Already in this register"`). The same obligation may be in two different registers.

The item screen shows the exact quote, the page number, the circular reference and the SHA-256 fingerprint. "View on page N" opens the page image with the quote marked (section 8.4), from the snapshot version, even if a newer version exists.

### 6.3 When the circular changes later

Never change an item's snapshot, status, deadline or tasks because the circular changed. Flag it and let a person decide.

**How the flag works (derived, no job):**
- Signature of a source = `f"{in_force_status}|{in_force_by_id or ''}|{current_version_id}|{'W' if withdrawn else ''}"`, where `in_force_status` comes from `bulk_in_force(db, ids, user=None)`, `current_version_id` from the document, and `withdrawn` means `publication_status == "WITHDRAWN"`.
- When an item is created, `source_ack_signature` is set to the source's signature at that moment (so adding from an already-amended circular does not flag, because the user was warned at add time).
- Old rows with NULL `source_ack_signature` compare against the baseline `"IN_FORCE||{source_version_id}|"`.
- On every item read, if the current signature differs from `source_ack_signature`, `source_change` is filled. Kind, in priority order: WITHDRAWN, REPEALED, REPLACED, AMENDED (the in-force status), NEW_VERSION (`current_version_id != source_version_id`).
- I8 "Mark as reviewed" stores the current signature, the person, time and their note. The flag clears until the source changes again.

**What the person can do from the flag banner:**
- "Mark as reviewed" (I8, note required), for example "Amendment changes the reporting form only; our item still applies."
- "Add items from {newer circular}" opens the add modal for the circular in `by` (or for the new version of the same circular).
- "Exempt this item" (I6 EXEMPTED, reason prefilled "Replaced by {ref}"), for heads/admins.
- "Reopen" when it was COMPLIANT (I9).

The dashboard shows a "Circular changed" count, and the register has a "Circular changed" filter.

---

## 7. Evidence files

- **Where:** `storage_service.store_file(namespace=f"evidence/{organization_id}/{item_id}/{task_id}", ...)` under `settings.STORAGE_LOCAL_ROOT`. The org id is in the path, so the same file uploaded by two banks is stored twice, never shared. No static route serves `storage/`; files leave only through T7.
- **Size:** new setting `EVIDENCE_MAX_BYTES: int = 25 * 1024 * 1024` in `backend/app/core/config.py` (replace the hard-coded 50 MB). Read the upload in 1 MB chunks and stop with 413 "File is larger than 25 MB." as soon as the limit is passed. Empty file → 400.
- **Types allowed** (by extension, lowercased, plus a content check):

| Extension | Stored mime | Content must start with |
|---|---|---|
| .pdf | application/pdf | `%PDF-` |
| .png | image/png | `\x89PNG\r\n\x1a\n` |
| .jpg, .jpeg | image/jpeg | `\xff\xd8\xff` |
| .docx | application/vnd.openxmlformats-officedocument.wordprocessingml.document | `PK\x03\x04` |
| .xlsx | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | `PK\x03\x04` |
| .csv | text/csv | decodes as UTF-8 |
| .txt | text/plain | decodes as UTF-8 |

Anything else → 415 "Allowed files: PDF, PNG, JPG, DOCX, XLSX, CSV, TXT." The stored extension comes from this table, never from the raw filename.
- **Filename:** keep `original_filename` for display only: strip path parts, control characters and quotes, cut to 200 chars. Fallback `evidence.<ext>`.
- **Hash:** SHA-256 of the bytes (`store_file` returns it). Shown in the UI (first 12 characters, full value on tap/copy) and returned in the `X-SHA256-Checksum` header on download.
- **Immutable:** evidence is never edited or deleted. "Withdraw" (T8) marks it withdrawn; the file stays for the audit trail and is still downloadable, shown struck through.
- **Download (T7):** check membership (not VIEWER), that the evidence's `organization_id` equals the path org and its `task_id` equals the path task, else 404. Headers: `Content-Type` = stored mime (fallback `application/octet-stream`), `Content-Disposition: attachment; filename="<ascii fallback>"; filename*=UTF-8''<percent-encoded>`, `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`, `X-SHA256-Checksum`. Use `FileResponse` on `storage_service.get_absolute_path(...)` instead of loading the file into memory.
- **Browser side:** the app sends a bearer token, so a plain `<a href>` will not work. Download with `apiFetch` → `blob()` → object URL → click a temporary `<a download>` → revoke the URL. Same pattern as `openDocumentPdf` in `frontend/services/api.ts`.

---

## 8. Screens

### 8.1 Files to add

Frontend:
- `frontend/services/workspaceApi.ts`: types from 3.2 and one function per endpoint. Import `apiFetch`, `ApiError` from `./api`. (Do not grow `api.ts` further.) Evidence upload uses `XMLHttpRequest` so it can report progress; set the bearer header from `getAuthToken()`.
- `frontend/services/workspaceRules.ts`: pure functions, no React: `dhakaToday()`, `msUntilDhakaMidnight()`, `effectiveDeadline`, `isItemOverdue`, `displayStatus`, `daysLeft`, `isTaskOverdue`, `allowedItemMoves(item, me)`, the permission functions from section 4, `summarize(items, tasks, departments, today)` for the dashboard, `sourceChangeText`.
- `frontend/services/workspaceStore.ts`: the shared store (8.2).
- `frontend/components/workspace/`: `WorkspaceNav.tsx`, `ItemStatusBadge.tsx`, `TaskStatusBadge.tsx`, `ItemRow.tsx` (table row on desktop, card on phone), `ItemFilters.tsx`, `AssignControls.tsx`, `DeadlineField.tsx`, `SourceQuote.tsx`, `SourceChangeBanner.tsx`, `TaskList.tsx`, `TaskEditor.tsx` (modal), `EvidenceList.tsx`, `EvidenceUpload.tsx`, `ReviewBox.tsx`, `SignoffBox.tsx`, `HistoryList.tsx`, `AddToRegisterModal.tsx`, `ReasonModal.tsx` (shared "reason required" dialog).
- Routes (all `"use client"`; wrap any component that calls `useSearchParams` in `<Suspense>` like `app/page.tsx` does, or `next build` fails):

| Route | File |
|---|---|
| `/workspace` | `app/workspace/page.tsx` |
| `/workspace/[orgId]` (dashboard) | `app/workspace/[orgId]/page.tsx` + `app/workspace/[orgId]/layout.tsx` (loads org, shows `WorkspaceNav`) |
| `/workspace/[orgId]/registers` | `.../registers/page.tsx` |
| `/workspace/[orgId]/registers/[registerId]` | `.../registers/[registerId]/page.tsx` |
| `/workspace/[orgId]/items/[itemId]` | `.../items/[itemId]/page.tsx` |
| `/workspace/[orgId]/tasks` | `.../tasks/page.tsx` |
| `/workspace/[orgId]/review` | `.../review/page.tsx` |
| `/workspace/[orgId]/report` | `.../report/page.tsx` |
| `/workspace/[orgId]/settings` | `.../settings/page.tsx` |
| `/workspace/[orgId]/audit` | `.../audit/page.tsx` |

Changes to existing files:
- `components/AppHeader.tsx`: add nav item `{ href: "/workspace", label: "Workspace", show: !!currentUser }`.
- `components/CircularDetail.tsx`: an "Add to register" button next to the history button, shown when the user is signed in, the circular is shared and published, and the user has `add_items` in at least one org. Opens `AddToRegisterModal`. Also a small "In your register" tag on each obligation that is already in a register of the user's active org (from `already_in_register_ids`).
- `app/page.tsx`: support a `version` query param. When `version` differs from the current version, load that version's pages with `fetchDocumentPages(docId, version)` and show a notice "You are viewing an older version of this circular (the one the register item was built from)."

### 8.2 The shared store (`workspaceStore.ts`)

Follow `relationshipsStore.ts`: module-level `state`, `subscribe`, `useWorkspace()` via `useSyncExternalStore`, `once()` to de-dup loads, `notice` for messages. Improve two things:

1. **Normalized state.** One copy of each record:
```
orgs: MyOrg[] | null
activeOrgId: string | null
me: Record<orgId, MeInOrg>
members: Record<orgId, MemberRead[]>
departments: Record<orgId, DepartmentRead[]>
registers: Record<registerId, RegisterRead>
items: Record<itemId, ItemRead>
tasks: Record<taskId, TaskRead>
evidence: Record<evidenceId, EvidenceRead>
taskReviews: Record<reviewId, TaskReviewRead>
itemReviews: Record<reviewId, ItemReviewRead>
history: Record<entityId, AuditRead[]>
loaded: Record<string, "loading" | "ok" | { error: string }>   // keys like "items:<orgId>"
pending: Record<entityId, number>   // count of saves in flight per record
lastSync: Record<orgId, string>     // server time of last full or delta load
today: string                       // Dhaka date, refreshed at midnight
notice: { kind, text } | null
```
Every list on every screen is a **selector** over these maps (for example `selectItems(state, {registerId, displayStatus, departmentId, ...})`, `selectDashboard(state, orgId)` which calls `summarize`). Selectors are memoized on the maps' identity. Because no screen keeps its own copy, one change redraws every screen, including the register counts, the dashboard and the page you return to.

2. **Per-record rollback**, not whole-state rollback. A mutation:
   1. Saves `before` copies of only the records it will touch (item, task, register counts are derived so they need nothing).
   2. Applies the optimistic change (including derived effects, e.g. uploading evidence sets the task to SUBMITTED and a NOT_STARTED item to IN_PROGRESS; a new deadline recomputes overdue through the selector).
   3. Increments `pending[id]`.
   4. Calls the API.
   5. On success, replaces the records with the server's copies (`TaskWriteResult` etc.), decrements `pending`, shows a short success notice only where useful ("Sent for sign-off").
   6. On failure, puts back the `before` copies **only if** the record's `lock_version` is still the optimistic one (another save may have landed), decrements `pending`, and shows an error notice in plain words with the server's `detail` ("Could not save: You cannot review evidence you uploaded. Nothing was changed."). On 409 with `current`, store `current` and say "Someone else changed this item. You now see their version."

**Loads never overwrite fresher data:** when a load returns, for each record skip it if `pending[id] > 0`, or if the stored `lock_version` is higher than the loaded one. Otherwise replace.

**Keeping in sync with other people and tabs:**
- Delta refresh every 30 s while the tab is visible, and on window focus: `GET /items?updated_since=lastSync` and `GET /tasks?updated_since=lastSync`. Merge with the rule above.
- After every successful write, post `{orgId, ids}` on a `BroadcastChannel("regwatch-workspace")`; other tabs run a delta refresh at once.
- Also refetch `GET /items/{id}` when the item screen opens (cheap, makes the source-change flag current).
- `/me` and departments/members load once per org and after any member or department write.

**Instant controls:**
- Every button reacts on tap: optimistic change first, then the request. Disable only the one control while its record is pending (show a small spinner in that control), not the whole screen.
- Lists and pickers are preloaded: when the workspace layout mounts, load `/me`, members, departments, registers, all items (paged until done) and all open tasks in parallel. Department and lead pickers then open at once with no fetch.
- Dropdown changes (department, lead, priority) save on change; no separate Save button.
- Date fields save on blur or Enter, and only if the value changed.

### 8.3 Screen by screen

All screens: loading = skeleton rows (`SkeletonLine`), never a blank page. Error = `Notice kind="error"` with the message and a "Try again" button that reruns the load. Empty = `EmptyState` with one helpful action. Phone width (375 px): one column, 16 px side padding, no sideways scrolling of the page, tap targets at least 44 px high, tables turn into cards, modals open as bottom sheets (the existing `Modal` does this).

**`/workspace`**
- Loads `GET /organizations/mine`.
- One org: redirect to `/workspace/{id}` with `router.replace`.
- Several: a list of org cards (name, your role). Tap opens it. The last used org id is kept in `localStorage` (wrapped in try/catch) and preselected next time.
- None: `EmptyState` "You are not in a bank workspace yet." Two actions: "Create a workspace" (inline form: bank name, type select COMMERCIAL_BANK / ISLAMIC_BANK / NBFI / OTHER; POST `/organizations`; on success go to settings to add departments) and a line "If your bank already uses RegWatch, ask your admin to add your email."
- Not signed in: "Sign in to use your bank's workspace" with a button that opens the existing `AccountModal`.

**Workspace layout (`[orgId]/layout.tsx`)**
- Header line: org name, your role tag.
- `WorkspaceNav` tabs: Dashboard, Registers, Tasks, Review (with a count badge of items/tasks waiting for you), Report, Settings (only with `manage_members` or `manage_departments`), Audit log (only with `view_audit_log`). On phones the tabs scroll sideways inside their own strip.
- 403 from `/me`: "You are not a member of this workspace." with a link back to `/workspace`.

**Dashboard (`/workspace/[orgId]`)** (the CCO view; all numbers come from `selectDashboard`)
- Four tiles, each a link to the register view with that filter: Open obligations (NOT_STARTED + IN_PROGRESS + EVIDENCE_SUBMITTED), Overdue, Waiting for sign-off, Circular changed. Each tile shows its denominator ("12 of 140 items").
- "Upcoming deadlines (next 30 days)": items and tasks sorted by date, each row: date, days left, title, department, status badge. Tap opens the item.
- "Overdue": same layout, red date.
- "By department": table (cards on phone) with columns Department, Open, Overdue, Waiting sign-off, Compliant, Exempted, Total. A row "No department" for unassigned items. Tap a row → register view filtered by that department.
- "My tasks": the signed-in user's open tasks, with a quick status toggle (PENDING ↔ IN_PROGRESS).
- Buttons: "Board report" (→ report page), "Download CSV".
- Empty (no registers): "No registers yet. Start one from a circular." Button "Browse circulars" (→ `/`) and, with `manage_registers`, "New register".

**Registers (`/registers`)**
- List of registers: title, description, counts bar (compliant / in progress / overdue / not started), number of source circulars, archived tag.
- "New register" (title, description) modal. "Show archived" toggle.
- Each card menu: Rename, Archive / Unarchive (PATCH R4).
- Empty: "No registers yet." + "New register" + "Browse circulars".

**Register view (`/registers/[registerId]`)**
- Header: title, description, counts, "Add from a circular" button (opens `AddToRegisterModal` with a circular search box: reuse `searchCirculars` from `services/api.ts`, then I0 for the picked circular).
- `ItemFilters`: status (All, Not started, In progress, Overdue, Waiting sign-off, Compliant, Exempted), department, lead, "Circular changed", text search, sort (deadline, status, circular). Filters live in the URL query so a link from a dashboard tile works. Filtering is done by the selector on the client (instant).
- Rows (`ItemRow`): obligation title, circular ref + page ("BRPD 12/2026, p. 3"), department picker, lead picker, effective deadline with days left, status badge, task progress ("2 of 3 tasks approved"), a "Circular changed" tag when flagged. Pickers are inline and save on change (I5). Row tap (outside the pickers) opens the item.
- Empty register: "This register has no items yet." + "Add from a circular". Empty after filter: "No items match these filters." + "Clear filters".

**`AddToRegisterModal`** (used on the register view and on the circular screen)
- Step 1 (only from the circular screen): pick register (select of active registers) or "New register named after this circular" (R5).
- Step 2: list from I0. Each obligation: checkbox, title, type, page, the exact quote (2 lines, expandable), regulatory deadline. Disabled ones show their reason. "Already in this register" ones are unchecked and disabled. "Select all addable" toggle.
- If the circular is not IN_FORCE: a warning Notice "This circular was {amended/replaced/repealed} by {ref}." with a button "Open {ref}" and "Add from {ref} instead".
- "Add N items" → I1 (or R5). Optimistic: the new items appear at once in the register view behind the modal with a pending style; on success they are replaced with server copies; skipped items are listed in the success notice.
- Empty: "This circular has no checked obligations yet. Obligations appear here after their quotes are checked."

**Item screen (`/items/[itemId]`)**
Top to bottom (one column on phone; on desktop the left column is the work, the right column the source):
1. Title (obligation title), status badge (display status), internal code (inline edit), breadcrumb back to its register.
2. `SourceChangeBanner` when `source_change` is set (section 6.3), with its actions.
3. `SourceQuote`: the exact quote in `.quote` style, "Circular {ref}, page {n}", circular title, publication date, fingerprint "SHA-256 3f9a1c…" (tap copies the full hash), in-force tag. Buttons: "View on page {n}" (opens `PagePanel` in a side panel or full-screen sheet on phone, with `versionId = source.version_id`, the snapshot quote and boxes as highlight, `canEdit=false`; pages from `fetchDocumentPages(source.document_id, source.version_id)`), "Open circular" (link to `page_link`). Requirement description and applicability below.
4. Assignment: department picker, lead picker (members of that department first, then everyone), internal deadline (`DeadlineField`), regulatory deadline (read only) with deadline description. If the internal deadline is after the regulatory deadline, show a warning line "Your deadline is after the regulator's deadline." (do not block). Notes (textarea, saves on blur).
5. Status actions, only those allowed for this user now (`allowedItemMoves`): "Start" , "Send for sign-off" (disabled with the reason when tasks are not all approved or there is no evidence: "Approve all tasks first" / "Add at least one evidence file"), "Exempt" (reason modal), "Remove exemption", "Reopen" (reason modal). Exemption reason shown when exempted.
6. `SignoffBox` when the item is EVIDENCE_SUBMITTED: who sent it and when, "Approve as compliant" and "Send back" (comment required). Hidden when the user cannot sign off; replaced by the self-review line from 5.4 when that is why.
7. `TaskList`: each task with title, assignee, due date + days left, priority tag, status badge. "Add task" opens `TaskEditor` (title, description, assignee picker, due date defaulting to the item's effective deadline, priority). Each task expands to show: status toggle for the assignee, edit, cancel (reason), `EvidenceList`, `EvidenceUpload`, `ReviewBox`.
8. `EvidenceUpload`: a file button and drag-and-drop zone (drop zone hidden on phones), notes field. Checks type and size in the browser first with the same table as section 7 (instant error, no request). While uploading: a row with the file name and a progress bar; the task badge already shows "Submitted". On failure: the row turns red with the reason and a "Try again" button; the task badge goes back.
9. `EvidenceList`: file name, size, short hash, who, when, notes, Download, Withdraw (uploader, before approval; reason modal). Withdrawn files are struck through with who/when.
10. `ReviewBox` when a task is SUBMITTED: Approve, Ask for changes, Reject (comments required for the last two). Shows past reviews with decision, reviewer, comment, time.
11. `HistoryList`: the item's audit events (A1 with `entity_id`), newest first, plain sentences ("Farhan changed the lead from — to Nusrat", "Rafi uploaded board-minutes.pdf (sha 3f9a1c…)"). "Show more" pages with `before`. New events from this user's own actions are added to the list at once (optimistic entry, replaced on reload).
- Loading: skeleton for the quote block and three task rows. Not found / other org: "This item does not exist in this workspace." with a link to Registers.

**Tasks (`/tasks`)**
- Tabs: "Mine" (default for ANALYST and DEPARTMENT_LEAD), "My department" (DEPARTMENT_LEAD), "All" (others default).
- Filters: status, overdue only, priority. Rows: title, item title (link), due date + days left, priority, status, assignee. Status toggle inline for own tasks.
- Empty: "No tasks here." For "Mine": "Nothing assigned to you. Enjoy the quiet."

**Review (`/review`)**
- Two sections: "Evidence to review" (tasks SUBMITTED that this user may review and did not work on) and "Items waiting for sign-off" (EVIDENCE_SUBMITTED items this user may sign off). Each row opens the item scrolled to the right block (`#task-{id}` / `#signoff`).
- Rows the user cannot decide on because of 5.4 are listed under "Waiting for another reviewer" (greyed).
- A decision made on the item screen removes the row here at once (selector).
- Empty: "Nothing waiting for your review."

**Report (`/report`)**
- Loads A2 json (with an optional register picker). Layout made for A4 printing: org name, "Compliance status as of {date}", generated by and when; totals; by-department table; overdue list; upcoming 30 days; circular-changed list; then the full item table (circular ref + page, obligation, department, lead, deadline, status, signed off by).
- Buttons (hidden in print): "Print or save as PDF" (`window.print()`), "Download CSV" (A2 csv via blob download).
- Print CSS in `globals.css` under `@media print`: hide `AppHeader`, `WorkspaceNav` and buttons; black on white; avoid breaking table rows across pages (`break-inside: avoid`); show full quotes.
- The page reads live from the store too: if an item changes in another tab while the report is open, the numbers update (the json load seeds the store; the report renders from selectors with the register filter).

**Settings (`/settings`)**
- Departments: list (name, head, members, open items), add, rename inline, set head (member picker), delete (ORG_ADMIN; disabled with "Move its items first" when it has items).
- Members: list (name, email, role select, department select, status). Role and department save on change. Suspend / reactivate. "Add member by email" form (email, role, department). Errors in plain words (the 404 text from O4).
- Changes show at once everywhere: the lead pickers on every item list use these members, so a new member can be picked straight away.

**Audit log (`/audit`)**
- Table (cards on phone): time, who, action in plain words, what (link to the item), before → after summary. Filters: action, person, date range (client paging with `before`). Read only.

### 8.4 Wording for statuses (badges)

| Value | Label | Tone |
|---|---|---|
| NOT_STARTED | Not started | muted |
| IN_PROGRESS | In progress | info |
| OVERDUE | Overdue | bad |
| EVIDENCE_SUBMITTED | Waiting sign-off | warn |
| COMPLIANT | Compliant | ok |
| EXEMPTED | Exempted | muted |
| task PENDING | To do | muted |
| task IN_PROGRESS | In progress | info |
| task SUBMITTED | Evidence submitted | warn |
| task APPROVED | Approved | ok |
| task REJECTED | Rejected | bad |
| task CANCELLED | Cancelled | muted |

Use the existing `Tag` / tone classes from `StatusBadge.tsx`.

---

## 9. Tests

### 9.1 Backend (pytest)

New files in `backend/app/tests/`. Use the existing `client` fixture style and `factories.py`. Add a helper `make_workspace(roles: dict)` in `factories.py` that creates an org, departments and one user per role and returns tokens.

`test_compliance_workspace.py`:
1. Add from circular: only VERIFIED obligations of the current version of a published shared circular are added; PENDING_REVIEW, unpublished, old-version and private-upload obligations are skipped with the right reasons.
2. Snapshot: the item keeps the exact quote, page number, version id and file SHA-256. Then delete the obligation (as re-analysis does) and check the item still reads correctly and `obligation_id` is NULL.
3. Re-analysis after a register item exists does not fail (run the analysis service with the mock provider on a document that has a register item).
4. Duplicate add to the same register is skipped; adding to a second register works.
5. Client `status` on item and task create is ignored.
6. Overdue: item with `internal_deadline` yesterday (Dhaka) and IN_PROGRESS shows `display_status=OVERDUE`; EVIDENCE_SUBMITTED with a past deadline does not; regulatory deadline is used when there is no internal one; `overdue=true` filter returns exactly the overdue ones. Freeze "today" by monkeypatching `compliance.rules.today_dhaka`.
7. State machine: every allowed move in 5.2 and 5.3 works; a sample of forbidden moves return 409; "Send for sign-off" is refused without evidence and while a task is not approved; automatic moves happen (task created → item IN_PROGRESS; evidence uploaded → task SUBMITTED; all evidence withdrawn → task back to IN_PROGRESS; sign-off rejected → item IN_PROGRESS).
8. Self-review: uploader cannot review the task (403), assignee cannot review, the person who sent the item for sign-off cannot sign it off, an uploader on any task cannot sign off the item; this holds for ORG_ADMIN and COMPLIANCE_HEAD. A different REVIEWER can.
9. Permissions: one test per row of the matrix in section 4 (parametrize by role), including DEPARTMENT_LEAD allowed on own department and refused on another department, ANALYST allowed only on assigned tasks, VIEWER refused on download.
10. Lock version: PATCH with a stale `lock_version` returns 409 with `current`.
11. Source change: create an item, then add a VERIFIED AMENDS relationship from another shared circular → `source_change.kind == "AMENDED"`; acknowledge → flag gone; add a REPEALS link → flag back with REPEALED. A link stated by a private upload does not flag. A new current version flags NEW_VERSION. A PENDING_REVIEW link does not flag.
12. Audit: each write in section 3 writes exactly one `AuditEvent` per changed record with the org id, actor and changed fields. A1 returns them; item history includes task and evidence events.
13. Report: json totals match the items; CSV has the BOM, the header row in the stated order, one row per item, and a cell starting with `=` is prefixed with `'`.
14. Evidence: size over the limit → 413 (set `EVIDENCE_MAX_BYTES` small with monkeypatch); wrong type → 415; `.pdf` without `%PDF-` → 415; stored path contains the org id; download headers include `nosniff`, `X-SHA256-Checksum`, and a safe `Content-Disposition` for a filename with quotes and Bangla characters; withdrawn evidence still downloads.

`test_compliance_isolation.py` (cross-org; two orgs A and B, a user in each, a superuser in neither):
1. B's user gets 403 on every A route (registers, items, tasks, evidence list, download, reviews, audit, report, members, departments, me). Parametrize over the route list.
2. B's user calling **B's** routes with **A's** ids (register, item, task, evidence, department, member, user as lead/assignee/head) gets 404 or 400, never A's data. Parametrize.
3. A superuser who is not a member of A gets 403 on A's compliance routes and A is not in their `/organizations/mine`.
4. A SUSPENDED member gets 403.
5. A's list endpoints never return B's rows (create data in both, list in A, assert all `organization_id == A`).
6. Evidence stored for A is under `evidence/{A}/...`; the same bytes uploaded in B get a different path.
7. The same file uploaded by A and B: each org's download returns its own record; B cannot download A's evidence id through B's path.

Update the old tests listed in 1.3.

Run: `.venv\Scripts\python.exe -m pytest -q` from the repo root. Expect 271 + your new tests passing, the same 6 failures and 1 error, nothing else. Then `git checkout -- backend/app/tests/fixtures`.

### 9.2 Browser checks (real browser, desktop and 375 px)

Start the backend and `npm run dev`. Seed data: use the demo org "ABC Bank PLC" from `backend/scripts/seed.py`, and add at least: one ORG_ADMIN, one COMPLIANCE_OFFICER, one DEPARTMENT_LEAD, one REVIEWER, one ANALYST user (sign up through the account modal, then add them by email in Settings). Use a published circular with verified obligations (run the mock analysis on a fixture circular if none exists locally).

Check each of these, at desktop width and at 375 px:
1. Add obligations from the circular screen. The register count on Registers and the dashboard tiles have already changed when you open them.
2. Change an item's department on the register view. The dashboard "By department" table and the item screen show it at once. Go back: the register row shows the new value.
3. Set an internal deadline in the past. The badge turns "Overdue" immediately on the item, the register row and the dashboard Overdue tile. Clear it: all go back.
4. Upload evidence as the ANALYST. The progress row shows; the task badge shows "Evidence submitted" at once; the Review tab badge of the REVIEWER (second browser profile or window) updates within 30 s or on focus.
5. As the uploader, open Review: the task is under "Waiting for another reviewer", approve buttons hidden.
6. As REVIEWER, approve the task, then sign off the item. Item becomes "Compliant" on every screen at once.
7. Force a failure (stop the backend, then change a status). The change shows, then rolls back with a plain error notice. Nothing else on the screen is reset.
8. Two tabs open on the same register: change a lead in one; the other updates at once (BroadcastChannel).
9. Add an AMENDS link to the source circular as platform admin and confirm it. The item shows the "Circular changed" banner after focus/refresh; "Mark as reviewed" clears it everywhere at once.
10. Report: numbers match the dashboard; Print preview hides navigation and buttons; CSV opens in Excel with Bangla readable.
11. Phone width: no sideways page scroll on any workspace screen; tabs scroll in their strip; modals open as bottom sheets; every button is at least 44 px tall; the page panel opens full-screen.
12. Dark mode toggle: every workspace screen is readable.
13. Browser console has no errors or React key warnings on any workspace screen.

Then `npm run build` and `npm run lint` in `frontend/`.

---

## 10. Build plan (do in order; verify each chunk before the next)

1. **Models and migration.** Sections 2.1–2.8. Factory changes from 1.3. Verify: pytest baseline unchanged; alembic upgrade/downgrade/upgrade on a copy of the dev DB.
2. **Foundations.** `get_workspace_membership` (no superuser bypass), `audit/service.py::record`, `compliance/permissions.py`, `compliance/rules.py` (today, overdue, signatures), Literal enums in schemas. Update the two old tests from 1.3. Verify: old compliance tests pass.
3. **Org endpoints** O1–O9. Tests for them plus isolation tests 1–4 for these routes.
4. **Item reads and snapshot.** `compliance/service.py::load_items`, I0, I1, I2, I3, I4, R1–R5, source change computation. Tests 1–6, 11.
5. **Item writes.** I5–I9 with the state machine and lock versions. Tests 7 (item part), 8 (sign-off part), 9, 10, 12.
6. **Tasks, evidence, reviews.** T1–T9, evidence hardening (section 7). Tests 7 (task part), 8 (task part), 14, and the full `test_compliance_isolation.py`.
7. **Audit and report.** A1, A2 (json, csv). Test 13 and the audit part of 12. Run the full pytest suite now.
8. **Frontend data layer.** `workspaceApi.ts`, `workspaceRules.ts`, `workspaceStore.ts` with preloading, selectors, optimistic writes, rollback, delta refresh, BroadcastChannel, midnight timer. Verify: `npm run build`, `npm run lint`.
9. **Workspace shell.** `/workspace`, layout, nav, AppHeader link, Settings (departments, members). Browser check: create a workspace, add departments and members, all lists update at once.
10. **Registers and adding.** Registers list, register view with filters and inline pickers, `AddToRegisterModal`, the CircularDetail button and "In your register" tag, `version` param on `/`. Browser checks 1–3.
11. **Item screen.** Source quote with page panel, assignment, status actions, tasks, evidence upload/list, reviews, sign-off, history, source-change banner. Browser checks 4–7, 9.
12. **Dashboard, Tasks, Review, Report, Audit pages.** Browser checks 5, 6, 8, 10.
13. **Phone and polish pass.** Browser checks 11–13 on every screen. Final full pytest run (then `git checkout -- backend/app/tests/fixtures`), `npm run build`, `npm run lint`. Check the diff against rule 5 of section 0. Do not commit.

---

## 11. Decisions for the product owner

Defaults are built as written above unless the owner says otherwise.

- **D1. Platform staff and bank data.** Default: platform superusers cannot open any bank's workspace or evidence unless the bank adds them as a member. Alternative: keep today's superuser bypass (read-only) for support. Banks will likely ask for the default in contracts.
- **D2. Recurring obligations** (monthly or quarterly returns). Default for this build: one item = one cycle; the frequency is shown but no new cycles are created. Later option: auto-create the next cycle's item or task after sign-off.
- **D3. Department leads reviewing their own department's evidence.** Default: allowed for task evidence (first check), but only REVIEWER, COMPLIANCE_HEAD or ORG_ADMIN can mark an item compliant. Stricter option: department leads cannot review at all.
- **D4. Board report format.** Default: printable page (browser "Save as PDF") plus CSV. A server-made, signed PDF can come later if boards or auditors require it.
- **D5. Evidence limits.** Default: 25 MB per file; PDF, PNG, JPG, DOCX, XLSX, CSV, TXT. Banks may want email files (.msg/.eml) or larger scans.
- **D6. Who can see evidence.** Default: every member except VIEWER can download every evidence file in the bank. Stricter option: only the item's department, compliance roles, reviewers and auditors.
- **D7. Alerts.** Not in this build. New-assignment, deadline-near and circular-changed alerts (email or in-app) depend on the open "alert channels" question in the business-purpose file.
