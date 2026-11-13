# Alerts: build spec

Status: ready to build. Written 2026-11-13.
Scope: feature 8 ("Alerts") in the business-purpose file at the repo root, on the existing FastAPI backend and Next.js frontend. It also delivers the alerts left out of `docs/specs/COMPLIANCE_WORKSPACE_SPEC.md` (its D7).
Read the business-purpose file (golden rule, personas), `DECISIONS.md` and `docs/specs/COMPLIANCE_WORKSPACE_SPEC.md` before you start. This spec does not change any decided item there.

---

## 0. Ground rules for the builder (read first)

1. **Instant, up-to-date UI is the top priority.** After any tap (mark read, mark all read, change a setting), every screen that shows that data must show the new state at once: the bell count, the bell panel, the inbox, the settings screen, and the screen you go back to. Never show old data until a refresh. Section 8 says how: one shared client store, optimistic updates, rollback on failure, a message to other tabs.
2. **Test every touched control in a real browser**, at desktop width and at phone width (375 px). Check that the control reacts at once and that every other screen and every other open tab showing the same data has already changed.
3. **Add tests** (section 9). No new pytest failures. The baseline is **317 pass, 6 fail, 1 error** (7 old known failures). After every pytest run, run `git checkout -- backend/app/tests/fixtures` (one old test rewrites a fixture PDF).
4. **Never send real email in tests.** Use the fake SMTP server or the monkeypatched transport in section 9. The test conftest already blocks non-local sockets; keep it that way.
5. `npm run build` and `npm run lint` (in `frontend/`) must pass.
6. Keep code, comments, UI text, email text, docs and test names free of any mention of how the analysis is produced (no tool or vendor names). Say "the analysis" when you must.
7. Do not commit or push.
8. Never send requests to bb.org.bd. Never print, log or return secrets (SMTP password, keys, tokens).
9. **Golden rule.** Alert text never makes a claim of its own. It names the circular (reference number and title, copied from the record) and links to it. Any quote shown is the stored exact quote, copied character for character, with its page number. No summaries, no "this means", no guessed impact.
10. Plain English in UI and email text. Short sentences.

---

## 1. Gap analysis

### 1.1 What already exists (and is reused)

| Area | File | What is there / how alerts use it |
|---|---|---|
| Settings | `backend/app/core/config.py` | `Settings` (pydantic-settings, env vars, `.env`). `SCHEDULER_ENABLED=False` and `VISION_WORKER_ENABLED=False` by default. `MONITOR_TIMEZONE="Asia/Dhaka"`, window 10:00-18:00 (the host PC is only on then). No SMTP settings, no public app URL. |
| App start | `backend/app/main.py` | `lifespan` runs `create_all`, starts `monitoring_scheduler` if `SCHEDULER_ENABLED`, starts `vision_worker` if `SCHEDULER_ENABLED or VISION_WORKER_ENABLED`. Routers mounted under `/api/v1`. A `ConflictError` handler returns 409 with `current`. |
| Background job pattern | `backend/app/modules/extraction/vision_jobs.py` (`VisionWorker`) | `start/stop/kick`, `asyncio.Event` wake-up, loop with timeout. Copy this pattern for the alerts worker. |
| Users | `backend/app/modules/identity/models.py`, `deps.py` | `User` (`email`, `full_name`, `is_active`, `is_superuser`). `get_current_user`, `get_current_superuser`. No platform "editor" role: platform admin = `is_superuser`. |
| Bank membership | `backend/app/modules/organizations/models.py`, `deps.py` | `OrganizationMember` (role, status ACTIVE/INVITED/SUSPENDED, `department_id`), `Department.head_user_id`. `get_workspace_membership` has no superuser bypass (compliance D1). |
| Roles and rules | `backend/app/modules/compliance/permissions.py`, `rules.py` | Role constants, `can_review_task`, `task_review_block`, `signoff_block`, `can_sign_off_role`. `rules.today_dhaka()` (tests monkeypatch it), `is_item_overdue`, `is_task_overdue`, `effective_deadline`, `ITEM_OVERDUE_STATUSES`, `TASK_OVERDUE_STATUSES`, `change_kind`, `change_text`. |
| Overdue | `compliance/rules.py`, `compliance/service.py::overdue_sql` | Overdue is **derived on read**, never stored. Nothing fires when an item becomes overdue. |
| Source change on items | `compliance/service.py` (`source_context`, `signature_for`, `current_source_change`) | Works out per item whether its circular was amended / replaced / repealed / withdrawn / has a new version, from VERIFIED shared-library links only (`bulk_in_force(db, ids, user=None)`), compared with `source_ack_signature`. Derived on read; nothing fires. |
| In-force status | `backend/app/modules/relationships/status.py` | `bulk_in_force`, `STATUS_BY_TYPE` (AMENDS→AMENDED, SUPERSEDES/REPLACES→REPLACED, REPEALS→REPEALED). |
| Link review | `backend/app/modules/relationships/router.py::review_relationship` | Superuser sets a link VERIFIED/REJECTED, writes an `AuditEvent`, commits. Changes in-force status. |
| Link targets | `backend/app/modules/relationships/linking.py::link_relationship_targets` | Fills `target_document_id` on links; commits. A VERIFIED link that just got its target also changes in-force status. |
| Compliance writes | `compliance/router.py`, `compliance/routes_tasks.py` | Task create/update (assignee), evidence upload (task → SUBMITTED), task review, item status (→ EVIDENCE_SUBMITTED), item sign-off, item PATCH (lead). Each writes `audit.record(...)` then `db.commit()`. |
| Audit helper | `backend/app/modules/audit/service.py` | `record()` adds a row in the caller's transaction, no commit. The alert `emit()` helper copies this style. |
| Publication | `backend/app/modules/sources/service.py` (lines ~401 backfill, ~569 archive re-check new version, ~730 `approve_and_ingest_discovery`), `backend/app/modules/analysis/service.py` (~302 `_persist_analysis`, ~410 `review_and_publish_analysis`), `analysis/pipeline.py` (~148) | Five places set `publication_status`. Published values all start with `PUBLISHED` (`PUBLISHED_MACHINE_PROCESSED`, `PUBLISHED_MACHINE_VERIFIED`, `PUBLISHED_HUMAN_REVIEWED`). |
| Document access | `backend/app/modules/documents/access.py` | Shared library = `owner_user_id IS NULL`. Private uploads are owner-only. |
| Review queues (admin) | `sources/models.py` (`SourceDiscovery.status == "VALIDATED"`), `documents/models.py` (`publication_status == "AWAITING_REVIEW"`, `DocumentPage.quality_status == "NEEDS_HUMAN_REVIEW"`), `relationships/models.py` (`verification_status == "PENDING_REVIEW"`) | The admin page (`frontend/app/admin/page.tsx`) shows these in tabs `queue`, `library`, `links`. No alert when they fill up. |
| Department codes | `institutions/models.py::InstitutionDepartment.code` (BRPD, DOS, FEPD, ...) | `Document.department_id` points here. Used for subscription filters. |
| Frontend auth | `frontend/services/api.ts` | Bearer token in `localStorage` (`regwatch_token`), `apiFetch`, `ApiError`, `AUTH_CHANGED_EVENT`, `getStoredUser()` (has `is_superuser`). **The token is sent in a header, so the browser's `EventSource` (server-sent events) cannot carry it.** |
| Store pattern | `frontend/services/workspaceStore.ts`, `relationshipsStore.ts` | Module-level state + `useSyncExternalStore`, `once()` load de-dup, `mutate()` with per-record rollback and `pending` counters, `BroadcastChannel("regwatch-workspace")`, `syncSessionUser()` clears state on sign-out, refresh on focus/visibility. |
| UI kit | `frontend/components/ui.tsx`, `StatusBadge.tsx` (`Tag`), `app/globals.css` | `Notice`, `Modal` (bottom sheet on phones), `ModalHeader`, `SkeletonLine`, `EmptyState`; classes `.btn .btn-primary .btn-secondary .btn-ghost .field .field-label .meta .panel .quote .refno .section-title`. Icons: `lucide-react`. |
| Header | `frontend/components/AppHeader.tsx` | Nav (Circulars, Search, Workspace, Admin), account button, theme toggle. No bell. |
| Deep-link targets | `frontend/app/page.tsx` (`/?doc=<id>&page=<n>`), `app/workspace/[orgId]/items/[itemId]/page.tsx` (tasks have `id="task-<id>"`, scroll code in `TaskList.tsx`), `app/workspace/[orgId]/registers/[registerId]/page.tsx` (filter `?changed=1` via `ItemFilters.tsx`), `app/workspace/[orgId]/review/page.tsx` | Links for alerts. The admin page keeps its tab in React state only (needs a `?tab=` param, section 7.4). |

### 1.2 What is missing (all of it is new)

**Backend**
1. No alert tables: no event outbox, no per-user inbox, no preferences, no email outbox, no delivery log.
2. No place where events are emitted. Nothing calls anything when a circular is published, a link is verified, a task is assigned, evidence is submitted or decided, or a deadline nears.
3. No email code. No SMTP settings. Nothing in `requirements.txt` sends mail (stdlib `smtplib` + `email` is enough; section 5).
4. No alerts worker. No digest.
5. No endpoints for an inbox, unread count, read state, preferences, test email.
6. `Settings` has no public app URL for links in emails.

**Frontend**
1. No bell, no inbox screen, no settings screen, no alerts store.
2. The admin page does not read `?tab=` so an alert cannot open the right admin tab.

**Business-purpose open question touched:** "Alert channels (email, SMS, WhatsApp, in-app) and how fast instant must be." This spec builds in-app + email only, with "instant" = the bell updates within the poll interval (15 s default) and immediately across your own tabs. SMS and WhatsApp are out of scope (decision A9).

---

## 2. How it works (one paragraph)

Code that changes something worth an alert calls `await alerts.emit(db, ...)` **inside its own transaction**. That adds one row to `alert_events` (the fan-out outbox), with a unique `dedupe_key`. After commit, a dispatcher turns each pending event into per-user rows in `alert_notifications` (the inbox), applying isolation, each user's preferences and filters. If email is set up and the user wants email right away, the dispatcher also adds a row to `email_outbox`. A worker sends outbox rows with retry and backoff and logs every attempt in `email_delivery_attempts`. Things that are **derived on read** (deadline near, overdue, circular changed, admin queues) are turned into events by idempotent "sweep" functions that run in the worker and also, throttled, when a user's browser polls the unread count. So the inbox works fully with the worker off; only email needs the worker.

