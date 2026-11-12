from io import BytesIO
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.storage import storage_service
from backend.app.database.session import get_async_db
from backend.app.modules.compliance.models import (
    ComplianceItem,
    ComplianceRegister,
    ComplianceTask,
    TaskEvent,
    TaskEvidence,
    TaskReview,
)
from backend.app.modules.compliance.schemas import (
    ComplianceItemCreate,
    ComplianceItemRead,
    ComplianceRegisterCreate,
    ComplianceRegisterRead,
    ComplianceTaskCreate,
    ComplianceTaskRead,
    TaskEvidenceRead,
    TaskReviewCreate,
    TaskReviewRead,
)
from backend.app.modules.identity.deps import get_current_user
from backend.app.modules.identity.models import User
from backend.app.modules.organizations.deps import get_org_membership
from backend.app.modules.documents.models import Document, DocumentVersion
from backend.app.modules.obligations.models import Obligation
from backend.app.modules.organizations.models import Department, OrganizationMember

router = APIRouter(
    prefix="/organizations/{organization_id}/compliance",
    tags=["Compliance Workflows (Tenant Isolated)"]
)

MAX_EVIDENCE_SIZE_BYTES = 50 * 1024 * 1024


async def _require_org_member_user(db: AsyncSession, organization_id: UUID, user_id: Optional[UUID], label: str) -> None:
    """Reject a user reference unless that user is an active member of this organization."""
    if user_id is None:
        return
    found = (await db.execute(
        select(OrganizationMember.id).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.status == "ACTIVE"
        )
    )).first()
    if not found:
        raise HTTPException(status_code=400, detail=f"{label} is not an active member of this organization.")


async def _require_org_department(db: AsyncSession, organization_id: UUID, department_id: Optional[UUID]) -> None:
    if department_id is None:
        return
    dept = await db.get(Department, department_id)
    if not dept or dept.organization_id != organization_id:
        raise HTTPException(status_code=400, detail="Department does not belong to this organization.")


# ---------------------------------------------------------------------------
# Compliance Registers
# ---------------------------------------------------------------------------
@router.post("/registers", response_model=ComplianceRegisterRead, status_code=status.HTTP_201_CREATED)
async def create_register(
    organization_id: UUID,
    payload: ComplianceRegisterCreate,
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_async_db)
):
    if membership.role not in ["ORG_ADMIN", "COMPLIANCE_HEAD"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions: Only Organization Admins or Compliance Heads can create compliance registers."
        )

    register = ComplianceRegister(
        organization_id=organization_id,
        title=payload.title,
        description=payload.description,
        is_active=payload.is_active
    )
    db.add(register)
    await db.commit()
    await db.refresh(register)
    return register


