"""Bank compliance workspace: registers and items (tasks, evidence, audit and report live next to this file)."""
from datetime import date, datetime
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.session import get_async_db
from backend.app.modules.alerts import hooks as alert_hooks
from backend.app.modules.audit import service as audit
from backend.app.modules.compliance import permissions as perms
from backend.app.modules.compliance import rules
from backend.app.modules.compliance.models import (
    ComplianceItem,
    ComplianceItemReview,
    ComplianceRegister,
    ComplianceTask,
    TaskReview,
)
from backend.app.modules.compliance.schemas import (
    AcknowledgeChange,
    AddableDocument,
    AddableObligation,
    AddableObligations,
    DocRef,
    FromDocument,
    ItemCreate,
    ItemDetail,
    ItemList,
    ItemRead,
    ItemSignoff,
    ItemSignoffResult,
    ItemStatusChange,
    ItemsAdded,
    ItemUpdate,
    RegisterCreate,
    RegisterCreated,
    RegisterFromDocument,
    RegisterRead,
    RegisterUpdate,
    ReopenItem,
    Skipped,
)
from backend.app.modules.compliance.service import (
    ItemFilter,
    build_evidence,
    build_item_reviews,
    build_items,
    build_registers,
    build_task_reviews,
    build_tasks,
    current_source_change,
    get_item_or_404,
    get_register_or_404,
    item_evidence,
    item_tasks,
    load_items,
    now_utc,
    one_item,
    signature_for,
    source_context,
)
from backend.app.modules.compliance.workflow import (
    bump,
    check_item_lock,
    forbidden,
    item_state,
    move_item,
    require,
    require_department,
    require_member_user,
)
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.identity.models import User
from backend.app.modules.obligations.models import Obligation
from backend.app.modules.organizations.deps import get_workspace_membership
from backend.app.modules.organizations.models import Department, OrganizationMember
from backend.app.modules.compliance.routes_tasks import router as tasks_router
from backend.app.modules.compliance.routes_reports import router as reports_router

router = APIRouter(
    prefix="/organizations/{organization_id}/compliance",
    tags=["Compliance Workflows (Tenant Isolated)"]
)
router.include_router(tasks_router)
router.include_router(reports_router)


# ---------------------------------------------------------------------------
# Checks shared by the routes below
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# What may be added from a circular (section 6.1)
# ---------------------------------------------------------------------------
def not_addable_reason(doc: Document, version_id, current_version_id, verification_status: str) -> Optional[str]:
    if doc.owner_user_id is not None:
        return "Private upload"
    if not str(doc.publication_status or "").startswith("PUBLISHED"):
        return "Circular not published yet"
    if current_version_id is None or str(version_id) != str(current_version_id):
        return "Older version of this circular"
    if verification_status != "VERIFIED":
        return "Awaiting quote check"
    return None


async def _shared_document_or_404(db: AsyncSession, document_id: UUID) -> Document:
    doc = await db.get(Document, document_id)
    if not doc or doc.owner_user_id is not None:
        raise HTTPException(status_code=404, detail="Circular not found.")
    return doc


async def _obligations_with_pages(db: AsyncSession, doc: Document, ids: Optional[List[UUID]] = None):
    query = (
        select(Obligation, DocumentPage.page_number, DocumentVersion)
        .join(DocumentVersion, DocumentVersion.id == Obligation.document_version_id)
        .join(DocumentPage, DocumentPage.id == Obligation.page_id)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc(), DocumentPage.page_number, Obligation.created_at, Obligation.id)
    )
    if ids is not None:
        query = query.where(Obligation.id.in_(list(ids)))
    return (await db.execute(query)).all()


def make_source_key(obl: Obligation, version: DocumentVersion, page_number: int) -> str:
    return rules.source_key(str(version.id), page_number, obl.supporting_text)


