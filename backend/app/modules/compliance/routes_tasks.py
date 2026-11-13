"""Tasks, evidence files and task reviews of a bank's compliance items."""
import os
import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.storage import storage_service
from backend.app.database.session import get_async_db
from backend.app.modules.alerts import hooks as alert_hooks
from backend.app.modules.audit import service as audit
from backend.app.modules.compliance import permissions as perms
from backend.app.modules.compliance import rules
from backend.app.modules.compliance.models import ComplianceItem, ComplianceTask, TaskEvidence, TaskReview
from backend.app.modules.compliance.schemas import (
    EvidenceRead,
    EvidenceWithdraw,
    EvidenceWriteResult,
    TaskCancel,
    TaskCreate,
    TaskList,
    TaskReviewCreate,
    TaskReviewResult,
    TaskUpdate,
    TaskWriteResult,
)
from backend.app.modules.compliance.service import (
    build_evidence,
    build_task_reviews,
    build_tasks,
    get_item_or_404,
    get_task_or_404,
    item_tasks,
    now_utc,
    one_item,
    utc,
)
from backend.app.modules.compliance.workflow import (
    CLOSED_ITEM_STATUSES,
    auto_reopen_item,
    auto_start_item,
    bump,
    check_task_lock,
    forbidden,
    require,
    require_member_user,
    task_state,
)
from backend.app.modules.organizations.deps import get_workspace_membership
from backend.app.modules.organizations.models import OrganizationMember

router = APIRouter()

