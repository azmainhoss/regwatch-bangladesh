"""Who may do what in a bank's workspace (the matrix in the spec, as plain functions).

`m` is the caller's membership (needs `.role`, `.user_id`, `.department_id`).
`item` needs `.department_id` and `.assigned_lead_id`; `task` needs `.assigned_to_user_id`.
The server is the final check; the browser mirrors these rules to hide controls early.
"""
from typing import Dict, Iterable, Optional

ADMIN = "ORG_ADMIN"
HEAD = "COMPLIANCE_HEAD"
OFFICER = "COMPLIANCE_OFFICER"
LEAD = "DEPARTMENT_LEAD"
REVIEWER = "REVIEWER"
ANALYST = "ANALYST"
AUDITOR = "AUDITOR"
VIEWER = "VIEWER"

ALL_EDITORS = (ADMIN, HEAD, OFFICER)


def _same(a, b) -> bool:
    return a is not None and b is not None and str(a) == str(b)


def own_department(m, item) -> bool:
    return _same(m.department_id, item.department_id)


def item_lead(m, item) -> bool:
    return _same(m.user_id, item.assigned_lead_id)


def is_assignee(m, task) -> bool:
    return _same(m.user_id, task.assigned_to_user_id)


# --- organization level -----------------------------------------------------
def can_manage_members(m) -> bool:
    return m.role in (ADMIN, HEAD)


def can_manage_departments(m) -> bool:
    return m.role in (ADMIN, HEAD)


def can_delete_department(m) -> bool:
    return m.role == ADMIN


def can_manage_registers(m) -> bool:
    return m.role in ALL_EDITORS


def can_add_items(m) -> bool:
    return m.role in ALL_EDITORS


def can_view_audit_log(m) -> bool:
    return m.role in (ADMIN, HEAD, REVIEWER, AUDITOR)


def can_download_evidence(m) -> bool:
    return m.role != VIEWER


def can_exempt_and_reopen(m) -> bool:
    return m.role in (ADMIN, HEAD)


def can_sign_off_role(m) -> bool:
    return m.role in (ADMIN, HEAD, REVIEWER)


def can_review_tasks_role(m) -> bool:
    return m.role in (ADMIN, HEAD, REVIEWER, LEAD)


def can_acknowledge(m) -> bool:
    return m.role in ALL_EDITORS


# --- item level ------------------------------------------------------------
def can_edit_item(m, item) -> bool:
    return m.role in ALL_EDITORS or (m.role == LEAD and own_department(m, item))


def can_start_item(m, item) -> bool:
    """Start an item or send it for sign-off."""
    return can_edit_item(m, item) or (m.role == ANALYST and item_lead(m, item))


def can_edit_tasks(m, item) -> bool:
    """Create, edit and cancel tasks of an item."""
    return can_edit_item(m, item) or (m.role == ANALYST and item_lead(m, item))


def can_change_task_status(m, task, item) -> bool:
    if can_edit_tasks(m, item):
        return True
    return m.role not in (AUDITOR, VIEWER) and is_assignee(m, task)


def can_upload_evidence(m, task, item) -> bool:
    if can_edit_tasks(m, item):
        return True
    return m.role not in (AUDITOR, VIEWER) and is_assignee(m, task)


def can_review_task(m, item) -> bool:
    if m.role in (ADMIN, HEAD, REVIEWER):
        return True
    return m.role == LEAD and own_department(m, item)


# --- "nobody reviews their own work" (section 5.4) -----------------------------
def task_review_block(user_id, task, evidence: Iterable) -> Optional[str]:
    """Reason the user cannot review this task, or None."""
    if _same(user_id, task.assigned_to_user_id):
        return "You cannot review evidence you uploaded."
    for e in evidence:
        if e.withdrawn_at is None and _same(e.submitted_by_user_id, user_id):
            return "You cannot review evidence you uploaded."
    return None


def signoff_block(user_id, item, all_evidence: Iterable) -> Optional[str]:
    """Reason the user cannot sign off this item, or None."""
    if _same(user_id, item.submitted_for_signoff_by_user_id):
        return "You cannot sign off an item you worked on."
    for e in all_evidence:
        if e.withdrawn_at is None and _same(e.submitted_by_user_id, user_id):
            return "You cannot sign off an item you worked on."
    return None


def org_permissions(m) -> Dict[str, bool]:
    return {
        "manage_members": can_manage_members(m),
        "manage_departments": can_manage_departments(m),
        "manage_registers": can_manage_registers(m),
        "add_items": can_add_items(m),
        "edit_any_item": m.role in ALL_EDITORS,
        "exempt_and_reopen": can_exempt_and_reopen(m),
        "sign_off_items": can_sign_off_role(m),
        "review_tasks": can_review_tasks_role(m),
        "view_audit_log": can_view_audit_log(m),
        "export_report": True,
        "download_evidence": can_download_evidence(m),
    }