async def _create_items(
    db: AsyncSession,
    *,
    organization_id: UUID,
    register: ComplianceRegister,
    doc: Document,
    rows,
    actor_user_id,
    request: Request,
    defaults: Optional[dict] = None,
):
    """Adds the given (obligation, page number, version) rows to a register. Returns (items, skipped)."""
    defaults = defaults or {}
    ctx = await source_context(db, [doc.id])
    probe = ComplianceItem(source_document_id=doc.id, source_version_id=doc.current_version_id)
    signature, *_ = signature_for(probe, ctx)
    existing = {
        k for (k,) in (await db.execute(
            select(ComplianceItem.source_key).where(ComplianceItem.register_id == register.id)
        )).all() if k
    }
    items: List[ComplianceItem] = []
    skipped: List[Skipped] = []
    for obl, page_number, version in rows:
        reason = not_addable_reason(doc, version.id, doc.current_version_id, obl.verification_status)
        if reason:
            skipped.append(Skipped(obligation_id=obl.id, reason=reason))
            continue
        key = make_source_key(obl, version, page_number)
        if key in existing:
            skipped.append(Skipped(obligation_id=obl.id, reason="Already in this register"))
            continue
        existing.add(key)
        item = ComplianceItem(
            organization_id=organization_id,
            register_id=register.id,
            obligation_id=obl.id,
            status="NOT_STARTED",
            source_document_id=doc.id,
            source_version_id=version.id,
            source_file_sha256=version.file_sha256,
            source_reference_number=doc.reference_number,
            source_title=doc.title,
            source_publication_date=doc.publication_date,
            source_page_number=page_number,
            source_quote=obl.supporting_text,
            source_quote_span_ids=obl.quote_span_ids,
            source_quote_boxes=obl.quote_boxes,
            source_key=key,
            obligation_title=obl.title,
            requirement_description=obl.requirement_description,
            obligation_type=obl.obligation_type,
            applicability_summary=obl.applicability_summary,
            regulatory_deadline=obl.explicit_deadline,
            deadline_description=obl.deadline_description,
            frequency=obl.frequency,
            source_ack_signature=signature,
            lock_version=1,
            **defaults,
        )
        db.add(item)
        items.append(item)
    await db.flush()
    for item in items:
        audit.record(
            db, organization_id=organization_id, actor_user_id=actor_user_id, action="ITEM_ADDED",
            entity_type="compliance_item", entity_id=item.id,
            after={
                "register_id": str(register.id), "obligation_title": item.obligation_title,
                "source_reference_number": item.source_reference_number, "source_page_number": item.source_page_number,
            },
            request=request,
        )
    return items, skipped


@router.get("/documents/{document_id}/addable-obligations", response_model=AddableObligations)
async def addable_obligations(
    organization_id: UUID,
    document_id: UUID,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db),
):
    doc = await _shared_document_or_404(db, document_id)
    rows = await _obligations_with_pages(db, doc)
    ctx = await source_context(db, [doc.id])
    probe = ComplianceItem(source_document_id=doc.id, source_version_id=doc.current_version_id)
    _sig, in_force_status, _doc, _withdrawn, by = signature_for(probe, ctx)
    keys = {make_source_key(o, v, p): o.id for o, p, v in rows}
    in_registers: Dict[str, List[UUID]] = {}
    if keys:
        found = (await db.execute(
            select(ComplianceItem.source_key, ComplianceItem.register_id)
            .where(ComplianceItem.organization_id == organization_id, ComplianceItem.source_key.in_(list(keys)))
        )).all()
        for k, rid in found:
            in_registers.setdefault(k, []).append(rid)
    obligations = []
    for obl, page_number, version in rows:
        reason = not_addable_reason(doc, version.id, doc.current_version_id, obl.verification_status)
        obligations.append(AddableObligation(
            id=obl.id, title=obl.title, obligation_type=obl.obligation_type, page_number=page_number,
            quote=obl.supporting_text, regulatory_deadline=obl.explicit_deadline,
            verification_status=obl.verification_status, addable=reason is None, reason_not_addable=reason,
            already_in_register_ids=in_registers.get(make_source_key(obl, version, page_number), []),
        ))
    return AddableObligations(
        document=AddableDocument(
            id=doc.id, reference_number=doc.reference_number, title=doc.title,
            publication_status=doc.publication_status, in_force_status=in_force_status,
            in_force_by=DocRef(id=by.id, reference_number=by.reference_number, title=by.title) if by else None,
            current_version_id=doc.current_version_id,
        ),
        obligations=obligations,
    )