@router.get("/registers", response_model=List[ComplianceRegisterRead])
async def list_registers(
    organization_id: UUID,
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_async_db)
):
    query = (
        select(ComplianceRegister)
        .where(ComplianceRegister.organization_id == organization_id)
        .order_by(ComplianceRegister.title)
    )
    result = await db.execute(query)
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Compliance Items
# ---------------------------------------------------------------------------
@router.post("/items", response_model=ComplianceItemRead, status_code=status.HTTP_201_CREATED)
async def create_compliance_item(
    organization_id: UUID,
    payload: ComplianceItemCreate,
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_async_db)
):
    if membership.role not in ["ORG_ADMIN", "COMPLIANCE_HEAD", "COMPLIANCE_OFFICER"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions: Only Compliance Officers, Heads, or Admins can create compliance items."
        )

    # Verify register belongs to this organization
    register = await db.get(ComplianceRegister, payload.register_id)
    if not register or register.organization_id != organization_id:
        raise HTTPException(status_code=400, detail="Invalid register for this organization.")

    # Compliance registers are shared with the whole organization, so only obligations
    # from the shared library can be linked; private uploads stay private.
    if payload.obligation_id is not None:
        shared_obligation = (await db.execute(
            select(Obligation.id)
            .join(DocumentVersion, DocumentVersion.id == Obligation.document_version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Obligation.id == payload.obligation_id, Document.owner_user_id.is_(None))
        )).first()
        if shared_obligation is None:
            raise HTTPException(status_code=400, detail="Obligation not found.")
    await _require_org_department(db, organization_id, payload.department_id)
    await _require_org_member_user(db, organization_id, payload.assigned_lead_id, "Assigned lead")

    item = ComplianceItem(
        organization_id=organization_id,
        register_id=payload.register_id,
        obligation_id=payload.obligation_id,
        internal_code=payload.internal_code,
        department_id=payload.department_id,
        assigned_lead_id=payload.assigned_lead_id,
        status=payload.status,
        internal_deadline=payload.internal_deadline
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/items", response_model=List[ComplianceItemRead])
async def list_compliance_items(
    organization_id: UUID,
    register_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_async_db)
):
    query = select(ComplianceItem).where(ComplianceItem.organization_id == organization_id)
    if register_id:
        query = query.where(ComplianceItem.register_id == register_id)
    if status_filter:
        query = query.where(ComplianceItem.status == status_filter)

    query = query.order_by(ComplianceItem.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Compliance Tasks
# ---------------------------------------------------------------------------
@router.post("/tasks", response_model=ComplianceTaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    organization_id: UUID,
    payload: ComplianceTaskCreate,
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_async_db)
):
    if membership.role not in ["ORG_ADMIN", "COMPLIANCE_HEAD", "COMPLIANCE_OFFICER", "DEPARTMENT_LEAD"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions: Only Department Leads, Compliance Officers, or Admins can assign tasks."
        )

    item = await db.get(ComplianceItem, payload.compliance_item_id)
    if not item or item.organization_id != organization_id:
        raise HTTPException(status_code=400, detail="Compliance item does not belong to this organization.")

    await _require_org_member_user(db, organization_id, payload.assigned_to_user_id, "Assigned user")

    task = ComplianceTask(
        organization_id=organization_id,
        compliance_item_id=payload.compliance_item_id,
        title=payload.title,
        description=payload.description,
        assigned_to_user_id=payload.assigned_to_user_id,
        due_date=payload.due_date,
        priority=payload.priority,
        status=payload.status
    )
    db.add(task)
    await db.flush()

    event = TaskEvent(
        task_id=task.id,
        actor_user_id=membership.user_id,
        event_type="TASK_CREATED",
        event_payload={"title": task.title, "priority": task.priority}
    )
    db.add(event)
    await db.commit()
    await db.refresh(task)
    return task


