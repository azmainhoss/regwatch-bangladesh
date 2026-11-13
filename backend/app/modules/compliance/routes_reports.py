"""The organization's audit log and the board report (JSON for the print page, CSV for spreadsheets)."""
import csv
import io
from datetime import datetime, timedelta
from typing import Dict, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.session import get_async_db
from backend.app.modules.audit import service as audit
from backend.app.modules.audit.models import AuditEvent
from backend.app.modules.compliance import permissions as perms
from backend.app.modules.compliance import rules
from backend.app.modules.compliance.models import ComplianceItem, ComplianceRegister, ComplianceTask, TaskEvidence
from backend.app.modules.compliance.schemas import (
    AuditPage,
    AuditRead,
    DepartmentTotals,
    ItemRead,
    ReportOrg,
    ReportRead,
    ReportTotals,
)
from backend.app.modules.compliance.service import (
    ItemFilter,
    get_register_or_404,
    load_items,
    now_utc,
    users_map,
    utc,
)
from backend.app.modules.compliance.workflow import forbidden
from backend.app.modules.identity.deps import get_current_user
from backend.app.modules.identity.models import User
from backend.app.modules.organizations.deps import get_workspace_membership
from backend.app.modules.organizations.models import Department, Organization, OrganizationMember
from backend.app.modules.organizations.schemas import UserMini

router = APIRouter()

STATUS_LABELS = {
    "NOT_STARTED": "Not started", "IN_PROGRESS": "In progress", "OVERDUE": "Overdue",
    "EVIDENCE_SUBMITTED": "Waiting sign-off", "COMPLIANT": "Compliant", "EXEMPTED": "Exempted",
}
OPEN_STATUSES = ("NOT_STARTED", "IN_PROGRESS", "EVIDENCE_SUBMITTED")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
@router.get("/audit", response_model=AuditPage)
async def get_audit_log(
    organization_id: UUID,
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[UUID] = Query(None),
    actor_id: Optional[UUID] = Query(None),
    action: Optional[str] = Query(None),
    before: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db),
):
    whole_log = perms.can_view_audit_log(membership)
    entity_ids = None
    if entity_id is not None:
        item = await db.get(ComplianceItem, entity_id)
        task = None if item else await db.get(ComplianceTask, entity_id)
        if item is not None and item.organization_id == organization_id:
            task_ids = [t for (t,) in (await db.execute(
                select(ComplianceTask.id).where(ComplianceTask.compliance_item_id == item.id))).all()]
            evidence_ids = [e for (e,) in (await db.execute(
                select(TaskEvidence.id).where(TaskEvidence.task_id.in_(task_ids)))).all()] if task_ids else []
            entity_ids = [item.id, *task_ids, *evidence_ids]
        elif task is not None and task.organization_id == organization_id:
            evidence_ids = [e for (e,) in (await db.execute(
                select(TaskEvidence.id).where(TaskEvidence.task_id == task.id))).all()]
            entity_ids = [task.id, *evidence_ids]
        elif whole_log:
            entity_ids = [entity_id]
        else:
            raise forbidden("Insufficient permissions: you cannot view the audit log.")
    elif not whole_log:
        raise forbidden("Insufficient permissions: you cannot view the audit log.")

    query = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
    if entity_ids is not None:
        query = query.where(AuditEvent.entity_id.in_(entity_ids))
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if actor_id:
        query = query.where(AuditEvent.actor_user_id == actor_id)
    if action:
        query = query.where(AuditEvent.action == action)
    if before:
        query = query.where(AuditEvent.created_at < utc(before))
    rows = list((await db.execute(
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit + 1)
    )).scalars().all())
    more = len(rows) > limit
    rows = rows[:limit]
    users = await users_map(db, [r.actor_user_id for r in rows])
    events = [
        AuditRead(
            id=r.id, action=r.action, entity_type=r.entity_type, entity_id=r.entity_id,
            actor=users.get(str(r.actor_user_id)) if r.actor_user_id else None,
            before=r.before_state, after=r.after_state, created_at=utc(r.created_at),
        )
        for r in rows
    ]
    return AuditPage(events=events, next_before=events[-1].created_at if more and events else None)


# ---------------------------------------------------------------------------
# Board report
# ---------------------------------------------------------------------------
def _totals(items) -> ReportTotals:
    t = ReportTotals(total=len(items))
    for i in items:
        if i.status in OPEN_STATUSES:
            t.open += 1
        if i.display_status == "NOT_STARTED":
            t.not_started += 1
        elif i.display_status == "IN_PROGRESS":
            t.in_progress += 1
        elif i.display_status == "OVERDUE":
            t.overdue += 1
        elif i.display_status == "EVIDENCE_SUBMITTED":
            t.evidence_submitted += 1
        elif i.display_status == "COMPLIANT":
            t.compliant += 1
        elif i.display_status == "EXEMPTED":
            t.exempted += 1
        if i.source_change is not None:
            t.flagged += 1
    return t