```
request / job ──emit()──> alert_events (PENDING) ──dispatch──> alert_notifications (inbox)
                                 ^                                   └──> email_outbox ──worker──> SMTP
sweeps (deadlines, source changes, admin queues, publish safety net) ┘                 └──> email_delivery_attempts
```

---

## 3. Data model

New module `backend/app/modules/alerts/` with `models.py`, `kinds.py`, `emit.py`, `recipients.py`, `dispatch.py`, `sweeps.py`, `mailer.py`, `templates.py`, `digest.py`, `worker.py`, `prefs.py`, `schemas.py`, `router.py`, `__init__.py`.
Register the models in `backend/app/database/models.py` (import and `__all__`), so `create_all` and tests see them.
All tables use `Base` (`id`, `created_at`, `updated_at`).

### 3.1 `alert_events` (model `AlertEvent`): the fan-out outbox

| Column | Type | Notes |
|---|---|---|
| `kind` | String(48), not null, index | One of the kinds in 3.6 |
| `dedupe_key` | String(255), not null, **unique** | Same real-world event → same key → never twice |
| `organization_id` | GUID FK organizations.id CASCADE, nullable, index | Set for bank events. NULL for library and admin events |
| `document_id` | GUID FK documents.id CASCADE, nullable, index | The circular the event is about, if any |
| `entity_type` | String(64), nullable | `compliance_item`, `compliance_task`, `document`, `admin_queue` |
| `entity_id` | GUID, nullable | |
| `actor_user_id` | GUID FK users.id SET NULL, nullable | Never alerted about their own action |
| `recipient_user_ids` | JSON, nullable | Fixed recipients (bank events). NULL = worked out at dispatch (library, admin) |
| `payload` | JSON, not null, default {} | Everything the text needs, copied at emit time (3.7) |
| `status` | String(16), not null, default `PENDING`, index | `PENDING`, `DISPATCHED`, `SUPPRESSED`, `FAILED` |
| `dispatched_at` | DateTime(tz), nullable | |
| `attempts` | Integer, not null, default 0 | Dispatch attempts |
| `last_error` | String(500), nullable | Short, no secrets |

Index: `ix_alert_events_status_created` on (`status`, `created_at`).

### 3.2 `alert_notifications` (model `AlertNotification`): the inbox

| Column | Type | Notes |
|---|---|---|
| `user_id` | GUID FK users.id CASCADE, not null, index | |
| `event_id` | GUID FK alert_events.id CASCADE, nullable, index | |
| `organization_id` | GUID FK organizations.id CASCADE, nullable, index | Copied from the event |
| `kind` | String(48), not null | |
| `group` | String(32), not null | Preference group (3.6) |
| `dedupe_key` | String(255), not null | Copied from the event |
| `severity` | String(8), not null, default `info` | `info`, `warn`, `bad` |
| `title` | String(300), not null | Built by `templates.py` |
| `body` | Text, not null | Built by `templates.py` |
| `detail` | Text, nullable | In-app only extra text (reviewer comments). Never emailed (decision A5) |
| `link` | String(512), not null | App-relative path, starts with `/` |
| `document_id` | GUID FK documents.id SET NULL, nullable | |
| `quote_text` | Text, nullable | Exact stored quote, copied unchanged |
| `quote_page_number` | Integer, nullable | Page of that quote |
| `quote_document_id` | GUID FK documents.id SET NULL, nullable | Circular the quote is from |
| `in_app` | Boolean, not null, default true | False = kept only for email/digest bookkeeping; hidden from the inbox and counts |
| `email_mode` | String(8), not null, default `OFF` | `OFF`, `INSTANT`, `DIGEST`, as chosen at dispatch time |
| `emailed_at` | DateTime(tz), nullable | Set when put into an outbox message |
| `read_at` | DateTime(tz), nullable | |

Constraint: `UniqueConstraint("user_id", "dedupe_key", name="uq_alert_notification_user_key")`.
Index: `ix_alert_notifications_user_inbox` on (`user_id`, `in_app`, `read_at`, `created_at`).

### 3.3 `alert_preferences` (model `AlertPreference`)

| Column | Type | Notes |
|---|---|---|
| `user_id` | GUID FK users.id CASCADE, not null, **unique** | No row = all defaults |
| `channels` | JSON, not null, default {} | `{group: {"in_app": bool, "email": "OFF"|"INSTANT"|"DIGEST"}}`. Missing groups use defaults (3.6) |
| `email_enabled` | Boolean, not null, default true | Master switch for this user's email |
| `library_department_codes` | JSON, not null, default [] | e.g. `["BRPD","DOS"]`. Empty = all |
| `library_document_types` | JSON, not null, default [] | e.g. `["CIRCULAR","GUIDELINE"]`. Empty = all |
| `library_keywords` | JSON, not null, default [] | Up to 20 words or phrases, each 2-60 chars. Empty = all |
| `lock_version` | Integer, not null, default 1, server_default "1" | Conflict check on save |

### 3.4 `email_outbox` (model `EmailOutbox`)

| Column | Type | Notes |
|---|---|---|
| `user_id` | GUID FK users.id CASCADE, nullable, index | |
| `organization_id` | GUID, nullable | For masking in the admin log |
| `to_address` | String(255), not null | The user's email at queue time |
| `kind` | String(8), not null | `INSTANT`, `DIGEST`, `TEST` |
| `dedupe_key` | String(255), not null, **unique** | `instant:{notification_id}`, `digest:{user_id}:{YYYY-MM-DD}`, `test:{uuid4}` |
| `notification_ids` | JSON, not null, default [] | |
| `subject` | String(300), not null | |
| `text_body` | Text, not null | |
| `html_body` | Text, not null | |
| `status` | String(12), not null, default `PENDING`, index | `PENDING`, `SENDING`, `SENT`, `FAILED`, `EXPIRED` |
| `attempts` | Integer, not null, default 0 | |
| `next_attempt_at` | DateTime(tz), not null, index | |
| `locked_until` | DateTime(tz), nullable | Lease while `SENDING` |
| `last_error` | String(500), nullable | Redacted (5.4) |
| `smtp_message_id` | String(255), nullable | |
| `sent_at` | DateTime(tz), nullable | |

Index: `ix_email_outbox_due` on (`status`, `next_attempt_at`).

### 3.5 `email_delivery_attempts` (model `EmailDeliveryAttempt`): the delivery log

| Column | Type |
|---|---|
| `outbox_id` | GUID FK email_outbox.id CASCADE, not null, index |
| `attempt_no` | Integer, not null |
| `started_at`, `finished_at` | DateTime(tz) |
| `outcome` | String(8): `SENT`, `RETRY`, `FAILED` |
| `smtp_code` | Integer, nullable |
| `error` | String(500), nullable (redacted) |

### 3.6 Kinds and preference groups (`alerts/kinds.py`)

Preferences are per **group**. Each kind belongs to one group. Defaults are used when the user has no setting for a group.

| Group | Label in UI | Kinds | Who can see the group in settings | Default in-app | Default email |
|---|---|---|---|---|---|
| `library` | New circulars | `CIRCULAR_PUBLISHED` | everyone | on | DIGEST |
| `source_change` | A circular in my bank's register changed | `REGISTER_SOURCE_CHANGED` | members of any bank | on | INSTANT |
| `assigned` | Work assigned to me | `TASK_ASSIGNED`, `ITEM_LEAD_ASSIGNED`, `TASK_CANCELLED` | members of any bank | on | INSTANT |
| `review_waiting` | Evidence or sign-off waiting for me | `EVIDENCE_AWAITING_REVIEW`, `ITEM_AWAITING_SIGNOFF` | members of any bank | on | INSTANT |
| `my_work_decided` | My evidence or item was decided | `TASK_REVIEWED`, `ITEM_SIGNOFF_DECIDED` | members of any bank | on | INSTANT |
| `due_soon` | Deadline coming up | `ITEM_DUE_SOON`, `TASK_DUE_SOON` | members of any bank | on | DIGEST |
| `overdue` | Overdue | `ITEM_OVERDUE`, `TASK_OVERDUE` | members of any bank | on | DIGEST |
| `admin_queue` | Review queues (platform staff) | `ADMIN_QUEUE` | superusers only | on | DIGEST |

Put the table in code as one dict `GROUPS` and one dict `KIND_GROUP`. Validate every API input against them.

### 3.7 Payload fields per kind