async def _addable_rows(db: AsyncSession, doc: Document, ids: Optional[List[UUID]]):
    """Rows to add: the given ids (anything not part of this circular is reported), or every addable obligation."""
    rows = await _obligations_with_pages(db, doc, ids)
    skipped: List[Skipped] = []
    if ids is not None:
        found = {str(r[0].id) for r in rows}
        skipped = [Skipped(obligation_id=i, reason="Not part of this circular") for i in ids if str(i) not in found]
    else:
        rows = [
            r for r in rows
            if not_addable_reason(doc, r[2].id, doc.current_version_id, r[0].verification_status) is None
        ]
    return rows, skipped


# ---------------------------------------------------------------------------
# Registers
# ---------------------------------------------------------------------------
@router.post("/registers", response_model=RegisterRead, status_code=status.HTTP_201_CREATED)
async def create_register(
    organization_id: UUID,
    payload: RegisterCreate,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    require(perms.can_manage_registers(membership),
            "Only Organization Admins, Compliance Heads or Compliance Officers can create compliance registers.")
    register = ComplianceRegister(organization_id=organization_id, title=payload.title, description=payload.description)
    db.add(register)
    await db.flush()
    audit.record(
        db, organization_id=organization_id, actor_user_id=membership.user_id, action="REGISTER_CREATED",
        entity_type="register", entity_id=register.id, after={"title": register.title}, request=request,
    )
    await db.commit()
    await db.refresh(register)
    return (await build_registers(db, organization_id, [register]))[0]


@router.get("/registers", response_model=List[RegisterRead])
async def list_registers(
    organization_id: UUID,
    include_archived: bool = Query(False),
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    query = select(ComplianceRegister).where(ComplianceRegister.organization_id == organization_id)
    if not include_archived:
        query = query.where(ComplianceRegister.is_active.is_(True))
    rows = (await db.execute(query.order_by(ComplianceRegister.title, ComplianceRegister.id))).scalars().all()
    return await build_registers(db, organization_id, list(rows))


@router.get("/registers/{register_id}", response_model=RegisterRead)
async def get_register(
    organization_id: UUID,
    register_id: UUID,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    register = await get_register_or_404(db, organization_id, register_id)
    return (await build_registers(db, organization_id, [register]))[0]


@router.patch("/registers/{register_id}", response_model=RegisterRead)
async def update_register(
    organization_id: UUID,
    register_id: UUID,
    payload: RegisterUpdate,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    require(perms.can_manage_registers(membership), "Only compliance staff can change registers.")
    register = await get_register_or_404(db, organization_id, register_id)
    fields = ("title", "description", "is_active")
    before = audit.pick(register, fields)
    sent = payload.model_fields_set
    if "title" in sent and payload.title is not None:
        register.title = payload.title
    if "description" in sent:
        register.description = payload.description
    if "is_active" in sent and payload.is_active is not None:
        register.is_active = payload.is_active
    b, a = audit.changed(before, audit.pick(register, fields))
    if a:
        audit.record(
            db, organization_id=organization_id, actor_user_id=membership.user_id, action="REGISTER_UPDATED",
            entity_type="register", entity_id=register.id, before=b, after=a, request=request,
        )
    await db.commit()
    await db.refresh(register)
    return (await build_registers(db, organization_id, [register]))[0]


@router.post("/registers/from-document", response_model=RegisterCreated, status_code=status.HTTP_201_CREATED)
async def create_register_from_document(
    organization_id: UUID,
    payload: RegisterFromDocument,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    require(perms.can_add_items(membership), "Only compliance staff can add items to a register.")
    doc = await _shared_document_or_404(db, payload.document_id)
    rows, skipped = await _addable_rows(db, doc, payload.obligation_ids)
    title = (payload.title or f"{doc.reference_number or 'Circular'}: {doc.title}")[:255]
    register = ComplianceRegister(organization_id=organization_id, title=title)
    db.add(register)
    await db.flush()
    audit.record(
        db, organization_id=organization_id, actor_user_id=membership.user_id, action="REGISTER_CREATED",
        entity_type="register", entity_id=register.id, after={"title": title, "from_document_id": str(doc.id)},
        request=request,
    )
    items, more_skipped = await _create_items(
        db, organization_id=organization_id, register=register, doc=doc, rows=rows,
        actor_user_id=membership.user_id, request=request,
    )
    await db.commit()
    await db.refresh(register)
    return RegisterCreated(
        register=(await build_registers(db, organization_id, [register]))[0],
        items=await build_items(db, items),
        skipped=skipped + more_skipped,
    )


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------
@router.post("/registers/{register_id}/items/from-document", response_model=ItemsAdded, status_code=status.HTTP_201_CREATED)
async def add_items_from_document(
    organization_id: UUID,
    register_id: UUID,
    payload: FromDocument,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    require(perms.can_add_items(membership), "Only compliance staff can add items to a register.")
    register = await get_register_or_404(db, organization_id, register_id)
    doc = await _shared_document_or_404(db, payload.document_id)
    rows, skipped = await _addable_rows(db, doc, payload.obligation_ids)
    items, more_skipped = await _create_items(
        db, organization_id=organization_id, register=register, doc=doc, rows=rows,
        actor_user_id=membership.user_id, request=request,
    )
    await db.commit()
    return ItemsAdded(items=await build_items(db, items), skipped=skipped + more_skipped)


@router.post("/items", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
async def create_compliance_item(
    organization_id: UUID,
    payload: ItemCreate,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    require(perms.can_add_items(membership),
            "Only Compliance Officers, Heads, or Admins can create compliance items.")
    register = await db.get(ComplianceRegister, payload.register_id)
    if not register or register.organization_id != organization_id:
        raise HTTPException(status_code=400, detail="Invalid register for this organization.")

    rows = (await db.execute(
        select(Obligation, DocumentPage.page_number, DocumentVersion, Document)
        .join(DocumentVersion, DocumentVersion.id == Obligation.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(DocumentPage, DocumentPage.id == Obligation.page_id)
        .where(Obligation.id == payload.obligation_id)
    )).all()
    if not rows:
        raise HTTPException(status_code=400, detail="Obligation not found.")
    obl, page_number, version, doc = rows[0]
    reason = not_addable_reason(doc, version.id, doc.current_version_id, obl.verification_status)
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    await require_department(db, organization_id, payload.department_id)
    await require_member_user(db, organization_id, payload.assigned_lead_id, "Assigned lead")

    items, skipped = await _create_items(
        db, organization_id=organization_id, register=register, doc=doc, rows=[(obl, page_number, version)],
        actor_user_id=membership.user_id, request=request,
        defaults={
            "internal_code": payload.internal_code,
            "department_id": payload.department_id,
            "assigned_lead_id": payload.assigned_lead_id,
            "internal_deadline": payload.internal_deadline,
        },
    )
    if not items:
        raise HTTPException(status_code=409, detail=skipped[0].reason if skipped else "Nothing was added.")
    if items[0].assigned_lead_id:
        await alert_hooks.item_lead_assigned(db, organization_id, items[0], membership.user_id)
    await db.commit()
    return (await build_items(db, items))[0]


@router.get("/items", response_model=ItemList)
async def list_compliance_items(
    organization_id: UUID,
    register_id: Optional[UUID] = Query(None),
    display_status: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    department_id: Optional[UUID] = Query(None),
    lead_id: Optional[UUID] = Query(None),
    overdue: Optional[bool] = Query(None),
    flagged: Optional[bool] = Query(None),
    due_before: Optional[date] = Query(None),
    q: Optional[str] = Query(None, max_length=200),
    updated_since: Optional[datetime] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    f = ItemFilter(
        register_id=register_id, display_status=display_status or status_filter, department_id=department_id,
        lead_id=lead_id, overdue=overdue, flagged=flagged, due_before=due_before, q=q,
        updated_since=updated_since, limit=limit, offset=offset,
    )
    today = rules.today_dhaka()
    _rows, total, items = await load_items(db, organization_id, f, today)
    return ItemList(items=items, total=total, as_of=today, server_time=now_utc())


@router.get("/items/{item_id}", response_model=ItemDetail)
async def get_item(
    organization_id: UUID,
    item_id: UUID,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    item = await get_item_or_404(db, organization_id, item_id)
    tasks = await item_tasks(db, item.id)
    evidence = await item_evidence(db, item.id)
    task_reviews = list((await db.execute(
        select(TaskReview).where(TaskReview.task_id.in_([t.id for t in tasks] or [item.id])).order_by(TaskReview.created_at, TaskReview.id)
    )).scalars().all()) if tasks else []
    item_reviews = list((await db.execute(
        select(ComplianceItemReview).where(ComplianceItemReview.item_id == item.id)
        .order_by(ComplianceItemReview.created_at, ComplianceItemReview.id)
    )).scalars().all())
    return ItemDetail(
        item=await one_item(db, item),
        tasks=await build_tasks(db, tasks),
        evidence=await build_evidence(db, evidence),
        task_reviews=await build_task_reviews(db, task_reviews),
        item_reviews=await build_item_reviews(db, item_reviews),
    )


@router.patch("/items/{item_id}", response_model=ItemRead)
async def update_item(
    organization_id: UUID,
    item_id: UUID,
    payload: ItemUpdate,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    item = await get_item_or_404(db, organization_id, item_id)
    require(perms.can_edit_item(membership, item), "You cannot change this item.")
    await check_item_lock(db, item, payload.lock_version)
    sent = payload.model_fields_set
    is_lead_only = membership.role == perms.LEAD
    before = item_state(item)
    old_lead = item.assigned_lead_id

    if "department_id" in sent:
        if is_lead_only and payload.department_id != item.department_id:
            raise forbidden("Insufficient permissions: department leads cannot move an item to another department.")
        await require_department(db, organization_id, payload.department_id)
        item.department_id = payload.department_id
    if "assigned_lead_id" in sent:
        lead = await require_member_user(db, organization_id, payload.assigned_lead_id, "Assigned lead")
        if is_lead_only and lead is not None and str(lead.department_id) != str(membership.department_id):
            raise forbidden("Insufficient permissions: department leads can only pick a lead from their own department.")
        item.assigned_lead_id = payload.assigned_lead_id
    if "internal_deadline" in sent:
        item.internal_deadline = payload.internal_deadline
    if "internal_code" in sent:
        item.internal_code = payload.internal_code or None
    if "notes" in sent:
        item.notes = payload.notes or None

    b, a = audit.changed(before, item_state(item))
    if a:
        bump(item)
        audit.record(
            db, organization_id=organization_id, actor_user_id=membership.user_id, action="ITEM_UPDATED",
            entity_type="compliance_item", entity_id=item.id, before=b, after=a, request=request,
        )
        if item.assigned_lead_id and item.assigned_lead_id != old_lead:
            await alert_hooks.item_lead_assigned(db, organization_id, item, membership.user_id)
    await db.commit()
    await db.refresh(item)
    return await one_item(db, item)


def _tasks_ready_reason(tasks: List[ComplianceTask], evidence_count: int) -> Optional[str]:
    live = [t for t in tasks if t.status != "CANCELLED"]
    if not live:
        return "Add a task first."
    if any(t.status != "APPROVED" for t in live):
        return "Approve all tasks first."
    if evidence_count == 0:
        return "Add at least one evidence file."
    return None


@router.post("/items/{item_id}/status", response_model=ItemRead)
async def change_item_status(
    organization_id: UUID,
    item_id: UUID,
    payload: ItemStatusChange,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    item = await get_item_or_404(db, organization_id, item_id)
    await check_item_lock(db, item, payload.lock_version)
    frm, to = item.status, payload.to
    cannot = HTTPException(status_code=409, detail=f"This item cannot move from {frm} to {to}.")

    if to == "IN_PROGRESS":
        if frm != "NOT_STARTED":
            raise cannot
        require(perms.can_start_item(membership, item), "You cannot start this item.")
        move_item(db, item, "IN_PROGRESS", actor_user_id=membership.user_id, request=request)
    elif to == "EVIDENCE_SUBMITTED":
        if frm != "IN_PROGRESS":
            raise cannot
        require(perms.can_start_item(membership, item), "You cannot send this item for sign-off.")
        tasks = await item_tasks(db, item.id)
        evidence = [e for e in await item_evidence(db, item.id) if e.withdrawn_at is None]
        reason = _tasks_ready_reason(tasks, len(evidence))
        if reason:
            raise HTTPException(status_code=409, detail=reason)
        move_item(db, item, "EVIDENCE_SUBMITTED", actor_user_id=membership.user_id, request=request)
        await alert_hooks.item_awaiting_signoff(db, organization_id, item, membership.user_id)
    elif to == "EXEMPTED":
        if frm in ("COMPLIANT", "EXEMPTED"):
            raise cannot
        require(perms.can_exempt_and_reopen(membership), "Only admins and compliance heads can exempt an item.")
        if not payload.reason:
            raise HTTPException(status_code=400, detail="A reason is required to exempt an item.")
        move_item(db, item, "EXEMPTED", actor_user_id=membership.user_id, request=request, reason=payload.reason)
    elif to == "NOT_STARTED":
        if frm != "EXEMPTED":
            raise cannot
        require(perms.can_exempt_and_reopen(membership), "Only admins and compliance heads can remove an exemption.")
        move_item(db, item, "NOT_STARTED", actor_user_id=membership.user_id, request=request)
        if any(t.status != "CANCELLED" for t in await item_tasks(db, item.id)):
            move_item(db, item, "IN_PROGRESS", actor_user_id=membership.user_id, request=request,
                      cause="the item already has tasks")
    await db.commit()
    await db.refresh(item)
    return await one_item(db, item)


@router.post("/items/{item_id}/signoff", response_model=ItemSignoffResult, status_code=status.HTTP_201_CREATED)
async def sign_off_item(
    organization_id: UUID,
    item_id: UUID,
    payload: ItemSignoff,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    item = await get_item_or_404(db, organization_id, item_id)
    require(perms.can_sign_off_role(membership), "Only admins, compliance heads and reviewers can sign off an item.")
    if item.status != "EVIDENCE_SUBMITTED":
        raise HTTPException(status_code=409, detail="This item is not waiting for sign-off.")
    block = perms.signoff_block(membership.user_id, item, await item_evidence(db, item.id))
    if block:
        raise forbidden(block)
    if payload.decision == "REJECTED" and not payload.comments:
        raise HTTPException(status_code=400, detail="Comments are required when sending an item back.")
    review = ComplianceItemReview(
        item_id=item.id, organization_id=organization_id, reviewer_user_id=membership.user_id,
        decision=payload.decision, comments=payload.comments,
    )
    db.add(review)
    await db.flush()
    submitted_by = item.submitted_for_signoff_by_user_id  # move_item clears it
    move_item(
        db, item, "COMPLIANT" if payload.decision == "APPROVED" else "IN_PROGRESS",
        actor_user_id=membership.user_id, request=request, action="ITEM_SIGNED_OFF",
        reason=payload.comments or None,
    )
    await alert_hooks.item_signoff_decided(db, organization_id, item, review, membership.user_id, submitted_by)
    await db.commit()
    await db.refresh(item)
    await db.refresh(review)
    return ItemSignoffResult(
        item=await one_item(db, item), review=(await build_item_reviews(db, [review]))[0]
    )


@router.post("/items/{item_id}/acknowledge-source-change", response_model=ItemRead)
async def acknowledge_source_change(
    organization_id: UUID,
    item_id: UUID,
    payload: AcknowledgeChange,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    item = await get_item_or_404(db, organization_id, item_id)
    require(perms.can_acknowledge(membership), "Only compliance staff can mark a circular change as reviewed.")
    ctx = await source_context(db, [item.source_document_id])
    change = current_source_change(item, ctx)
    if change is None:
        raise HTTPException(status_code=409, detail="This circular has not changed since it was last reviewed.")
    signature, *_ = signature_for(item, ctx)
    old = item.source_ack_signature or rules.baseline_signature(item.source_version_id)
    item.source_ack_signature = signature
    item.source_ack_at = now_utc()
    item.source_ack_by_user_id = membership.user_id
    item.source_ack_note = payload.note
    bump(item)
    audit.record(
        db, organization_id=organization_id, actor_user_id=membership.user_id,
        action="ITEM_SOURCE_CHANGE_ACKNOWLEDGED", entity_type="compliance_item", entity_id=item.id,
        before={"source_ack_signature": old},
        after={"source_ack_signature": signature, "note": payload.note, "source_change": change.model_dump(mode="json")},
        request=request,
    )
    await db.commit()
    await db.refresh(item)
    return await one_item(db, item)


@router.post("/items/{item_id}/reopen", response_model=ItemRead)
async def reopen_item(
    organization_id: UUID,
    item_id: UUID,
    payload: ReopenItem,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    item = await get_item_or_404(db, organization_id, item_id)
    require(perms.can_exempt_and_reopen(membership), "Only admins and compliance heads can reopen an item.")
    if item.status != "COMPLIANT":
        raise HTTPException(status_code=409, detail=f"This item cannot move from {item.status} to IN_PROGRESS.")
    move_item(db, item, "IN_PROGRESS", actor_user_id=membership.user_id, request=request, reason=payload.reason)
    await db.commit()
    await db.refresh(item)
    return await one_item(db, item)
