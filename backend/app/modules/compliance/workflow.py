"""Shared building blocks for item and task writes: audit snapshots, lock checks, automatic moves."""
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.audit import service as audit
from backend.app.modules.compliance.models import ComplianceItem, ComplianceTask
from backend.app.modules.compliance.service import ConflictError, now_utc, one_item
from backend.app.modules.organizations.models import Department, OrganizationMember

ITEM_AUDIT_FIELDS = (
    "status", "department_id", "assigned_lead_id", "internal_deadline", "internal_code", "notes",
    "exemption_reason", "submitted_for_signoff_by_user_id", "submitted_for_signoff_at",
    "signed_off_by_user_id", "signed_off_at",
)
TASK_AUDIT_FIELDS = (
    "title", "description", "assigned_to_user_id", "due_date", "priority", "status", "cancelled_reason",
)

CLOSED_ITEM_STATUSES = ("COMPLIANT", "EXEMPTED")


def forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=403, detail=message)


def item_state(item: ComplianceItem) -> dict:
    return audit.pick(item, ITEM_AUDIT_FIELDS)


def task_state(task: ComplianceTask) -> dict:
    return audit.pick(task, TASK_AUDIT_FIELDS)


def bump(record) -> None:
    record.lock_version = (record.lock_version or 1) + 1


async def check_item_lock(db: AsyncSession, item: ComplianceItem, lock_version: Optional[int]) -> None:
    if lock_version is not None and lock_version != item.lock_version:
        raise ConflictError("Someone else changed this item. You now see their version.", await one_item(db, item))


async def check_task_lock(db: AsyncSession, task: ComplianceTask, lock_version: Optional[int], build) -> None:
    if lock_version is not None and lock_version != task.lock_version:
        raise ConflictError("Someone else changed this task. You now see their version.", (await build(db, [task]))[0])


def move_item(
    db: AsyncSession,
    item: ComplianceItem,
    to: str,
    *,
    actor_user_id,
    request: Optional[Request],
    cause: Optional[str] = None,
    action: str = "ITEM_STATUS_CHANGED",
    reason: Optional[str] = None,
) -> None:
    """Moves an item to a new status, clears the fields that belong to the old one and writes one audit entry.
    `cause` marks an automatic move ("automatic: <cause>")."""
    before = item_state(item)
    old = item.status
    item.status = to
    if to != "EVIDENCE_SUBMITTED":
        item.submitted_for_signoff_by_user_id = None
        item.submitted_for_signoff_at = None
    if to != "COMPLIANT":
        item.signed_off_by_user_id = None
        item.signed_off_at = None
    if to != "EXEMPTED":
        item.exemption_reason = None
    if to == "EXEMPTED":
        item.exemption_reason = reason
    if to == "EVIDENCE_SUBMITTED":
        item.submitted_for_signoff_by_user_id = actor_user_id
        item.submitted_for_signoff_at = now_utc()
    if to == "COMPLIANT":
        item.signed_off_by_user_id = actor_user_id
        item.signed_off_at = now_utc()
    bump(item)
    b, a = audit.changed(before, item_state(item))
    if cause:
        a["reason"] = f"automatic: {cause}"
    elif reason:
        a["reason"] = reason
    b["status"] = old
    audit.record(
        db, organization_id=item.organization_id, actor_user_id=actor_user_id, action=action,
        entity_type="compliance_item", entity_id=item.id, before=b, after=a, request=request,
    )


def auto_start_item(db, item: ComplianceItem, *, actor_user_id, request, cause: str) -> None:
    """Work began: NOT_STARTED becomes IN_PROGRESS."""
    if item.status == "NOT_STARTED":
        move_item(db, item, "IN_PROGRESS", actor_user_id=actor_user_id, request=request, cause=cause)


def auto_reopen_item(db, item: ComplianceItem, *, actor_user_id, request, cause: str) -> None:
    """Something changed under a waiting sign-off: the item goes back to IN_PROGRESS."""
    if item.status == "EVIDENCE_SUBMITTED":
        move_item(db, item, "IN_PROGRESS", actor_user_id=actor_user_id, request=request, cause=cause)


async def require_member_user(
    db: AsyncSession, organization_id: UUID, user_id: Optional[UUID], label: str
) -> Optional[OrganizationMember]:
    """Reject a user reference unless that user is an active member of this organization."""
    if user_id is None:
        return None
    found = (await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.status == "ACTIVE"
        )
    )).scalar_one_or_none()
    if not found:
        raise HTTPException(status_code=400, detail=f"{label} is not an active member of this organization.")
    return found


async def require_department(db: AsyncSession, organization_id: UUID, department_id: Optional[UUID]) -> None:
    if department_id is None:
        return
    dept = await db.get(Department, department_id)
    if not dept or dept.organization_id != organization_id:
        raise HTTPException(status_code=400, detail="Department does not belong to this organization.")


def require(allowed: bool, message: str) -> None:
    if not allowed:
        raise forbidden(f"Insufficient permissions: {message}")