def _by_department(items, departments: Dict[str, str]):
    rows: Dict[Optional[str], DepartmentTotals] = {}
    for i in items:
        key = str(i.department_id) if i.department_id else None
        row = rows.get(key)
        if row is None:
            row = DepartmentTotals(
                department_id=i.department_id,
                name=departments.get(key, "No department") if key else "No department",
            )
            rows[key] = row
        row.total += 1
        if i.status in OPEN_STATUSES:
            row.open += 1
        if i.is_overdue:
            row.overdue += 1
        if i.status == "EVIDENCE_SUBMITTED":
            row.evidence_submitted += 1
        elif i.status == "COMPLIANT":
            row.compliant += 1
        elif i.status == "EXEMPTED":
            row.exempted += 1
    for dept_id, name in departments.items():
        if dept_id not in rows:
            rows[dept_id] = DepartmentTotals(department_id=UUID(dept_id), name=name)
    return sorted(rows.values(), key=lambda r: (r.department_id is None, r.name.lower()))


def _cell(value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)  # numbers such as -3 days are not formulas
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


CSV_HEADER = [
    "Register", "Internal code", "Obligation", "Circular reference", "Circular title", "Page", "Exact quote",
    "File SHA-256", "Department", "Lead", "Regulatory deadline", "Internal deadline", "Status (display)",
    "Days left", "Open tasks", "Evidence files", "Signed off by", "Signed off at", "Source change",
]


def _csv(items, registers: Dict[str, str], departments: Dict[str, str], today) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for i in items:
        writer.writerow([_cell(c) for c in [
            registers.get(str(i.register_id), ""),
            i.internal_code or "",
            i.obligation_title or "",
            i.source.reference_number or "",
            i.source.title or "",
            i.source.page_number if i.source.page_number is not None else "",
            i.source.quote or "",
            i.source.file_sha256 or "",
            departments.get(str(i.department_id), "") if i.department_id else "",
            i.assigned_lead.full_name if i.assigned_lead else "",
            i.regulatory_deadline.isoformat() if i.regulatory_deadline else "",
            i.internal_deadline.isoformat() if i.internal_deadline else "",
            STATUS_LABELS.get(i.display_status, i.display_status),
            i.days_left if i.days_left is not None else "",
            i.task_counts.open,
            i.evidence_count,
            i.signed_off_by.full_name if i.signed_off_by else "",
            i.signed_off_at.isoformat() if i.signed_off_at else "",
            i.source_change.detail if i.source_change else "",
        ]])
    return ("﻿" + buf.getvalue()).encode("utf-8")


@router.get("/report")
async def board_report(
    organization_id: UUID,
    request: Request,
    register_id: Optional[UUID] = Query(None),
    format: Literal["json", "csv"] = Query("json"),
    membership: OrganizationMember = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    register = None
    if register_id:
        register = await get_register_or_404(db, organization_id, register_id)
    today = rules.today_dhaka()
    _rows, _total, items = await load_items(
        db, organization_id, ItemFilter(register_id=register_id, limit=100000), today
    )
    departments = {
        str(d.id): d.name for d in (await db.execute(
            select(Department).where(Department.organization_id == organization_id))).scalars().all()
    }
    registers = {
        str(r.id): r.title for r in (await db.execute(
            select(ComplianceRegister).where(ComplianceRegister.organization_id == organization_id))).scalars().all()
    }

    audit.record(
        db, organization_id=organization_id, actor_user_id=membership.user_id, action="REPORT_EXPORTED",
        entity_type="report", entity_id=register_id or organization_id,
        after={"format": format, "register_id": str(register_id) if register_id else None}, request=request,
    )
    await db.commit()

    if format == "csv":
        return Response(
            content=_csv(items, registers, departments, today),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="regwatch-report-{today.isoformat()}.csv"'},
        )

    org = await db.get(Organization, organization_id)
    horizon = today + timedelta(days=30)
    by_date = lambda i: (i.effective_deadline or today, i.obligation_title or "")  # noqa: E731
    overdue_items = sorted([i for i in items if i.is_overdue], key=by_date)
    upcoming = sorted(
        [i for i in items
         if i.status in OPEN_STATUSES and not i.is_overdue and i.effective_deadline
         and today <= i.effective_deadline <= horizon],
        key=by_date,
    )
    flagged = [i for i in items if i.source_change is not None]
    return ReportRead(
        organization=ReportOrg(id=org.id, name=org.name),
        generated_at=now_utc(),
        as_of=today,
        generated_by=UserMini(id=current_user.id, full_name=current_user.full_name, email=current_user.email),
        register_id=register_id,
        register_title=register.title if register else None,
        totals=_totals(items),
        by_department=_by_department(items, departments),
        overdue_items=overdue_items,
        upcoming_items=upcoming,
        flagged_items=flagged,
        items=items,
    )