Copied at emit time from the database (never from user input or analysis text other than the stored quote):
- Circular fields: `document_id`, `reference_number`, `title`, `document_type`, `department_code`, `publication_date`.
- Bank fields: `organization_name`, `item_id`, `item_title` (= `obligation_title`), `register_id`, `task_id`, `task_title`, `due_date`/`deadline`, `days_left`, `actor_name`, `decision`, `comments` (in-app only).
- Source change: `change_kind`, `by_document_id`, `by_reference_number`, `by_title`, `link_quote` (the VERIFIED link's `supporting_quote`, exact), `link_quote_page` (page number of `source_page_id`), `item_ids` (max 50), `register_ids`, `item_count`.
- Admin queue: `queue`, `count`.

### 3.8 Alembic migration

File: `backend/migrations/versions/b9d1f3a5c7e8_alerts.py`
`revision = "b9d1f3a5c7e8"`, `down_revision = "a3c5e7f9b1d4"`.
Verified on 2026-11-13: `a3c5e7f9b1d4_compliance_workspace.py` is the head (it revises `f1b3d5a7c9e2`, and no file revises it). Re-check with `alembic heads` before you start; if the head moved, chain onto the new head.

Copy the style of `a3c5e7f9b1d4`: `_has_table(name)` / `_columns(table)` helpers so it is safe to re-run (the app's `create_all` at start-up may already have made the tables), `GUID = backend.app.database.base.GUID`.

`upgrade()`:
1. Create the five tables with their constraints and indexes, each only if missing.
2. **Backfill the "already announced" marker** so turning alerts on never floods everyone with old circulars: for every document with `owner_user_id IS NULL` and `publication_status LIKE 'PUBLISHED%'`, insert an `alert_events` row `kind='CIRCULAR_PUBLISHED'`, `dedupe_key='CIRCULAR_PUBLISHED:{document_id}'`, `status='SUPPRESSED'`, `payload={}`, skipping keys that exist. Use a Python loop over a `SELECT` (works on SQLite and PostgreSQL); generate ids with `uuid.uuid4()`, timestamps with `datetime.now(timezone.utc)`.

`downgrade()`: drop the five tables (attempts, outbox, notifications, preferences, events, in that order).

Check it: copy `data/regwatch.db` to the scratch folder, point `DATABASE_URL` and `SYNC_DATABASE_URL` at the copy, run `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` from the repo root. All three must succeed, and after the last one `SELECT count(*) FROM alert_events WHERE status='SUPPRESSED'` equals the number of published shared circulars.

---

## 4. Events: where each one is emitted

### 4.1 The emit helper (`alerts/emit.py`)

```python
async def emit(db, *, kind, dedupe_key, organization_id=None, document_id=None,
               entity_type=None, entity_id=None, actor_user_id=None,
               recipient_user_ids=None, payload=None) -> Optional[AlertEvent]
```
- Validates `kind` against `KIND_GROUP`.
- Returns `None` without adding anything if a row with that `dedupe_key` exists (one `SELECT`), or if `recipient_user_ids` is an empty list after removing `actor_user_id`.
- Adds the row (`status="PENDING"`) in the caller's transaction. No commit. Same as `audit.record`.
- Inserts inside `async with db.begin_nested():` and catches `IntegrityError` (a race with another process) so the caller's transaction never fails because of an alert.
- Marks the session so that **after commit** the dispatcher is kicked: on first use per session, `event.listen(db.sync_session, "after_commit", _kick, once=True)` where `_kick` calls `alerts.worker.kick_dispatch()`. `kick_dispatch()` does nothing when `settings.ALERTS_KICK_AFTER_COMMIT` is false (tests), else `asyncio.get_running_loop().create_task(dispatch_in_new_session())`. Wrap in try/except and log at warning level; never raise.
- **Emitting must never break the main action.** Every hook call site wraps the call in `try/except Exception` and logs `logger.warning("Alert not recorded: %s", type(e).__name__)`.

`dispatch_in_new_session()` opens `AsyncSessionLocal()`, calls `dispatch_pending(session)`, commits, and closes. It holds a module-level `asyncio.Lock` so two dispatches in one process never overlap.

### 4.2 Library: a new circular is published

Helper: `async def circular_published(db, doc: Document)` in `emit.py`. It does nothing unless `doc.owner_user_id is None` **and** `str(doc.publication_status).startswith("PUBLISHED")`. Then `emit(kind="CIRCULAR_PUBLISHED", dedupe_key=f"CIRCULAR_PUBLISHED:{doc.id}", document_id=doc.id, entity_type="document", entity_id=doc.id, payload=<circular fields 3.7>)`. Once per circular, ever (a later re-publish or new version does not re-announce it).

Call it **before the commit** at each place that sets a published status:

| File | Where | Note |
|---|---|---|
| `backend/app/modules/sources/service.py` | backfill, right after `doc.publication_status = "PUBLISHED_MACHINE_PROCESSED"` (~line 401) | |
| `backend/app/modules/sources/service.py` | `approve_and_ingest_discovery`, after `doc.publication_status = "PUBLISHED_MACHINE_PROCESSED"` (~line 730) | |
| `backend/app/modules/analysis/service.py` | `_persist_analysis`, after `doc.publication_status = ...` (~line 302) | Only fires if the new status is published |
| `backend/app/modules/analysis/service.py` | `review_and_publish_analysis`, after `doc.publication_status = decision` (~line 410) | Fires for `PUBLISHED_HUMAN_REVIEWED` |

Not here: the archive re-check (~line 569) stores a **new version** of a known circular. That is a source change for registers (4.3), not a new circular.

**Safety net (sweep, 6.1):** `sweep_published(db)` finds shared documents with a published status, `updated_at` in the last `ALERTS_PUBLISH_SWEEP_HOURS` (48) hours, and no `alert_events` row with key `CIRCULAR_PUBLISHED:{id}`, and emits for each. This catches any future code path that publishes without calling the helper. The 48-hour window plus the migration backfill stop floods on databases made by `create_all`.

**Recipients (worked out at dispatch):** every active user (`User.is_active`) whose `library` group is on (in-app or email), and whose filters match:
- `library_department_codes` empty, or the circular's department code is in it;
- `library_document_types` empty, or its `document_type` is in it;
- `library_keywords` empty, or any keyword is found (case-insensitive, after Unicode NFC) in `reference_number + " " + title + " " + (title_bn or "")`.
All non-empty filter groups must match (AND across groups, OR inside a group).

Before dispatching, re-load the document. If it is now private, missing, or not published, set the event `SUPPRESSED`.

**Private uploads never alert anyone,** including their owner: the helper and the sweep both require `owner_user_id IS NULL`.

### 4.3 Bank: a circular in my bank's register changed

Sweep function `ensure_source_change_events(db, organization_id)` in `sweeps.py`:
1. Load the org's items with `status != "EXEMPTED"` and a `source_document_id`. Use `compliance.service.source_context(db, doc_ids)` and `current_source_change(item, ctx)` / `signature_for(item, ctx)`. These already use only VERIFIED links stated by **shared-library** circulars (`bulk_in_force(..., user=None)`), so a private upload never changes a bank's register.
2. Keep items whose `current_source_change` is not None (so items already "marked as reviewed" for this signature do not alert).
3. Group them by (`source_document_id`, current signature). For each group, emit `REGISTER_SOURCE_CHANGED` with `dedupe_key=f"SOURCE_CHANGED:{org_id}:{source_document_id}:{signature}"`. A new amending circular gives a new signature, so a new alert. The same state never alerts twice.
4. Payload: circular fields of the source, `change_kind`, the "by" circular fields, the item ids/register ids/count. If the change comes from a link (AMENDED / REPLACED / REPEALED), load the VERIFIED `DocumentRelationship` from the "by" circular to the source circular whose type maps to that status (`STATUS_BY_TYPE`), and copy its `supporting_quote` exactly into `link_quote` and the page number of `source_page_id` into `link_quote_page`. If there are several, take the newest by `reviewed_at`. If none is found, leave the quote out (never make one up).
5. Recipients (fixed at emit time): ACTIVE members of the org with role ORG_ADMIN, COMPLIANCE_HEAD or COMPLIANCE_OFFICER; plus the `assigned_lead_id` of each affected item; plus ACTIVE DEPARTMENT_LEAD members whose `department_id` equals an affected item's `department_id`. Remove duplicates.

When it runs:
- **Hook, right after the change is committed** (inline, awaited, wrapped in try/except; call `alerts.sweeps.library_changed(db, doc_ids)` which finds the orgs that have items whose `source_document_id` is in `doc_ids` and runs `ensure_source_change_events` for each, then commits):

| File | Where | `doc_ids` |
|---|---|---|
| `relationships/router.py::review_relationship` | after `await db.commit()` | `[rel.target_document_id]` if set |
| `relationships/linking.py::link_relationship_targets` | after its commit, when `linked > 0` | the target ids it just set (collect them in a list) |
| `analysis/service.py::_persist_analysis` | after the commit and the linking call | targets of the document's relationships, plus `doc.id` |
| `analysis/service.py::review_and_publish_analysis` | after the commit, when `decision` is `WITHDRAWN` or `SUPERSEDED` | `[doc.id]` |
| `sources/service.py` archive re-check | after the commit that stored the new version | `[doc_id]` |

- **Worker sweep** for every active org (6.1), and the **on-poll sweep** for the user's own orgs (6.2). These catch anything a hook missed.

### 4.4 Bank: work assigned to me

All emitted before the commit in the same request, with `organization_id`, `actor_user_id=membership.user_id`, `recipient_user_ids=[<the person>]`. Skip when the person is the actor.

| Kind | File / function | When | `dedupe_key` |
|---|---|---|---|
| `TASK_ASSIGNED` | `routes_tasks.py::create_task` | `payload.assigned_to_user_id` set | `TASK_ASSIGNED:{task.id}:{assignee}:{task.lock_version}` |
| `TASK_ASSIGNED` | `routes_tasks.py::update_task` | `assigned_to_user_id` changed to a non-null user | same pattern (after `bump(task)`) |
| `ITEM_LEAD_ASSIGNED` | `compliance/router.py::create_compliance_item` | `assigned_lead_id` set | `ITEM_LEAD_ASSIGNED:{item.id}:{lead}:{item.lock_version}` |
| `ITEM_LEAD_ASSIGNED` | `compliance/router.py::update_item` | `assigned_lead_id` changed to a non-null user | same pattern (after `bump(item)`) |
| `TASK_CANCELLED` | `routes_tasks.py::cancel_task` | task had an assignee | `TASK_CANCELLED:{task.id}:{task.lock_version}` |

`lock_version` is in the key so a real second assignment (A → B → A) alerts again, but a retried request does not.

### 4.5 Bank: evidence or sign-off waiting for me

| Kind | File / function | When | Recipients | `dedupe_key` |
|---|---|---|---|---|
| `EVIDENCE_AWAITING_REVIEW` | `routes_tasks.py::submit_task_evidence` | the task moved to SUBMITTED in this request | ACTIVE members for whom `perms.can_review_task(m, item)` is true and `perms.task_review_block(m.user_id, task, evidence)` is None, limited to roles COMPLIANCE_HEAD, REVIEWER and DEPARTMENT_LEAD (own department). If that set is empty, ORG_ADMIN members who are not blocked. | `EVIDENCE_AWAITING_REVIEW:{task.id}:{task.lock_version}` |
| `ITEM_AWAITING_SIGNOFF` | `compliance/router.py::change_item_status` | `to == "EVIDENCE_SUBMITTED"` succeeded | ACTIVE COMPLIANCE_HEAD and REVIEWER members with `perms.signoff_block(...)` None; if empty, unblocked ORG_ADMIN members | `ITEM_AWAITING_SIGNOFF:{item.id}:{item.lock_version}` |

Helper `recipients.reviewers_for_task(db, org_id, task, item)` and `recipients.signers_for_item(db, org_id, item)` in `alerts/recipients.py`, using the functions in `compliance/permissions.py` so the rules stay in one place.

### 4.6 Bank: my evidence or item was decided

| Kind | File / function | Recipients | `dedupe_key` |
|---|---|---|---|
| `TASK_REVIEWED` | `routes_tasks.py::review_task` (after the review row is flushed) | uploaders of the non-withdrawn evidence on the task, plus the task assignee, minus the reviewer | `TASK_REVIEWED:{review.id}` |
| `ITEM_SIGNOFF_DECIDED` | `compliance/router.py::sign_off_item` | the person in `item.submitted_for_signoff_by_user_id` **read before `move_item` clears it**, plus the item lead, minus the reviewer | `ITEM_SIGNOFF:{review.id}` |

Payload carries `decision` and `comments`. Comments go into the notification's `detail` (in-app only).

### 4.7 Bank: deadline coming up, and overdue

**Choice: sweeps that turn the derived state into events, run by the worker and, throttled, on the user's poll.** Justification:
- Overdue is derived on read (compliance spec 5.1) and must stay that way. So something has to look at deadlines on a clock.
- A worker-only design fails in the common setup: `SCHEDULER_ENABLED` is off in dev and on all but one process, and the host PC is only on 10:00-18:00. Deadline alerts would silently never appear.
- A read-only design (compute alerts when the inbox loads, store nothing) cannot send email to people who do not open the app, and cannot mark an alert read.
- The hybrid stores one row per real event (so read state and email work), uses a `dedupe_key` that includes the deadline date (so running it many times is harmless and an edited deadline alerts again), and needs no job for the in-app inbox.

`ensure_deadline_events(db, organization_id, today)` in `sweeps.py`, with `today = compliance.rules.today_dhaka()`:

Items: `status in rules.ITEM_OVERDUE_STATUSES`, effective deadline (`coalesce(internal_deadline, regulatory_deadline)`) not null and `<= today + max(ALERTS_DUE_SOON_DAYS)`. One SQL query using `compliance.service.eff_deadline_sql()`.
- Overdue (`deadline < today`): emit `ITEM_OVERDUE`, key `ITEM_OVERDUE:{item.id}:{deadline}`.
- Else `days_left = (deadline - today).days`. Thresholds come from `ALERTS_DUE_SOON_DAYS` (default `"7,1"`). Take the **smallest** threshold `t` with `days_left <= t`. Emit `ITEM_DUE_SOON`, key `ITEM_DUE_SOON:{item.id}:{deadline}:{t}`. (First seen at 1 day left: only the 1-day alert, not both.)
- Recipients for due-soon: the item lead; if none, the department head (`Department.head_user_id`) if ACTIVE in the org; if none, ACTIVE COMPLIANCE_HEAD members.
- Recipients for overdue: the item lead, the department head, and all ACTIVE COMPLIANCE_HEAD members (decision A6).

Tasks: `status in rules.TASK_OVERDUE_STATUSES`, `due_date <= today + max(threshold)`, item not COMPLIANT or EXEMPTED.
- `TASK_OVERDUE` key `TASK_OVERDUE:{task.id}:{due_date}`; `TASK_DUE_SOON` key `TASK_DUE_SOON:{task.id}:{due_date}:{t}`.
- Recipients: the assignee; if none, the item lead.

All recipients must be ACTIVE members of the org (check in one query). No `actor_user_id` (the system is the actor).

### 4.8 Admin: items waiting in the review queues

`ensure_admin_queue_events(db, today)` in `sweeps.py`. Four counts, shared library only:

| `queue` | Count | Link |
|---|---|---|
| `discoveries` | `SourceDiscovery.status == "VALIDATED"` | `/admin?tab=queue` |
| `analyses` | shared documents with `publication_status == "AWAITING_REVIEW"` | `/admin?tab=library` |
| `links` | `DocumentRelationship.verification_status == "PENDING_REVIEW"` whose source document is shared | `/admin?tab=links` |
| `pages` | `DocumentPage.quality_status == "NEEDS_HUMAN_REVIEW"` on versions of shared documents | `/admin?tab=library` |

For each queue with count > 0, emit `ADMIN_QUEUE` with key `ADMIN_QUEUE:{queue}:{today}` (at most one per queue per Dhaka day). Recipients: worked out at dispatch = all active superusers. Text gives the count at that moment.

---

## 5. Email

### 5.1 Settings (add to `core/config.py`, and to `.env.example` and `backend/.env.example` with empty values and one-line comments)

| Setting | Default | Meaning |
|---|---|---|
| `SMTP_HOST` | `None` | Empty = email is off |
| `SMTP_PORT` | `587` | |
| `SMTP_USERNAME` | `None` | Optional |
| `SMTP_PASSWORD` | `None`, type `Optional[SecretStr]` | Never logged or returned. `SecretStr` keeps it out of `repr` |
| `SMTP_FROM` | `None` | Sender address. Empty = email is off |
| `SMTP_FROM_NAME` | `"RegWatch Bangladesh"` | |
| `SMTP_TLS_MODE` | `"starttls"` | `starttls`, `ssl`, or `none`. Validate with a `Literal` |
| `SMTP_TIMEOUT_SECONDS` | `20` | |
| `APP_PUBLIC_URL` | `"http://localhost:3000"` | Base for links in emails. No trailing slash |
| `ALERTS_WORKER_ENABLED` | `False` | Run the alerts worker here even when `SCHEDULER_ENABLED` is off |
| `ALERTS_KICK_AFTER_COMMIT` | `True` | Dispatch right after a commit. Tests set it false |
| `ALERTS_WORKER_POLL_SECONDS` | `30` | |
| `ALERTS_SWEEP_MINUTES` | `15` | Worker sweep interval |
| `ALERTS_ON_POLL_SWEEP_MINUTES` | `10` | Throttle for sweeps run from a user's poll, per org |
| `ALERTS_DUE_SOON_DAYS` | `"7,1"` | Parsed to a sorted list of ints, each 0-90 |
| `ALERTS_DIGEST_TIME` | `"10:30"` | Dhaka time. Inside the 10:00-18:00 window on purpose |
| `ALERTS_EMAIL_MAX_ATTEMPTS` | `6` | |
| `ALERTS_EMAIL_MAX_AGE_HOURS` | `48` | Older unsent mail becomes EXPIRED (the inbox still has it) |
| `ALERTS_PUBLISH_SWEEP_HOURS` | `48` | Safety-net window (4.2) |
| `ALERTS_RETENTION_DAYS` | `180` | Notifications older than this are deleted by the worker |

`email_configured()` in `mailer.py` returns `bool(settings.SMTP_HOST and settings.SMTP_FROM)`.
In production (`settings.is_production`) with `SMTP_TLS_MODE == "none"` and a host other than `localhost`/`127.0.0.1`, `email_configured()` returns False and start-up logs one warning ("Email is off: plain SMTP is only allowed to a local relay."). This stops a password being sent in clear text.

In `tests/conftest.py` add, next to the other `os.environ` lines: `SMTP_HOST=""`, `SMTP_FROM=""`, `ALERTS_KICK_AFTER_COMMIT="false"`, `ALERTS_WORKER_ENABLED="false"`.

### 5.2 Rules when email is off

- No `email_outbox` row is ever created (so turning SMTP on later does not send a backlog of old mail).
- Notifications still get `email_mode` from preferences, but `emailed_at` stays NULL and nothing is sent.
- No SMTP connection is opened, no error is logged, no error is shown. The inbox works the same.
- The settings screen shows "Email is not set up on this server. You will see alerts here in the app." and disables the email choices.
- `POST /alerts/admin/test-email` returns 409 "Email is not set up. Set SMTP_HOST and SMTP_FROM on the server."

### 5.3 Library and sending (`alerts/mailer.py`)

Use the **standard library only**: `smtplib`, `ssl`, `email.message.EmailMessage`, `email.utils` (`formataddr`, `make_msgid`, `formatdate`). Nothing new in `requirements.txt`. (`aiosmtplib` is not installed; `smtplib` in a thread is enough for a few hundred emails a day.)

- `build_message(to, subject, text, html) -> EmailMessage`: `From = formataddr((SMTP_FROM_NAME, SMTP_FROM))`, `To`, `Subject`, `Date = formatdate(localtime=False)`, `Message-ID = make_msgid(domain=<part after @ in SMTP_FROM>)`, `Auto-Submitted: auto-generated`, `List-Unsubscribe: <{APP_PUBLIC_URL}/alerts/settings>`. `msg.set_content(text)` then `msg.add_alternative(html, subtype="html")`. Strip `\r` and `\n` from subject and address (header injection).
- `_open(host, port)`: one function the tests can monkeypatch. `ssl` → `smtplib.SMTP_SSL(host, port, timeout=..., context=ssl.create_default_context())`. `starttls` → `smtplib.SMTP(...)`, `ehlo()`, `starttls(context=ssl.create_default_context())`, `ehlo()`. `none` → `smtplib.SMTP(...)`, `ehlo()`.
- `send_now(msg) -> SendResult` (sync): open, `login(user, password.get_secret_value())` when a username is set, `send_message(msg)`, `quit()`. Returns `SendResult(ok, outcome, smtp_code, error)`. Never raises.
- The worker calls it with `await asyncio.to_thread(send_now, msg)`.
- Error sorting:
  - `SMTPRecipientsRefused`, `SMTPSenderRefused`, `SMTPDataError` or any `SMTPResponseException` with code 500-599 → `FAILED` (permanent).
  - Code 400-499, `SMTPServerDisconnected`, `SMTPConnectError`, `SMTPAuthenticationError` (the admin may fix the password; retry), `socket.timeout`, `OSError`, `ssl.SSLError` → `RETRY`.

### 5.4 Never leak the password

- `redact(text)`: replace the password value (if set) and the base64 forms of `"\0user\0password"` and `password` with `***`; cut to 500 chars. Apply to every `last_error` and `error` before saving, and to every log line about email.
- Log only: outbox id, kind, attempt number, outcome, SMTP code, the error class name. Never log subject, body or the password. Never put `settings` objects in log lines.
- `GET /alerts/admin/email-status` returns `password_set: bool`, never the value.

### 5.5 Sending loop, retry and backoff (`worker.py::send_due_emails`)

1. If not `email_configured()`: return.
2. Rows `SENDING` with `locked_until < now` → back to `PENDING` (a crash mid-send; may send twice, accepted and noted in the code).
3. Rows `PENDING` older than `ALERTS_EMAIL_MAX_AGE_HOURS` → `EXPIRED`.
4. Take up to 20 rows `PENDING` with `next_attempt_at <= now`, oldest first. For each: set `SENDING`, `locked_until = now + 5 min`, commit. Send. Then:
   - ok → `SENT`, `sent_at`, `smtp_message_id`; set `emailed_at` on its notifications.
   - `FAILED` → status `FAILED`.
   - `RETRY` → `attempts += 1`; if `attempts >= ALERTS_EMAIL_MAX_ATTEMPTS` then `FAILED`, else `PENDING` with `next_attempt_at = now + BACKOFF[attempts-1]`, where `BACKOFF = [60, 300, 900, 3600, 10800, 21600]` seconds (1 min, 5 min, 15 min, 1 h, 3 h, 6 h).
   - Always add one `EmailDeliveryAttempt` row. Commit after each row.
5. One SMTP connection per message is fine at this size.

A failed send never loses the alert: the notification is already in the inbox, the outbox row stays with its error, and an admin can retry it (`POST /alerts/admin/outbox/{id}/retry`).

### 5.6 Which emails are made

- **Instant:** at dispatch, for each new notification where the user's group setting is `INSTANT`, `email_enabled` is true, `email_configured()` is true and the user has an email: add `EmailOutbox(kind="INSTANT", dedupe_key=f"instant:{notification.id}")`, `next_attempt_at=now`. Then kick the worker (`alerts_worker.kick()`).
- **Daily digest** (`digest.py::build_digests(db, now)`): runs from the worker loop. If Dhaka time is at or after `ALERTS_DIGEST_TIME`, for each user with notifications where `email_mode == "DIGEST"`, `emailed_at IS NULL`, `read_at IS NULL`, created in the last 7 days and still visible (isolation check 7.1): make one outbox row `dedupe_key=f"digest:{user_id}:{today}"` and set `emailed_at` on those notifications in the same transaction. If the key exists, skip (one digest per user per day). Read ones are left out. If nothing is left, no email. If the PC was off at 10:30, the first loop after that time catches up.
- **Test:** see 7.3.

### 5.7 Templates (`alerts/templates.py`)

One function per kind returns `(title, body, detail, link, severity)` from the payload. Same strings are used for the inbox and for email. Plain English. Every value is inserted with `html.escape` in HTML. Dates as `13 Nov 2026`. `{ref}` = reference number, or "A circular" if none. `{title}` = the stored title, cut to 160 chars with "…".

| Kind | Title | Body | Link | Severity |
|---|---|---|---|---|
| `CIRCULAR_PUBLISHED` | `New circular: {ref}` | `{title}. Published {publication_date}.` | `/?doc={document_id}` | info |
| `REGISTER_SOURCE_CHANGED` (AMENDED/REPLACED/REPEALED) | `{ref} was {amended|replaced|repealed}` | `{by_ref} {amends|replaces|repeals} it. {item_count} item(s) in your registers at {org} point to it. Please check them.` | one item: `/workspace/{org}/items/{item_id}`; else `/workspace/{org}/registers/{register_id}?changed=1` (first register) | warn (REPEALED: bad) |
| `REGISTER_SOURCE_CHANGED` (NEW_VERSION) | `New version of {ref}` | `A newer version of this circular was published. {item_count} item(s) at {org} point to the older one.` | as above | warn |
| `REGISTER_SOURCE_CHANGED` (WITHDRAWN) | `{ref} was withdrawn` | `{item_count} item(s) at {org} point to it.` | as above | bad |
| `TASK_ASSIGNED` | `Task assigned to you: {task_title}` | `{actor_name} assigned you a task at {org}. Due {due_date}.` | `/workspace/{org}/items/{item_id}#task-{task_id}` | info |
| `ITEM_LEAD_ASSIGNED` | `You lead an item: {item_title}` | `{actor_name} made you the lead at {org}.` + ` Deadline {deadline}.` when set | `/workspace/{org}/items/{item_id}` | info |
| `TASK_CANCELLED` | `Task cancelled: {task_title}` | `{actor_name} cancelled this task at {org}.` | item link | info |
| `EVIDENCE_AWAITING_REVIEW` | `Evidence to review: {task_title}` | `{actor_name} uploaded evidence at {org}.` | `/workspace/{org}/review` | info |
| `ITEM_AWAITING_SIGNOFF` | `Item ready for sign-off: {item_title}` | `{actor_name} sent it for sign-off at {org}.` | `/workspace/{org}/items/{item_id}` | info |
| `TASK_REVIEWED` | `Evidence {approved|needs changes|rejected}: {task_title}` | `{actor_name} reviewed your evidence at {org}.` (detail = comments) | task link | info / warn / bad |
| `ITEM_SIGNOFF_DECIDED` | `Item {signed off as compliant|sent back}: {item_title}` | `{actor_name} decided at {org}.` (detail = comments) | item link | info / warn |
| `ITEM_DUE_SOON` | `Due in {n} day(s): {item_title}` (n = 0 → `Due today: ...`) | `Deadline {deadline} at {org}.` | item link | warn |
| `TASK_DUE_SOON` | `Task due in {n} day(s): {task_title}` | `Due {due_date} at {org}.` | task link | warn |
| `ITEM_OVERDUE` | `Overdue: {item_title}` | `The deadline was {deadline} at {org}.` | item link | bad |
| `TASK_OVERDUE` | `Overdue task: {task_title}` | `It was due {due_date} at {org}.` | task link | bad |
| `ADMIN_QUEUE` | `{count} {new circulars to approve|analyses to review|links to confirm|pages to check}` | `They are waiting in the admin review queue.` | `/admin?tab=...` (4.8) | info |

Quotes: the source-change notification sets `quote_text = link_quote`, `quote_page_number = link_quote_page`, `quote_document_id = by_document_id`. No other kind shows a quote. The inbox and email show it under a label "From {by_ref}, page {n}:" with the text exactly as stored.

**Email layout:**
- Subject = the title. Bank kinds prefix `[{org name}] `. Digest subject: `RegWatch daily summary: {n} alert(s)`.
- Text: title, blank line, body, blank line, quote (if any) as `"{quote}" (from {by_ref}, page {n})`, blank line, `Open: {APP_PUBLIC_URL}{link}`, then the footer.
- HTML: one column, max-width 560 px, system fonts, title in a 18 px heading, body paragraph, quote in a left-bordered block, one button-style link "Open in RegWatch". Inline styles only. No images, no tracking pixels, no external CSS.
- Digest: grouped under headings "New circulars", then one heading per bank name, then "Platform review queues"; each line = title + link; at most 50 lines, then "and {n} more in your inbox: {APP_PUBLIC_URL}/alerts".
- Footer (both): `You get this email because of your alert settings. Change them here: {APP_PUBLIC_URL}/alerts/settings`.
- Never in email: `detail` (reviewer comments), evidence file names, notes (decision A5).

---

## 6. Jobs and how they stay off

### 6.1 The alerts worker (`alerts/worker.py`, `AlertsWorker`)

Copy `VisionWorker`: `start()`, `stop()`, `kick()`, a loop that waits on an `asyncio.Event` with timeout `ALERTS_WORKER_POLL_SECONDS`. `running` property. Each loop, each step in its own session and its own try/except:
1. `dispatch_pending(session)`.
2. If `ALERTS_SWEEP_MINUTES` passed since the last sweep: for every active organization `ensure_deadline_events` and `ensure_source_change_events`; then `ensure_admin_queue_events`, `sweep_published`; then dispatch again; then delete notifications older than `ALERTS_RETENTION_DAYS` and clear `text_body`/`html_body` of SENT/EXPIRED/FAILED outbox rows older than 30 days (replace with empty string).
3. `build_digests(session, now)`.
4. `send_due_emails(session)`.

**Off unless enabled.** In `main.py` `lifespan`: `run_alerts = settings.SCHEDULER_ENABLED or settings.ALERTS_WORKER_ENABLED`. Start `alerts_worker` only then; stop it on shutdown. If `email_configured()` and not `run_alerts`, log once: "Email is set up but the alerts job is off. Set ALERTS_WORKER_ENABLED=true on one process." Run it in **one process only**, like the scheduler (the per-process dispatch lock is in memory; the unique keys protect against duplicates anyway).

### 6.2 What still works with the worker off

`GET /alerts/summary` (the poll) does, in this order, each step inside try/except so the count is always returned:
1. `dispatch_pending(db)` (one indexed query when nothing is pending).
2. Throttled sweeps for **this user only**: for each org where the user is ACTIVE, if more than `ALERTS_ON_POLL_SWEEP_MINUTES` passed since the last on-poll sweep of that org in this process (module-level dict `{org_id: datetime}`), run `ensure_deadline_events` and `ensure_source_change_events` for it. If the user is a superuser, the same throttle on key `"admin"` for `ensure_admin_queue_events` and `sweep_published`. Then dispatch again if anything was emitted.
3. Commit, then return the count.

So in dev (no worker, no SMTP) every in-app alert still appears within one poll plus the throttle. Email needs the worker.

### 6.3 Dispatch (`alerts/dispatch.py::dispatch_pending(db, limit=200)`)

For each `PENDING` event, oldest first:
1. Work out recipients:
   - Bank event (`organization_id` set): `recipient_user_ids` ∩ users who are ACTIVE members of that org now, and whose `User.is_active`. Organization must be active. **No superuser bypass.**
   - Library event: 4.2 rules. Re-check the document is shared and published, else `SUPPRESSED`.
   - Admin event: active superusers.
   - Remove `actor_user_id`.
2. Load preferences for all recipients in one query (`prefs.load_many`). For each user, the group setting (defaults from 3.6). Skip the user if `in_app` is false and email is `OFF`. For library events apply the filters.
3. Build the text once per event with `templates.render(kind, payload)`.
4. Insert one `AlertNotification` per user (skip if `(user_id, dedupe_key)` exists; check with one `SELECT ... WHERE user_id IN (...) AND dedupe_key = ...`). `in_app` and `email_mode` from the user's setting.
5. Instant email rows per 5.6.
6. Event → `DISPATCHED`, `dispatched_at = now`. On an exception for one event: `attempts += 1`, `last_error` (short, redacted), leave `PENDING`; after 5 attempts `FAILED`. Continue with the next event.

---

## 7. Endpoints

New router `backend/app/modules/alerts/router.py`, prefix `/alerts`, tag `Alerts`, mounted in `main.py` under `/api/v1`. All need `get_current_user` (401 otherwise).

### 7.1 Isolation rule for every read

A notification is visible to the caller only when:
- `user_id == caller.id`, **and**
- `in_app` is true, **and**
- `organization_id IS NULL`, or the caller is an ACTIVE member of that org and the org is active (join `organization_members`), **and**
- kind `ADMIN_QUEUE` only if the caller is still a superuser.

Put this in one function `visible_notifications_condition(user)` and use it in every list, count, read and read-all query. A notification the caller cannot see returns **404** (never 403; never reveal it exists). A suspended member stops seeing that bank's alerts at once, and they come back if re-activated.

### 7.2 User endpoints

| # | Method, path | Body / query | Response | Notes |
|---|---|---|---|---|
| N1 | GET `/alerts/summary` | – | `{unread_count, latest_id, latest_created_at, email_configured, server_time}` | The poll. Runs 6.2 first. Must answer in under 50 ms on a warm DB when nothing is pending |
| N2 | GET `/alerts` | `filter: all|unread` (default all), `group?` (one of 3.6), `before?: datetime` (paging, older than), `after?: datetime` (newer than, for delta), `limit` (default 30, max 100) | `{alerts: List[AlertRead], next_before: datetime|null, unread_count}` | Newest first. Runs `dispatch_pending` first |
| N3 | POST `/alerts/{id}/read` | – | `{alert: AlertRead, unread_count}` | Idempotent (keeps the first `read_at`) |
| N4 | POST `/alerts/{id}/unread` | – | `{alert: AlertRead, unread_count}` | |
| N5 | POST `/alerts/read-all` | `{up_to: datetime, group?: str}` | `{updated: int, unread_count}` | Marks visible unread rows with `created_at <= up_to` (so an alert that arrived after the click stays unread) |
| N6 | GET `/alerts/preferences` | – | `PreferencesRead` | Defaults merged in |
| N7 | PUT `/alerts/preferences` | `PreferencesWrite` | `PreferencesRead` | Full replace. 409 with `{"detail": "...", "current": PreferencesRead}` on `lock_version` mismatch (raise the existing `ConflictError`). Bumps `lock_version` |

`AlertRead`: `id, kind, group, severity, organization_id, organization_name (null for library/admin), title, body, detail, link, document: {id, reference_number, title} | null, quote: {text, page_number, document_id, document_reference} | null, read_at, created_at`.

`PreferencesRead`: `channels: {group: {in_app, email}}` for **the groups this user can see** (3.6; bank groups only if the user has an ACTIVE membership, `admin_queue` only for superusers), `email_enabled, library_department_codes, library_document_types, library_keywords, lock_version, email_configured, due_soon_days: List[int], digest_time: "10:30", options: {groups: [{id, label, description}], department_codes: [{code, name}] (from InstitutionDepartment, sorted by code), document_types: [str] (distinct shared-library values, sorted)}`.

`PreferencesWrite` validation (422 on failure): only known groups; `email` in `OFF|INSTANT|DIGEST`; lists of strings; department codes must exist; keywords trimmed, 2-60 chars, max 20, no duplicates (case-insensitive); groups the user cannot see are ignored (not stored).

### 7.3 Admin endpoints (superuser only, `get_current_superuser`)

| # | Method, path | Response | Notes |
|---|---|---|---|
| E1 | GET `/alerts/admin/email-status` | `{configured, host, port, tls_mode, from_address, username_set, password_set, worker_running, outbox: {pending, sending, sent_24h, failed, expired}, last_error: str|null}` | No password. `host` and `from_address` are shown (not secret) |
| E2 | POST `/alerts/admin/test-email` | `{ok, outcome, smtp_code, detail}` | 409 when not configured. Sends **only to the caller's own email** (no address field, so it cannot be used as a relay). Creates an `EmailOutbox(kind="TEST")` row, sends at once in this request with `asyncio.to_thread(send_now, ...)`, records the attempt, returns the result. Subject "RegWatch test email", body "Email from RegWatch works. Sent {time} Dhaka time." Never returns or logs the password. Rate limit: 1 per 30 s per user (in-memory), else 429 |
| E3 | GET `/alerts/admin/outbox` | `{rows: [{id, kind, status, attempts, next_attempt_at, sent_at, last_error, created_at, to_masked}]}`; query `status?`, `limit` (default 50, max 200) | **No subject or body.** `to_masked` = first letter + `***@` + domain. Bank email content stays private to the bank (compliance D1) |
| E4 | POST `/alerts/admin/outbox/{id}/retry` | the row as in E3 | Only `FAILED` or `EXPIRED`: set `PENDING`, `attempts=0`, `next_attempt_at=now`, kick the worker |

### 7.4 Small changes to existing endpoints and screens

- None of the existing response shapes change.
- `frontend/app/admin/page.tsx`: read `?tab=` (`queue`, `collection`, `upload`, `library`, `links`, `engine`) on first render with `useSearchParams` (wrap the page body in `<Suspense>`), and write it back with `router.replace` when the tab changes, so alert links open the right tab.

---

## 8. Screens and the client store

### 8.1 Files to add

- `frontend/services/alertsApi.ts`: types from 7.2/7.3 and one function per endpoint, using `apiFetch` and `ApiError` from `./api`. Do not grow `api.ts`.
- `frontend/services/alertsStore.ts`: the store (8.2).
- `frontend/components/alerts/BellButton.tsx`, `AlertPanel.tsx` (the dropdown / bottom sheet), `AlertRow.tsx`, `AlertQuote.tsx`.
- `frontend/app/alerts/page.tsx` (inbox), `frontend/app/alerts/settings/page.tsx` (preferences, plus the admin email box for superusers). Both `"use client"`; wrap anything using `useSearchParams` in `<Suspense>`.
- Change `frontend/components/AppHeader.tsx`: put `<BellButton />` before the account button when signed in. Call `startAlertsSync()` once when a user is signed in.

### 8.2 The store (`alertsStore.ts`)

Follow `workspaceStore.ts`: module-level `state`, `subscribe`, `useAlerts()` via `useSyncExternalStore`, `once()` load de-dup, `notice`, `syncSessionUser()` that resets everything when the signed-in user changes (listen to `AUTH_CHANGED_EVENT`; a different person must never see the last person's alerts).

State:
```
userId: string | null
alerts: Record<id, AlertRead>          // one copy of each; lists are selectors
listLoaded: "idle" | "loading" | "ok" | { error: string }
nextBefore: string | null              // for "Load older"
newestSeen: string | null              // latest_created_at we have loaded
unread: number                          // server count, adjusted by local optimistic changes
pending: Record<id, number>             // saves in flight per alert
prefs: PreferencesRead | null
prefsPending: number
emailConfigured: boolean
emailStatus: EmailStatus | null         // superusers
notice: { kind, text } | null
```

Selectors: `selectAlerts(state, {filter, group})` sorted by `created_at` desc, `selectPanelAlerts(state)` (latest 8 visible), `unreadCount(state)`.

**Polling (the "instant" choice).** Poll `GET /alerts/summary` every 15 s while the tab is visible (`ALERTS_POLL_MS`, read from `process.env.NEXT_PUBLIC_ALERTS_POLL_MS`, default 15000). Stop the timer when the tab is hidden. On `visibilitychange` to visible and on `focus`, poll at once. If `latest_created_at` is newer than `newestSeen`, fetch `GET /alerts?after=<newestSeen>` and merge. Why polling and not server-sent events:
- The sign-in token lives in `localStorage` and is sent as a `Bearer` header. The browser's `EventSource` cannot send headers, so SSE would need the token in the URL (it would land in server and proxy logs) or a new cookie login. Polling reuses `apiFetch` as is.
- One small server (uvicorn, one process, SQLite now). Each open tab of SSE holds a connection and a task forever; a 15 s poll of one indexed count query is cheaper and survives restarts, sleep and flaky Bangladeshi mobile links with no reconnect logic.
- Alerts are not chat. 15 s is fast enough for "a circular was published" or "a task was assigned". Your own tabs update at once anyway (below). Decision A1 lets the owner shorten it.

**Other tabs, at once.** `BroadcastChannel("regwatch-alerts")`. After every local change post a message; other tabs apply the same change to their state without a request:
- `{type: "read", ids, at}` → set `read_at` on those ids, recompute `unread`.
- `{type: "unread", ids}`.
- `{type: "read-all", upTo, group}` → mark loaded ones read, set `unread` from the message's `unread` value.
- `{type: "prefs", prefs}` → replace `prefs`.
- `{type: "poll"}` → poll now (sent after a tab sees new alerts, so all tabs show them together).
Wrap in try/catch; if `BroadcastChannel` is missing, other tabs catch up on their next poll or focus.

**Optimistic writes** (same per-record rollback as `workspaceStore.mutate`):
- `markRead(id)`: set `read_at = now`, `unread -= 1` (only if it was unread and visible), `pending[id]++`, broadcast, call N3. On success put the server copy and set `unread` to the server `unread_count` **only if no other alert write is pending**. On failure put back that alert only, re-add 1 to `unread`, show "Could not mark as read. Nothing was changed."
- `markUnread(id)`: mirror.
- `markAllRead()`: `upTo = newestSeen ?? now`; set `read_at` on every loaded unread alert with `created_at <= upTo`; `unread = 0` (or the count of loaded unread newer than `upTo`); broadcast; call N5. On failure put back exactly those alerts and the old count.
- `openAlert(alert, router)`: `markRead` (fire and forget) then `router.push(alert.link)`. The navigation does not wait for the save.
- `savePrefs(change)`: apply to `prefs` at once, `prefsPending++`, debounce 400 ms (merge several taps into one PUT), send with `lock_version`. On 409 put `current` into `prefs` and show "Your settings were changed in another window. You now see the latest." On other failure put back the last saved copy and show the error.

**Poll results never overwrite fresher local data:** use an `epoch` counter like `relationshipsStore`; a summary or list response that started before the latest local write finished is applied only for alerts not in `pending`, and its `unread_count` is ignored while any write is pending.

**Link with the workspace store.** When a poll brings new bank alerts for the org that is open in the workspace (`getWorkspaceState().activeOrgId`), call `refreshWorkspace(orgId, false)` from `workspaceStore.ts`, so the task list, review tab and item screens update at the same moment as the bell.

**Tab title.** While `unread > 0`, prefix `document.title` with `(n) `; remove it at 0. Update in a store subscription, not in each page.

**Preloading.** `startAlertsSync()` (called by `AppHeader` when signed in) polls once at start and loads the first page of alerts and the preferences in the background, so the panel and the settings screen open with data and no spinner.

### 8.3 Screens and every control

**Bell (`BellButton`, in the header).**
- Icon `Bell` (lucide), 44 × 44 px tap target on phones (`h-11 w-11`), `h-9 w-9` from `sm`. Label for screen readers: "Alerts, {n} unread".
- Badge: red dot with the count, `99+` cap, hidden at 0. Updates the moment the store changes (another tab, a poll, a read).
- Tap: from `sm` (≥ 640 px) opens `AlertPanel` as a popover under the bell, right-aligned, 380 px wide, max 70 vh tall, closes on outside click and `Escape`, focus moves into it. Below `sm` opens the same content in the shared `Modal` (bottom sheet).
- Signed out: no bell.

**Panel (`AlertPanel`).**
- Header: "Alerts", a "Mark all read" text button (disabled at 0 unread), a settings icon button (links to `/alerts/settings`).
- Up to 8 newest alerts (`AlertRow` compact). Skeleton rows only if the first load is still running.
- Empty: "Nothing new. You will see new circulars and work for you here."
- Footer: "See all alerts" link to `/alerts`.

**Row (`AlertRow`).**
- Unread: dot on the left and bold title. Read: normal weight, no dot.
- Small group icon (Library `FileText`, source change `GitCompare`, assigned `UserCheck`, review `ClipboardCheck`, decided `CheckCircle2`, due soon `Clock`, overdue `AlertTriangle`, admin `Inbox`), coloured by `severity` with the existing tones.
- Title (1 line, clamp), body (2 lines clamp), bank name as a `Tag` when `organization_name` is set, time as "5 min ago" with the full date and time in `title`.
- `AlertQuote` when `quote` is set: uses the `.quote` class, label "From {document_reference}, page {n}:" and the exact text. No clamping inside the inbox page; 3 lines in the panel.
- `detail` (comments) shown under the body on the inbox page only, prefixed "Comment:".
- Whole row is a button: tap → `openAlert`. A separate 44 px icon button on the right toggles read/unread ("Mark as read" / "Mark as unread" `aria-label`); it does not navigate.

**Inbox page (`/alerts`).**
- Title "Alerts". Right side: "Mark all read" (`btn-secondary`), "Settings" (`btn-ghost`, link).
- Filter strip: segmented "All | Unread (n)"; then group chips (only groups present for this user): New circulars, My bank's circulars, Assigned to me, Waiting for me, Decisions, Deadlines (due soon + overdue together), Review queues. Filters live in the URL (`?filter=unread&group=assigned`) so the back button works. On phones the chips scroll inside their own strip (no page side-scroll).
- List of `AlertRow` (full size). "Load older" button at the bottom while `nextBefore` is set (loads 30 more; button shows a spinner only on itself).
- Empty states: "No alerts yet." / "No unread alerts." / for a group "Nothing here yet."
- Signed out: `EmptyState` "Sign in to see your alerts." with a button that opens the account modal (dispatch the same event `AppHeader` listens to, or link to `/` with a note; pick the existing pattern used by the workspace page when signed out).
- Desktop: list max-width 760 px, centred. Phone: full width with 16 px side padding.

**Settings page (`/alerts/settings`).**
- Title "Alert settings". A one-line status at top:
  - email on: "Emails go to {your email}."
  - email off on server: "Email is not set up on this server. You will see alerts here in the app."
- Switch "Send me email" (`email_enabled`). Disabled with the reason when the server has no email.
- Table "What to tell me about" (desktop: rows = groups the user can see, columns "In the app" (checkbox) and "Email" (segmented: Off / Right away / Daily summary)). On phones each group is a card: label, one-line description, the checkbox, then the segmented control full width. Every control saves the moment it is tapped (optimistic), with a small "Saved" tick that fades after 1.5 s. No Save button.
- Group descriptions (plain English): e.g. Deadline coming up: "{due_soon_days} days and 1 day before a deadline. Sent to the item lead or the task owner." Daily summary: "One email a day at {digest_time} (Dhaka time)."
- Section "New circulars: only these" (only when the library group is on):
  - Departments: multi-select chips from `options.department_codes` ("BRPD", "DOS", ...; name in `title`). None selected = "All departments".
  - Document types: chips from `options.document_types`. None = "All types".
  - Keywords: a text field; Enter or comma adds a chip; each chip has a 44 px remove button. Helper text: "We check the circular's reference number and title. Leave empty for all circulars."
  - A line under the section: "You will get alerts for: {summary}" built from the current filters, updating as you tap.
- Superusers only, section "Email server" (`AdminEmailBox`): status lines from E1 (configured yes/no, host, port, TLS mode, from address, user set, password set, worker running), outbox counts, last error. Button "Send me a test email" (`btn-secondary`), disabled with the reason when email is not configured. It works even when the alerts job is off (the test email is sent directly). While sending, the button shows a spinner; the result shows in a `Notice` ("Test email sent to {email}." or "Could not send: {detail}"). A small table "Recent emails" from E3 (kind, status, attempts, to (masked), last error, time) with a "Retry" button on FAILED/EXPIRED rows; retry is optimistic (row shows PENDING at once).
- Phone: no side-scroll; the table becomes cards; all controls at least 44 px tall.

### 8.4 Wording rules
- Never say "notification" in the UI; say "alert".
- Times: relative under 24 h ("5 min ago"), else "13 Nov, 10:30".
- Keep every string in English (decision A10).

---

## 9. Tests

### 9.1 Backend (pytest), new files

`backend/app/tests/test_alerts.py`, `backend/app/tests/test_alerts_email.py`, helper `backend/app/tests/fake_smtp.py`. Use the existing style: `httpx.AsyncClient(transport=ASGITransport(app=app))`, `make_user`, `make_workspace`, `make_document` from `factories.py`. Freeze dates by monkeypatching `backend.app.modules.compliance.rules.today_dhaka`. Call `dispatch_pending` or `GET /alerts/summary` to dispatch (kicks are off in tests). Clear the on-poll throttle dict in a fixture.

`fake_smtp.py`: a tiny SMTP server on `127.0.0.1` port 0 using `socketserver.ThreadingTCPServer` and a line-based handler: answers `220` greeting; `EHLO`/`HELO` (advertise `AUTH PLAIN LOGIN` and `8BITMIME`), `AUTH PLAIN` (accept, remember the user), `MAIL FROM`, `RCPT TO`, `DATA` (collect until a line `.`), `RSET`, `NOOP`, `QUIT`. Stores messages as `(mail_from, rcpts, raw_bytes)`. A `mode` field: `ok`, `temp_fail` (`451` on `MAIL`), `perm_fail` (`550` on `RCPT`), `drop` (close the socket after greeting). Use it with `SMTP_TLS_MODE="none"`. Start and stop it in a fixture. (Loopback only, so the conftest network guard allows it.) Unit tests that only need the transport may instead monkeypatch `alerts.mailer._open`.

Tests (each numbered item is at least one test):
1. **Library publish.** Approving a discovery (or calling `circular_published` on a shared published doc) adds one event; after dispatch every active user with defaults has one unread notification titled `New circular: {ref}`, body only `{title}. Published {date}.`, link `/?doc={id}`, no quote.
2. **Private upload never alerts.** A private document set to a published status: `circular_published` adds nothing; `sweep_published` adds nothing; no user (owner included) gets a notification.
3. **Filters.** Department code, document type and keyword filters each include/exclude correctly; two groups are ANDed; a keyword matches case-insensitively in the reference number and in `title_bn`.
4. **Dedupe.** Publishing path run twice, `PUBLISHED → AWAITING_REVIEW → PUBLISHED_HUMAN_REVIEWED`, sweep run three times, dispatch run twice: still exactly one notification per user. `emit` with an existing key returns None and does not break the caller's transaction.
5. **Safety net.** A shared doc set to published without the helper and `updated_at` now → `sweep_published` emits; one updated 3 days ago → not.
6. **Bank isolation.** Workspace A and B. Assigning a task in A alerts only the assignee in A. A member of B gets nothing, and `GET /alerts`, N3, N4 on A's alert ids return 404 for them. A superuser who is not a member of A gets nothing and cannot read A's alerts. Suspend the assignee in A: A's alerts vanish from their list and count at once; re-activate: they come back.
7. **No self-alerts.** Assigning a task to yourself, uploading and then (as another reviewer) reviewing: the actor never gets their own event.
8. **Assignment.** T1 with assignee → `TASK_ASSIGNED`; T3 reassign to B → B alerted; reassign back to A → A alerted again (new key); repeating the same PATCH with no change → nothing. Item lead set on I5 → `ITEM_LEAD_ASSIGNED`. Cancel → `TASK_CANCELLED` to the assignee.
9. **Review waiting.** Evidence upload by the ANALYST moves the task to SUBMITTED → REVIEWER, COMPLIANCE_HEAD and the own-department lead are alerted; the uploader and the other department's lead are not; ORG_ADMIN is not (fallback case tested separately with no reviewers in the org). Item sent for sign-off → heads and reviewers who are not blocked by `signoff_block`.
10. **Decisions.** T9 CHANGES_REQUESTED → uploader and assignee get `TASK_REVIEWED` with `detail` = comments and severity warn; reviewer does not. I7 REJECTED → the person who sent it for sign-off gets `ITEM_SIGNOFF_DECIDED` (proves the recipient is read before `move_item` clears it).
11. **Deadlines.** Item with lead, deadline today+7 → `ITEM_DUE_SOON` (7); sweep again → nothing new; move the frozen date to deadline−1 → the 1-day alert; past the deadline → `ITEM_OVERDUE` to lead, department head and all heads, once. Item first seen at 1 day left gets only the 1-day alert. EVIDENCE_SUBMITTED item with a past deadline → no overdue alert. Editing the deadline → a new due-soon alert. Task overdue → assignee. Item with no lead → department head, then heads.
12. **Source change.** Register with 3 items from circular X. A PENDING_REVIEW `REPLACES` link from Y to X → nothing. Review it VERIFIED through the endpoint → exactly one `REGISTER_SOURCE_CHANGED` per recipient in that org (not three), `quote_text == link.supporting_quote` byte for byte, `quote_page_number` = the link's page. Org B without X → nothing. Acknowledge all three items (I8), add a second verified `AMENDS` link from Z → new signature → a new alert. Re-running the sweep → no duplicates. A verified link stated by a private upload → nothing.
13. **Admin queues.** One VALIDATED discovery → each superuser gets `ADMIN_QUEUE` "1 new circulars to approve" (fix the plural: "1 new circular"); a normal user does not; sweep again the same day → nothing; next day → a new one.
14. **Inbox endpoints.** N2 paging (`before`, `next_before`), `filter=unread`, `group`; N3 idempotent; N4; N5 with `up_to` leaves a newer alert unread; counts in every response match a fresh N1.
15. **Preferences.** N6 defaults (bank groups hidden for a user with no membership; `admin_queue` hidden for non-superusers). N7 rejects unknown group, bad email mode, unknown department code, keyword too short (422). Stale `lock_version` → 409 with `current`. In-app off + email off for `assigned` → no notification row. In-app off + email DIGEST → row with `in_app=False`, hidden from N1/N2.
16. **Golden rule.** For every kind, the rendered title/body contain only payload values and fixed words from the template table (assert exact strings for 4 kinds). No notification body contains the analysis summary of the circular.
17. **Worker gating.** With `SCHEDULER_ENABLED=false` and `ALERTS_WORKER_ENABLED=false`, entering the app lifespan does not start `alerts_worker` (`running is False`).

`test_alerts_email.py`:
18. **SMTP unset → no send.** Monkeypatch `smtplib.SMTP` and `smtplib.SMTP_SSL` to raise if constructed. Dispatch instant-email alerts and run `send_due_emails` and `build_digests`: no `email_outbox` rows, no exception, no log line at warning or above. E2 returns 409. N1 says `email_configured: false`.
19. **Instant email.** Settings monkeypatched to the fake server (`SMTP_HOST="127.0.0.1"`, port, `SMTP_FROM`, `SMTP_USERNAME`, `SMTP_PASSWORD="s3cret-test"`, `SMTP_TLS_MODE="none"`). Assign a task → one outbox row → `send_due_emails` → fake server got one message to the assignee with subject `[{org}] Task assigned to you: ...`, a `text/plain` and a `text/html` part, an absolute link `{APP_PUBLIC_URL}/workspace/...`, the footer, and no reviewer comments. Row `SENT`, one `SENT` attempt row, notification `emailed_at` set.
20. **Retry and backoff.** Fake server `temp_fail`: attempt 1 → `PENDING`, `attempts=1`, `next_attempt_at ≈ now+60 s`; drive the clock forward and repeat until `ALERTS_EMAIL_MAX_ATTEMPTS` → `FAILED`; one attempt row per try. `perm_fail` → `FAILED` after one attempt. `drop` → RETRY. The notification is still in the inbox in every case. E4 retry → `PENDING` again.
21. **Password never leaks.** With `caplog` at DEBUG through tests 19-20 and E1/E2: the password string and its base64 forms never appear in logs, `last_error`, attempt `error`, or any response body. E1 has `password_set: true` and no password field.
22. **Digest.** Two DIGEST notifications for a user, one read in-app: before `ALERTS_DIGEST_TIME` nothing; after it one outbox row `digest:{user}:{date}` listing only the unread one; running again the same day → no second row; both notifications now have `emailed_at` (the read one stays NULL).
23. **Expiry.** A PENDING row older than `ALERTS_EMAIL_MAX_AGE_HOURS` → `EXPIRED`, never sent.
24. **Test email.** E2 as superuser sends to their own address only (fake server rcpt check); as a normal user → 403; a second call within 30 s → 429.
25. **Production plain-SMTP guard.** `is_production` true, `SMTP_TLS_MODE="none"`, host `mail.example.com` → `email_configured()` is False.

Run the whole suite after each chunk. Expected end state: 317 + new tests pass, the same 6 fail and 1 error. Then `git checkout -- backend/app/tests/fixtures`.

### 9.2 Browser checks (real browser, desktop and 375 px)

Start the backend (with `ALERTS_KICK_AFTER_COMMIT=true`, no SMTP) and `npm run dev`. Use the demo org from `backend/scripts/seed.py` with an ORG_ADMIN, a COMPLIANCE_OFFICER, a REVIEWER, a DEPARTMENT_LEAD and an ANALYST (as in the compliance spec 9.2), plus a superuser. Use two browser profiles for two people.

Check each at desktop width and at 375 px:
1. As the officer, assign a task to the analyst. In the analyst's window the bell count goes up within 15 s with no reload (and at once on focus). The panel lists it; tapping it opens the item and scrolls to the task; the badge drops by one at that moment.
2. Two tabs as the same user: mark an alert read in one; the other tab's bell, panel and inbox change at once (no poll wait). Same for "Mark all read" and for a settings change.
3. Mark all read while a new alert arrives: the new one stays unread.
4. Stop the backend and tap "Mark as read": it shows read, then puts back with a plain error; nothing else on the screen resets.
5. Analyst uploads evidence: the reviewer's bell goes up; the workspace Review tab badge in the reviewer's window updates at the same moment as the bell.
6. Superuser confirms a REPLACES link to the register's circular in Admin → Links: the officer gets one "was replaced" alert showing the exact quote and page; the link opens the item or the register with "Circular changed" filtered.
7. Settings: every checkbox and segmented control reacts on tap and shows "Saved"; reload the page: the values stay. Turn off "Work assigned to me" in the app, assign again: no new alert.
8. Library filters: choose BRPD only; approve a DOS circular in admin: no alert; a BRPD one: alert.
9. With no SMTP: settings shows the "Email is not set up" line, email controls disabled; the superuser's "Send me a test email" is disabled with the reason. No console errors.
10. With a local test relay (any local SMTP catcher on 127.0.0.1, `SMTP_TLS_MODE=none`, `ALERTS_WORKER_ENABLED=true`): "Send me a test email" shows success; an instant alert arrives as email with working links; the "Recent emails" table shows it SENT.
11. Admin alert link `/admin?tab=links` opens the Links tab.
12. Phone width: no sideways page scroll on `/alerts` and `/alerts/settings`; the bell opens a bottom sheet; chips scroll in their strip; every button is at least 44 px tall.
13. Dark mode: bell, panel, inbox and settings readable.
14. Sign out, sign in as another user: no alerts from the previous user flash on screen.
15. Browser console: no errors or React key warnings on any alerts screen.

Then `npm run build` and `npm run lint` in `frontend/`.

---

## 10. Build plan (do in order; verify each chunk before the next)

1. **Models, settings, migration.** 3.1-3.8, the settings in 5.1, conftest env lines. Verify: pytest baseline unchanged (317/6/1); alembic upgrade/downgrade/upgrade on a copy of the dev DB; backfill count correct.
2. **Core: kinds, emit, templates, prefs, dispatch.** `kinds.py`, `emit.py` (with the after-commit kick), `templates.py`, `prefs.py` (defaults and merge), `recipients.py`, `dispatch.py`. Verify: tests 4, 15 (model part), 16.
3. **Inbox endpoints.** Router N1-N7 with the 7.1 isolation condition; mount in `main.py`. Verify: tests 14, 15, 6 (read part).
4. **Library events.** `circular_published` hooked at the four places in 4.2, `sweep_published`. Verify: tests 1, 2, 3, 5.
5. **Bank workflow events.** Hooks in 4.4-4.6. Verify: tests 6, 7, 8, 9, 10. Run the full compliance tests: nothing else changed.
6. **Sweeps.** `ensure_deadline_events`, `ensure_source_change_events` (+ hooks in 4.3), `ensure_admin_queue_events`, the on-poll throttle in N1. Verify: tests 11, 12, 13.
7. **Email.** `mailer.py`, `send_due_emails`, `digest.py`, E1-E4, `fake_smtp.py`. Verify: tests 18-25.
8. **Worker.** `worker.py`, start/stop in `main.py` behind the flags, retention clean-up. Verify: test 17; start the app locally with the flags off and on and read the start-up log lines.
9. **Frontend data layer.** `alertsApi.ts`, `alertsStore.ts` (poll, delta, BroadcastChannel, optimistic writes, epoch guard, session reset, workspace refresh link, tab title). Verify: `npm run build`, `npm run lint`.
10. **Bell and panel** in `AppHeader`. Browser checks 1-4, 14.
11. **Inbox and settings pages**, admin email box, `/admin?tab=`. Browser checks 5-11.
12. **Phone and polish pass.** Browser checks 12, 13, 15 on every alerts screen. Final full pytest run (then `git checkout -- backend/app/tests/fixtures`), `npm run build`, `npm run lint`. Grep the diff for tool or vendor names of the analysis step and for any mention of how the code was written; remove them. Do not commit.

---

## 11. Decisions for the product owner

Defaults are built as written above unless the owner says otherwise.

- **A1. How fast is "instant".** Default: the bell checks every 15 s while the tab is open and visible, and at once when you come back to the tab; your own tabs sync at once. Option: 5 s (3x the server load), or server-sent events later with a cookie login.
- **A2. Default channels.** Default: everything on in the app; email right away for work and for register circular changes; daily summary email for new circulars, deadlines, overdue and admin queues.
- **A3. Deadline warnings.** Default: 7 days and 1 day before, server-wide (`ALERTS_DUE_SOON_DAYS`). Option: let each user or each bank choose.
- **A4. Daily summary time.** Default: 10:30 Dhaka time for everyone (the host PC is on 10:00-18:00). Option: per-user time.
- **A5. What bank emails may contain.** Default: alert title, short body (task or obligation title, bank name, dates) and a link. Never reviewer comments, evidence file names or notes; those stay in the app. Stricter option: bank emails say only "You have a new alert at {bank}" plus a link.
- **A6. Who hears about overdue items.** Default: the item lead, the department head and every compliance head of the bank. Option: lead only, heads get it in the daily summary only.
- **A7. Who is asked to review evidence.** Default: compliance heads, reviewers and the department lead of that item's department; bank admins only when the bank has none of those.
- **A8. New-circular alerts for everyone.** Default: on for every signed-in user (in app, daily summary by email), filters optional. Option: off by default, users opt in.
- **A9. Other channels.** Default: in-app and email only. SMS and WhatsApp later; they need a paid gateway and phone number checks.
- **A10. Language.** Default: English alerts and emails. Bangla later, with the rest of the UI (open question in the business-purpose file).
- **A11. Platform staff and bank alerts.** Default (follows compliance D1): superusers get no bank alerts and cannot see bank email content in the admin outbox unless the bank adds them as a member.
- **A12. Keeping alerts.** Default: alerts are deleted after 180 days; sent email bodies are cleared after 30 days (the delivery log stays).