CHUNK = 1024 * 1024
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ALLOWED_FILES = {
    ".pdf": ("application/pdf", lambda b: b.startswith(b"%PDF-")),
    ".png": ("image/png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    ".docx": (DOCX, lambda b: b.startswith(b"PK\x03\x04")),
    ".xlsx": (XLSX, lambda b: b.startswith(b"PK\x03\x04")),
    ".csv": ("text/csv", None),
    ".txt": ("text/plain", None),
}
TYPE_ERROR = "Allowed files: PDF, PNG, JPG, DOCX, XLSX, CSV, TXT."


def clean_filename(name: Optional[str], ext: str) -> str:
    base = re.split(r"[\\/]", name or "")[-1]
    base = re.sub(r"[\x00-\x1f\x7f\"']", "", base).strip()[:200]
    return base or f"evidence{ext}"


def _decodes(content: bytes) -> bool:
    try:
        content.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


async def _task_and_item(db: AsyncSession, organization_id: UUID, task_id: UUID):
    task = await get_task_or_404(db, organization_id, task_id)
    item = await get_item_or_404(db, organization_id, task.compliance_item_id)
    return task, item


async def _result(db: AsyncSession, task: ComplianceTask, item: ComplianceItem) -> TaskWriteResult:
    return TaskWriteResult(task=(await build_tasks(db, [task]))[0], item=await one_item(db, item))


async def _live_evidence(db: AsyncSession, task_id) -> List[TaskEvidence]:
    return list((await db.execute(
        select(TaskEvidence).where(TaskEvidence.task_id == task_id, TaskEvidence.withdrawn_at.is_(None))
        .order_by(TaskEvidence.created_at, TaskEvidence.id)
    )).scalars().all())


def _set_task_status(db, task: ComplianceTask, to: str, *, actor_user_id, request, cause: Optional[str] = None) -> None:
    before = task_state(task)
    task.status = to
    bump(task)
    b, a = audit.changed(before, task_state(task))
    if cause:
        a["reason"] = f"automatic: {cause}"
    audit.record(
        db, organization_id=task.organization_id, actor_user_id=actor_user_id, action="TASK_STATUS_CHANGED",
        entity_type="compliance_task", entity_id=task.id, before=b, after=a, request=request,
    )


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
@router.post("/tasks", response_model=TaskWriteResult, status_code=status.HTTP_201_CREATED)
async def create_task(
    organization_id: UUID,
    payload: TaskCreate,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    item = await db.get(ComplianceItem, payload.compliance_item_id)
    if not item or item.organization_id != organization_id:
        raise HTTPException(status_code=400, detail="Compliance item does not belong to this organization.")
    require(perms.can_edit_tasks(membership, item),
            "Only Department Leads, Compliance Officers, or Admins can assign tasks.")
    if item.status in CLOSED_ITEM_STATUSES:
        raise HTTPException(status_code=400, detail="Reopen it first.")
    await require_member_user(db, organization_id, payload.assigned_to_user_id, "Assigned user")

    task = ComplianceTask(
        organization_id=organization_id,
        compliance_item_id=item.id,
        title=payload.title,
        description=payload.description,
        assigned_to_user_id=payload.assigned_to_user_id,
        due_date=payload.due_date,
        priority=payload.priority,
        status="PENDING",
        lock_version=1,
    )
    db.add(task)
    await db.flush()
    audit.record(
        db, organization_id=organization_id, actor_user_id=membership.user_id, action="TASK_CREATED",
        entity_type="compliance_task", entity_id=task.id,
        after={**task_state(task), "compliance_item_id": str(item.id)}, request=request,
    )
    kw = dict(actor_user_id=membership.user_id, request=request, cause="a task was added")
    auto_start_item(db, item, **kw)
    auto_reopen_item(db, item, **kw)
    if task.assigned_to_user_id:
        await alert_hooks.task_assigned(db, organization_id, task, item, membership.user_id)
    await db.commit()
    await db.refresh(task)
    await db.refresh(item)
    return await _result(db, task, item)


@router.get("/tasks", response_model=TaskList)
async def list_tasks(
    organization_id: UUID,
    item_id: Optional[UUID] = Query(None),
    assignee: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    overdue: Optional[bool] = Query(None),
    awaiting_review: Optional[bool] = Query(None),
    updated_since: Optional[datetime] = Query(None),
    limit: int = Query(1000, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    today = rules.today_dhaka()
    query = select(ComplianceTask).where(ComplianceTask.organization_id == organization_id)
    if item_id:
        query = query.where(ComplianceTask.compliance_item_id == item_id)
    if assignee:
        if assignee == "me":
            query = query.where(ComplianceTask.assigned_to_user_id == membership.user_id)
        else:
            try:
                query = query.where(ComplianceTask.assigned_to_user_id == UUID(assignee))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid assignee.")
    if status_filter:
        query = query.where(ComplianceTask.status == status_filter)
    if awaiting_review:
        query = query.where(ComplianceTask.status == "SUBMITTED")
    od = and_(ComplianceTask.status.in_(rules.TASK_OVERDUE_STATUSES), ComplianceTask.due_date < today)
    if overdue is True:
        query = query.where(od)
    elif overdue is False:
        query = query.where(~od)
    if updated_since:
        query = query.where(ComplianceTask.updated_at > utc(updated_since))
    total = (await db.execute(select(func.count()).select_from(query.order_by(None).subquery()))).scalar_one()
    rows = (await db.execute(
        query.order_by(ComplianceTask.due_date, ComplianceTask.id).limit(limit).offset(offset)
    )).scalars().all()
    return TaskList(tasks=await build_tasks(db, rows, today), total=total, as_of=today, server_time=now_utc())


@router.patch("/tasks/{task_id}", response_model=TaskWriteResult)
async def update_task(
    organization_id: UUID,
    task_id: UUID,
    payload: TaskUpdate,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    task, item = await _task_and_item(db, organization_id, task_id)
    sent = payload.model_fields_set - {"lock_version"}
    editor = perms.can_edit_tasks(membership, item)
    if not editor:
        require(perms.can_change_task_status(membership, task, item), "You cannot change this task.")
        if sent - {"status"}:
            raise forbidden("Insufficient permissions: you can only change the status of a task assigned to you.")
    await check_task_lock(db, task, payload.lock_version, build_tasks)
    if task.status in ("APPROVED", "CANCELLED"):
        raise HTTPException(status_code=409, detail="This task is closed.")
    if "status" in sent:
        if payload.status is None or task.status not in ("PENDING", "IN_PROGRESS"):
            raise HTTPException(status_code=409, detail=f"This task cannot move from {task.status} to {payload.status}.")

    before = task_state(task)
    old_assignee = task.assigned_to_user_id
    if "title" in sent and payload.title:
        task.title = payload.title
    if "description" in sent:
        task.description = payload.description or None
    if "assigned_to_user_id" in sent:
        await require_member_user(db, organization_id, payload.assigned_to_user_id, "Assigned user")
        task.assigned_to_user_id = payload.assigned_to_user_id
    if "due_date" in sent and payload.due_date:
        task.due_date = payload.due_date
    if "priority" in sent and payload.priority:
        task.priority = payload.priority
    if "status" in sent and payload.status:
        task.status = payload.status
    b, a = audit.changed(before, task_state(task))
    if a:
        bump(task)
        action = "TASK_STATUS_CHANGED" if set(a) == {"status"} else "TASK_UPDATED"
        audit.record(
            db, organization_id=organization_id, actor_user_id=membership.user_id, action=action,
            entity_type="compliance_task", entity_id=task.id, before=b, after=a, request=request,
        )
        if task.status == "IN_PROGRESS":
            auto_start_item(db, item, actor_user_id=membership.user_id, request=request, cause="a task was started")
        if task.assigned_to_user_id and task.assigned_to_user_id != old_assignee:
            await alert_hooks.task_assigned(db, organization_id, task, item, membership.user_id)
    await db.commit()
    await db.refresh(task)
    await db.refresh(item)
    return await _result(db, task, item)


@router.post("/tasks/{task_id}/cancel", response_model=TaskWriteResult)
async def cancel_task(
    organization_id: UUID,
    task_id: UUID,
    payload: TaskCancel,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    task, item = await _task_and_item(db, organization_id, task_id)
    require(perms.can_edit_tasks(membership, item), "You cannot cancel this task.")
    if task.status == "APPROVED":
        raise HTTPException(status_code=409, detail="An approved task cannot be cancelled.")
    if task.status == "CANCELLED":
        raise HTTPException(status_code=409, detail="This task is already cancelled.")
    before = task_state(task)
    task.status = "CANCELLED"
    task.cancelled_reason = payload.reason
    bump(task)
    b, a = audit.changed(before, task_state(task))
    audit.record(
        db, organization_id=organization_id, actor_user_id=membership.user_id, action="TASK_STATUS_CHANGED",
        entity_type="compliance_task", entity_id=task.id, before=b, after=a, request=request,
    )
    await db.flush()
    if item.status == "EVIDENCE_SUBMITTED" and not any(t.status != "CANCELLED" for t in await item_tasks(db, item.id)):
        auto_reopen_item(db, item, actor_user_id=membership.user_id, request=request, cause="its last task was cancelled")
    if task.assigned_to_user_id:
        await alert_hooks.task_cancelled(db, organization_id, task, item, membership.user_id)
    await db.commit()
    await db.refresh(task)
    await db.refresh(item)
    return await _result(db, task, item)


# ---------------------------------------------------------------------------
# Task evidence (private customer files)
# ---------------------------------------------------------------------------
@router.post("/tasks/{task_id}/evidence", response_model=EvidenceWriteResult, status_code=status.HTTP_201_CREATED)
async def submit_task_evidence(
    organization_id: UUID,
    task_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    notes: Optional[str] = Form(None),
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    """Stores confidential audit evidence in the bank's own folder. Only reachable through the download route."""
    task, item = await _task_and_item(db, organization_id, task_id)
    require(perms.can_upload_evidence(membership, task, item),
            "Only the assigned user, department leads, or compliance officers can submit evidence.")
    if task.status in ("APPROVED", "CANCELLED"):
        raise HTTPException(status_code=409, detail="This task is closed. Evidence cannot be added.")
    if item.status in CLOSED_ITEM_STATUSES:
        raise HTTPException(status_code=409, detail="This item is closed. Reopen it first.")

    ext = os.path.splitext(re.split(r"[\\/]", file.filename or "")[-1])[1].lower()
    if ext not in ALLOWED_FILES:
        raise HTTPException(status_code=415, detail=TYPE_ERROR)
    mime, check = ALLOWED_FILES[ext]

    limit = settings.EVIDENCE_MAX_BYTES
    parts: List[bytes] = []
    size = 0
    while True:
        chunk = await file.read(CHUNK)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail=f"File is larger than {limit // (1024 * 1024)} MB.")
        parts.append(chunk)
    content = b"".join(parts)
    if size == 0:
        raise HTTPException(status_code=400, detail="Empty evidence file.")
    if (check is not None and not check(content)) or (check is None and not _decodes(content)):
        raise HTTPException(status_code=415, detail=TYPE_ERROR)

    # Short layout: evidence/<org>/<ab>/<hash>.<ext>. The item and task link lives in the database,
    # and each evidence row stores its own relative path, so files saved under the older, longer
    # layout still download.
    try:
        storage_path, file_sha256, file_size = storage_service.store_file(
            namespace=f"evidence/{organization_id}",
            filename_prefix="evidence",
            content=content,
            extension=ext,
            fanout=1,
        )
    except OSError as exc:
        logger.warning("Evidence file could not be saved: %s", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="The file could not be saved on the server. Nothing was changed. Please try again, or ask your administrator to check the storage folder.",
        )
    evidence = TaskEvidence(
        organization_id=organization_id,
        task_id=task.id,
        submitted_by_user_id=membership.user_id,
        file_sha256=file_sha256,
        storage_path=storage_path,
        original_filename=clean_filename(file.filename, ext),
        file_size_bytes=file_size,
        mime_type=mime,
        notes=(notes or "").strip()[:2000] or None,
    )
    db.add(evidence)
    await db.flush()
    audit.record(
        db, organization_id=organization_id, actor_user_id=membership.user_id, action="EVIDENCE_UPLOADED",
        entity_type="task_evidence", entity_id=evidence.id,
        after={"task_id": str(task.id), "filename": evidence.original_filename, "sha256": file_sha256,
               "size": file_size, "mime": mime},
        request=request,
    )
    moved_to_submitted = False
    if task.status in ("PENDING", "IN_PROGRESS", "REJECTED"):
        _set_task_status(db, task, "SUBMITTED", actor_user_id=membership.user_id, request=request,
                         cause="evidence was uploaded")
        moved_to_submitted = True
    auto_start_item(db, item, actor_user_id=membership.user_id, request=request, cause="evidence was uploaded")
    if moved_to_submitted:
        await alert_hooks.evidence_awaiting_review(db, organization_id, task, item, membership.user_id)
    await db.commit()
    await db.refresh(evidence)
    await db.refresh(task)
    await db.refresh(item)
    return EvidenceWriteResult(
        evidence=(await build_evidence(db, [evidence]))[0],
        task=(await build_tasks(db, [task]))[0],
        item=await one_item(db, item),
    )


@router.get("/tasks/{task_id}/evidence", response_model=List[EvidenceRead])
async def list_task_evidence(
    organization_id: UUID,
    task_id: UUID,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    task = await get_task_or_404(db, organization_id, task_id)
    rows = (await db.execute(
        select(TaskEvidence)
        .where(TaskEvidence.organization_id == organization_id, TaskEvidence.task_id == task.id)
        .order_by(TaskEvidence.created_at, TaskEvidence.id)
    )).scalars().all()
    return await build_evidence(db, list(rows))


def _ascii_name(name: str) -> str:
    out = re.sub(r"[^\x20-\x7e]", "_", name)
    return out.replace('"', "").replace("\\", "_") or "evidence"


@router.get("/tasks/{task_id}/evidence/{evidence_id}/download")
async def download_task_evidence(
    organization_id: UUID,
    task_id: UUID,
    evidence_id: UUID,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    """Serves one evidence file after checking membership, organization and task. Never cached."""
    require(perms.can_download_evidence(membership), "Viewers cannot download evidence files.")
    evidence = await db.get(TaskEvidence, evidence_id)
    if not evidence or evidence.organization_id != organization_id or evidence.task_id != task_id:
        raise HTTPException(status_code=404, detail="Evidence record not found.")
    try:
        path = storage_service.get_absolute_path(evidence.storage_path)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Evidence file missing from storage.")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Evidence file missing from storage.")
    audit.record(
        db, organization_id=organization_id, actor_user_id=membership.user_id, action="EVIDENCE_DOWNLOADED",
        entity_type="task_evidence", entity_id=evidence.id,
        after={"filename": evidence.original_filename, "sha256": evidence.file_sha256}, request=request,
    )
    await db.commit()
    name = evidence.original_filename
    return FileResponse(
        path,
        media_type=evidence.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=\"{_ascii_name(name)}\"; filename*=UTF-8''{quote(name, safe='')}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "X-SHA256-Checksum": evidence.file_sha256,
        },
    )


@router.post("/tasks/{task_id}/evidence/{evidence_id}/withdraw", response_model=EvidenceWriteResult)
async def withdraw_evidence(
    organization_id: UUID,
    task_id: UUID,
    evidence_id: UUID,
    payload: EvidenceWithdraw,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    task, item = await _task_and_item(db, organization_id, task_id)
    evidence = await db.get(TaskEvidence, evidence_id)
    if not evidence or evidence.organization_id != organization_id or evidence.task_id != task.id:
        raise HTTPException(status_code=404, detail="Evidence record not found.")
    if str(evidence.submitted_by_user_id) != str(membership.user_id):
        raise forbidden("Insufficient permissions: only the person who uploaded a file can withdraw it.")
    if evidence.withdrawn_at is not None:
        raise HTTPException(status_code=409, detail="This file was already withdrawn.")
    if task.status == "APPROVED":
        raise HTTPException(status_code=409, detail="This task is approved. Evidence can no longer be withdrawn.")
    evidence.withdrawn_at = now_utc()
    evidence.withdrawn_by_user_id = membership.user_id
    await db.flush()
    audit.record(
        db, organization_id=organization_id, actor_user_id=membership.user_id, action="EVIDENCE_WITHDRAWN",
        entity_type="task_evidence", entity_id=evidence.id,
        before={"withdrawn_at": None}, after={"withdrawn_at": evidence.withdrawn_at.isoformat(), "reason": payload.reason},
        request=request,
    )
    if task.status == "SUBMITTED" and not await _live_evidence(db, task.id):
        _set_task_status(db, task, "IN_PROGRESS", actor_user_id=membership.user_id, request=request,
                         cause="every evidence file was withdrawn")
        auto_reopen_item(db, item, actor_user_id=membership.user_id, request=request,
                         cause="every evidence file was withdrawn")
    await db.commit()
    await db.refresh(evidence)
    await db.refresh(task)
    await db.refresh(item)
    return EvidenceWriteResult(
        evidence=(await build_evidence(db, [evidence]))[0],
        task=(await build_tasks(db, [task]))[0],
        item=await one_item(db, item),
    )


# ---------------------------------------------------------------------------
# Task reviews
# ---------------------------------------------------------------------------
@router.post("/tasks/{task_id}/reviews", response_model=TaskReviewResult, status_code=status.HTTP_201_CREATED)
async def review_task(
    organization_id: UUID,
    task_id: UUID,
    payload: TaskReviewCreate,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    """Only Compliance Heads, Admins, Reviewers (and department leads for their own items) decide on evidence,
    and never on work they did themselves."""
    task, item = await _task_and_item(db, organization_id, task_id)
    require(perms.can_review_task(membership, item), "Only Compliance Leads or Admins can review tasks.")
    all_evidence = list((await db.execute(select(TaskEvidence).where(TaskEvidence.task_id == task.id))).scalars().all())
    block = perms.task_review_block(membership.user_id, task, all_evidence)
    if block:
        raise forbidden(block)
    if task.status != "SUBMITTED":
        raise HTTPException(status_code=409, detail="This task has no evidence waiting for review.")
    if payload.decision in ("CHANGES_REQUESTED", "REJECTED") and not payload.comments:
        raise HTTPException(status_code=400, detail="Comments are required when you ask for changes or reject.")

    review = TaskReview(
        task_id=task.id,
        organization_id=organization_id,
        reviewer_user_id=membership.user_id,
        decision=payload.decision,
        comments=payload.comments,
        evidence_ids=[str(e.id) for e in all_evidence if e.withdrawn_at is None],
    )
    db.add(review)
    await db.flush()
    new_status = {"APPROVED": "APPROVED", "CHANGES_REQUESTED": "IN_PROGRESS", "REJECTED": "REJECTED"}[payload.decision]
    old_status = task.status
    task.status = new_status
    bump(task)
    audit.record(
        db, organization_id=organization_id, actor_user_id=membership.user_id, action="TASK_REVIEWED",
        entity_type="compliance_task", entity_id=task.id,
        before={"status": old_status},
        after={"status": new_status, "decision": payload.decision, "comments": payload.comments},
        request=request,
    )
    if new_status != "APPROVED":
        auto_reopen_item(db, item, actor_user_id=membership.user_id, request=request,
                         cause="a task is no longer approved")
    await db.flush()
    await alert_hooks.task_reviewed(db, organization_id, task, item, review, membership.user_id)
    await db.commit()
    await db.refresh(review)
    await db.refresh(task)
    await db.refresh(item)
    return TaskReviewResult(
        review=(await build_task_reviews(db, [review]))[0],
        task=(await build_tasks(db, [task]))[0],
        item=await one_item(db, item),
    )