@router.get("/tasks", response_model=List[ComplianceTaskRead])
async def list_tasks(
    organization_id: UUID,
    item_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_async_db)
):
    query = select(ComplianceTask).where(ComplianceTask.organization_id == organization_id)
    if item_id:
        query = query.where(ComplianceTask.compliance_item_id == item_id)
    if status_filter:
        query = query.where(ComplianceTask.status == status_filter)

    result = await db.execute(query.order_by(ComplianceTask.due_date))
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Task Evidence Submissions (Strictly Private Customer Files)
# ---------------------------------------------------------------------------
@router.post("/tasks/{task_id}/evidence", response_model=TaskEvidenceRead, status_code=status.HTTP_201_CREATED)
async def submit_task_evidence(
    organization_id: UUID,
    task_id: UUID,
    file: UploadFile = File(...),
    notes: Optional[str] = Form(None),
    membership: OrganizationMember = Depends(get_org_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Submits confidential audit evidence.
    File is stored in isolated evidence namespace (storage/evidence/...).
    Never accessible to other tenant organizations.
    """
    task = await db.get(ComplianceTask, task_id)
    if not task or task.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Task not found in this organization.")

    if (
        membership.role not in ["ORG_ADMIN", "COMPLIANCE_HEAD", "COMPLIANCE_OFFICER", "DEPARTMENT_LEAD"]
        and task.assigned_to_user_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions: Only the assigned user, department leads, or compliance officers can submit evidence."
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty evidence file.")
    if len(content) > MAX_EVIDENCE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Evidence file exceeds 50MB limit.")

    # Store file in private evidence namespace
    storage_path, file_sha256, file_size = storage_service.store_file(
        namespace=f"evidence/{organization_id}/{task_id}",
        filename_prefix="evidence",
        content=content,
        extension=f".{file.filename.split('.')[-1]}" if "." in (file.filename or "") else ".bin"
    )

    evidence = TaskEvidence(
        organization_id=organization_id,
        task_id=task_id,
        submitted_by_user_id=current_user.id,
        file_sha256=file_sha256,
        storage_path=storage_path,
        original_filename=file.filename or "evidence.bin",
        file_size_bytes=file_size,
        notes=notes
    )
    db.add(evidence)

    # Transition task status to SUBMITTED
    task.status = "SUBMITTED"

    event = TaskEvent(
        task_id=task_id,
        actor_user_id=current_user.id,
        event_type="EVIDENCE_SUBMITTED",
        event_payload={"filename": evidence.original_filename, "sha256": file_sha256}
    )
    db.add(event)
    await db.commit()
    await db.refresh(evidence)
    return evidence


@router.get("/tasks/{task_id}/evidence", response_model=List[TaskEvidenceRead])
async def list_task_evidence(
    organization_id: UUID,
    task_id: UUID,
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_async_db)
):
    task = await db.get(ComplianceTask, task_id)
    if not task or task.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Task not found in this organization.")

    query = select(TaskEvidence).where(
        TaskEvidence.organization_id == organization_id,
        TaskEvidence.task_id == task_id
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/tasks/{task_id}/evidence/{evidence_id}/download")
async def download_task_evidence(
    organization_id: UUID,
    task_id: UUID,
    evidence_id: UUID,
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Secure evidence download stream:
    Strictly verifies organization membership before serving raw file.
    Cross-tenant requests return 403 / 404.
    """
    evidence = await db.get(TaskEvidence, evidence_id)
    if not evidence or evidence.organization_id != organization_id or evidence.task_id != task_id:
        raise HTTPException(status_code=404, detail="Evidence record not found.")

    try:
        file_bytes = storage_service.get_file_bytes(evidence.storage_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Evidence file missing from storage.")

    return StreamingResponse(
        BytesIO(file_bytes),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=\"{evidence.original_filename}\"",
            "Content-Length": str(len(file_bytes)),
            "X-SHA256-Checksum": evidence.file_sha256
        }
    )


# ---------------------------------------------------------------------------
# Task Reviews & Signoffs
# ---------------------------------------------------------------------------
@router.post("/tasks/{task_id}/reviews", response_model=TaskReviewRead, status_code=status.HTTP_201_CREATED)
async def review_task(
    organization_id: UUID,
    task_id: UUID,
    payload: TaskReviewCreate,
    membership: OrganizationMember = Depends(get_org_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Enforces that only COMPLIANCE_HEAD, ORG_ADMIN, or DEPARTMENT_LEAD can sign off on evidence.
    """
    if membership.role not in ["ORG_ADMIN", "COMPLIANCE_HEAD", "DEPARTMENT_LEAD"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions: Only Compliance Leads or Admins can review tasks."
        )

    task = await db.get(ComplianceTask, task_id)
    if not task or task.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Task not found in this organization.")

    review = TaskReview(
        task_id=task_id,
        reviewer_user_id=current_user.id,
        decision=payload.decision,
        comments=payload.comments
    )
    db.add(review)

    # Update task status based on review decision
    if payload.decision == "APPROVED":
        task.status = "APPROVED"
    elif payload.decision == "CHANGES_REQUESTED":
        task.status = "IN_PROGRESS"
    elif payload.decision == "REJECTED":
        task.status = "REJECTED"

    event = TaskEvent(
        task_id=task_id,
        actor_user_id=current_user.id,
        event_type="REVIEW_COMPLETED",
        event_payload={"decision": payload.decision, "comments": payload.comments}
    )
    db.add(event)
    await db.commit()
    await db.refresh(review)
    return review

