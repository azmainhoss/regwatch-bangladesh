"""Loads and shapes workspace records: users, source circulars, overdue flags, counts, source changes.

Every list is built with a fixed number of queries (no per-item lookups).
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.compliance import rules
from backend.app.modules.compliance.models import (
    ComplianceItem,
    ComplianceItemReview,
    ComplianceRegister,
    ComplianceTask,
    TaskEvidence,
    TaskReview,
)
from backend.app.modules.compliance.schemas import (
    DocRef,
    EvidenceRead,
    ItemCounts,
    ItemRead,
    ItemReviewRead,
    RegisterRead,
    SourceChange,
    SourceRef,
    TaskCounts,
    TaskRead,
    TaskReviewRead,
)
from backend.app.modules.documents.models import Document
from backend.app.modules.identity.models import User
from backend.app.modules.organizations.schemas import UserMini
from backend.app.modules.relationships.status import InForce, bulk_in_force


class ConflictError(Exception):
    """Raised when a save was made against an out-of-date copy. `current` is the fresh record."""

    def __init__(self, message: str, current):
        super().__init__(message)
        self.message = message
        self.current = current


def utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
async def users_map(db: AsyncSession, ids: Iterable) -> Dict[str, UserMini]:
    wanted = list({str(i): i for i in ids if i is not None}.values())
    if not wanted:
        return {}
    rows = (await db.execute(select(User).where(User.id.in_(wanted)))).scalars().all()
    return {str(u.id): UserMini(id=u.id, full_name=u.full_name, email=u.email) for u in rows}


def mini(users: Dict[str, UserMini], uid) -> Optional[UserMini]:
    return users.get(str(uid)) if uid is not None else None


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------
def eff_deadline_sql():
    return func.coalesce(ComplianceItem.internal_deadline, ComplianceItem.regulatory_deadline)


def overdue_sql(today: date):
    return and_(
        ComplianceItem.status.in_(rules.ITEM_OVERDUE_STATUSES),
        eff_deadline_sql().is_not(None),
        eff_deadline_sql() < today,
    )


@dataclass
class ItemFilter:
    register_id: Optional[UUID] = None
    display_status: Optional[str] = None
    department_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    overdue: Optional[bool] = None
    flagged: Optional[bool] = None
    due_before: Optional[date] = None
    q: Optional[str] = None
    updated_since: Optional[datetime] = None
    limit: int = 500
    offset: int = 0
    ids: Optional[Sequence[UUID]] = None
    include_archived: bool = True


async def _task_counts(db: AsyncSession, item_ids: Sequence, today: date) -> Dict[str, TaskCounts]:
    if not item_ids:
        return {}
    overdue_flag = case(
        (and_(ComplianceTask.status.in_(rules.TASK_OVERDUE_STATUSES), ComplianceTask.due_date < today), 1),
        else_=0,
    )
    rows = (await db.execute(
        select(
            ComplianceTask.compliance_item_id,
            ComplianceTask.status,
            func.count(ComplianceTask.id),
            func.sum(overdue_flag),
        )
        .where(ComplianceTask.compliance_item_id.in_(item_ids), ComplianceTask.status != "CANCELLED")
        .group_by(ComplianceTask.compliance_item_id, ComplianceTask.status)
    )).all()
    out: Dict[str, TaskCounts] = {}
    for item_id, status, count, overdue in rows:
        c = out.setdefault(str(item_id), TaskCounts())
        c.total += count
        if status in rules.TASK_OPEN_STATUSES:
            c.open += count
        elif status == "SUBMITTED":
            c.submitted += count
        elif status == "APPROVED":
            c.approved += count
        c.overdue += int(overdue or 0)
    return out


async def _evidence_counts_by_item(db: AsyncSession, item_ids: Sequence) -> Dict[str, int]:
    if not item_ids:
        return {}
    rows = (await db.execute(
        select(ComplianceTask.compliance_item_id, func.count(TaskEvidence.id))
        .join(TaskEvidence, TaskEvidence.task_id == ComplianceTask.id)
        .where(ComplianceTask.compliance_item_id.in_(item_ids), TaskEvidence.withdrawn_at.is_(None))
        .group_by(ComplianceTask.compliance_item_id)
    )).all()
    return {str(k): v for k, v in rows}


def _doc_ref(doc: Optional[Document]) -> Optional[DocRef]:
    if doc is None:
        return None
    return DocRef(id=doc.id, reference_number=doc.reference_number, title=doc.title)


@dataclass
class SourceContext:
    docs: Dict[str, Document] = field(default_factory=dict)
    in_force: Dict[str, InForce] = field(default_factory=dict)


async def source_context(db: AsyncSession, doc_ids: Iterable) -> SourceContext:
    ids = list({str(i): i for i in doc_ids if i is not None}.values())
    if not ids:
        return SourceContext()
    docs = (await db.execute(select(Document).where(Document.id.in_(ids)))).scalars().all()
    in_force = await bulk_in_force(db, ids, user=None)  # shared library only
    return SourceContext(docs={str(d.id): d for d in docs}, in_force=in_force)


def signature_for(item: ComplianceItem, ctx: SourceContext) -> Tuple[str, str, Optional[Document], bool, Optional[Document]]:
    """(current signature, in-force status, circular, withdrawn, in-force-by circular)."""
    doc = ctx.docs.get(str(item.source_document_id)) if item.source_document_id else None
    inf = ctx.in_force.get(str(item.source_document_id), InForce()) if item.source_document_id else InForce()
    withdrawn = bool(doc is not None and doc.publication_status == "WITHDRAWN")
    sig = rules.source_signature(
        inf.status, inf.by.id if inf.by else None, doc.current_version_id if doc else None, withdrawn
    )
    return sig, inf.status, doc, withdrawn, inf.by


def current_source_change(item: ComplianceItem, ctx: SourceContext) -> Optional[SourceChange]:
    if item.source_document_id is None:
        return None
    sig, status, doc, withdrawn, by = signature_for(item, ctx)
    acked = item.source_ack_signature or rules.baseline_signature(item.source_version_id)
    if sig == acked:
        return None
    kind = rules.change_kind(status, doc.current_version_id if doc else None, item.source_version_id, withdrawn)
    if kind is None:
        return None
    return SourceChange(kind=kind, by=_doc_ref(by), detail=rules.change_text(kind, by.reference_number if by else None))


async def build_items(
    db: AsyncSession, items: Sequence[ComplianceItem], today: Optional[date] = None
) -> List[ItemRead]:
    today = today or rules.today_dhaka()
    if not items:
        return []
    item_ids = [i.id for i in items]
    users = await users_map(
        db,
        [x for i in items for x in (i.assigned_lead_id, i.submitted_for_signoff_by_user_id, i.signed_off_by_user_id)],
    )
    ctx = await source_context(db, [i.source_document_id for i in items])
    task_counts = await _task_counts(db, item_ids, today)
    evidence_counts = await _evidence_counts_by_item(db, item_ids)

    out: List[ItemRead] = []
    for i in items:
        overdue = rules.is_item_overdue(i.status, i.internal_deadline, i.regulatory_deadline, today)
        eff = rules.effective_deadline(i.internal_deadline, i.regulatory_deadline)
        _sig, in_force_status, doc, withdrawn, by = signature_for(i, ctx)
        page_link = None
        if i.source_document_id and i.source_version_id:
            page_link = f"/?doc={i.source_document_id}&version={i.source_version_id}&page={i.source_page_number or 1}"
        source = SourceRef(
            document_id=i.source_document_id,
            version_id=i.source_version_id,
            reference_number=i.source_reference_number,
            title=i.source_title,
            publication_date=i.source_publication_date,
            page_number=i.source_page_number,
            quote=i.source_quote,
            quote_span_ids=i.source_quote_span_ids,
            quote_boxes=i.source_quote_boxes,
            file_sha256=i.source_file_sha256,
            page_link=page_link,
            in_force_status=in_force_status,
            in_force_by=_doc_ref(by),
            current_version_id=doc.current_version_id if doc else None,
            is_withdrawn=withdrawn,
        )
        out.append(ItemRead(
            id=i.id,
            organization_id=i.organization_id,
            register_id=i.register_id,
            internal_code=i.internal_code,
            obligation_id=i.obligation_id,
            obligation_title=i.obligation_title,
            requirement_description=i.requirement_description,
            obligation_type=i.obligation_type,
            applicability_summary=i.applicability_summary,
            frequency=i.frequency,
            regulatory_deadline=i.regulatory_deadline,
            deadline_description=i.deadline_description,
            internal_deadline=i.internal_deadline,
            effective_deadline=eff,
            status=i.status,
            display_status=rules.display_status(i.status, overdue),
            is_overdue=overdue,
            days_left=rules.days_left(eff, today),
            department_id=i.department_id,
            assigned_lead=mini(users, i.assigned_lead_id),
            notes=i.notes,
            exemption_reason=i.exemption_reason,
            submitted_for_signoff_by=mini(users, i.submitted_for_signoff_by_user_id),
            submitted_for_signoff_at=utc(i.submitted_for_signoff_at),
            signed_off_by=mini(users, i.signed_off_by_user_id),
            signed_off_at=utc(i.signed_off_at),
            source=source,
            source_change=current_source_change(i, ctx),
            task_counts=task_counts.get(str(i.id), TaskCounts()),
            evidence_count=evidence_counts.get(str(i.id), 0),
            lock_version=i.lock_version,
            created_at=utc(i.created_at),
            updated_at=utc(i.updated_at),
        ))
    return out


async def load_items(
    db: AsyncSession, organization_id: UUID, f: ItemFilter, today: Optional[date] = None
) -> Tuple[List[ComplianceItem], int, List[ItemRead]]:
    """Items of one organization with the filters applied. Returns (rows, total, built items)."""
    today = today or rules.today_dhaka()
    query = select(ComplianceItem).where(ComplianceItem.organization_id == organization_id)
    if f.ids is not None:
        query = query.where(ComplianceItem.id.in_(list(f.ids)))
    if f.register_id:
        query = query.where(ComplianceItem.register_id == f.register_id)
    if not f.include_archived:
        query = query.join(ComplianceRegister, ComplianceRegister.id == ComplianceItem.register_id).where(
            ComplianceRegister.is_active.is_(True)
        )
    if f.department_id:
        query = query.where(ComplianceItem.department_id == f.department_id)
    if f.lead_id:
        query = query.where(ComplianceItem.assigned_lead_id == f.lead_id)
    if f.due_before:
        query = query.where(eff_deadline_sql().is_not(None), eff_deadline_sql() <= f.due_before)
    if f.updated_since:
        query = query.where(ComplianceItem.updated_at > utc(f.updated_since))
    if f.q:
        like = f"%{f.q.strip().lower()}%"
        query = query.where(or_(
            func.lower(func.coalesce(ComplianceItem.obligation_title, "")).like(like),
            func.lower(func.coalesce(ComplianceItem.source_quote, "")).like(like),
            func.lower(func.coalesce(ComplianceItem.source_reference_number, "")).like(like),
        ))
    od = overdue_sql(today)
    if f.overdue is True:
        query = query.where(od)
    elif f.overdue is False:
        query = query.where(~od)
    ds = f.display_status
    if ds == "OVERDUE":
        query = query.where(od)
    elif ds in ("NOT_STARTED", "IN_PROGRESS"):
        query = query.where(ComplianceItem.status == ds, ~od)
    elif ds in ("EVIDENCE_SUBMITTED", "COMPLIANT", "EXEMPTED"):
        query = query.where(ComplianceItem.status == ds)

    order = (ComplianceItem.created_at, ComplianceItem.id)
    if f.flagged is None:
        total = (await db.execute(select(func.count()).select_from(query.order_by(None).subquery()))).scalar_one()
        rows = (await db.execute(query.order_by(*order).limit(f.limit).offset(f.offset))).scalars().all()
        return list(rows), total, await build_items(db, rows, today)

    rows = (await db.execute(query.order_by(*order))).scalars().all()
    built = await build_items(db, rows, today)
    pairs = [(r, b) for r, b in zip(rows, built) if (b.source_change is not None) == f.flagged]
    total = len(pairs)
    pairs = pairs[f.offset:f.offset + f.limit]
    return [p[0] for p in pairs], total, [p[1] for p in pairs]


async def get_item_or_404(db: AsyncSession, organization_id: UUID, item_id: UUID) -> ComplianceItem:
    item = await db.get(ComplianceItem, item_id)
    if not item or item.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Item not found in this workspace.")
    return item


async def get_register_or_404(db: AsyncSession, organization_id: UUID, register_id: UUID) -> ComplianceRegister:
    reg = await db.get(ComplianceRegister, register_id)
    if not reg or reg.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Register not found in this workspace.")
    return reg


async def get_task_or_404(db: AsyncSession, organization_id: UUID, task_id: UUID) -> ComplianceTask:
    task = await db.get(ComplianceTask, task_id)
    if not task or task.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Task not found in this organization.")
    return task


async def one_item(db: AsyncSession, item: ComplianceItem) -> ItemRead:
    return (await build_items(db, [item]))[0]


# ---------------------------------------------------------------------------
# Registers
# ---------------------------------------------------------------------------
async def build_registers(db: AsyncSession, organization_id: UUID, registers: Sequence[ComplianceRegister]) -> List[RegisterRead]:
    if not registers:
        return []
    ids = [r.id for r in registers]
    rows = (await db.execute(
        select(ComplianceItem).where(ComplianceItem.organization_id == organization_id, ComplianceItem.register_id.in_(ids))
    )).scalars().all()
    built = await build_items(db, rows)
    counts: Dict[str, ItemCounts] = {str(r.id): ItemCounts() for r in registers}
    sources: Dict[str, List[UUID]] = {str(r.id): [] for r in registers}
    for row, b in zip(rows, built):
        c = counts[str(row.register_id)]
        c.total += 1
        key = {
            "NOT_STARTED": "not_started", "IN_PROGRESS": "in_progress", "EVIDENCE_SUBMITTED": "evidence_submitted",
            "COMPLIANT": "compliant", "EXEMPTED": "exempted", "OVERDUE": "overdue",
        }[b.display_status]
        setattr(c, key, getattr(c, key) + 1)
        if b.source_change is not None:
            c.flagged += 1
        if row.source_document_id and row.source_document_id not in sources[str(row.register_id)]:
            sources[str(row.register_id)].append(row.source_document_id)
    return [
        RegisterRead(
            id=r.id, organization_id=r.organization_id, title=r.title, description=r.description,
            is_active=r.is_active, created_at=utc(r.created_at), updated_at=utc(r.updated_at),
            item_counts=counts[str(r.id)], source_document_ids=sources[str(r.id)],
        )
        for r in registers
    ]


# ---------------------------------------------------------------------------
# Tasks, evidence, reviews
# ---------------------------------------------------------------------------
async def build_tasks(db: AsyncSession, tasks: Sequence[ComplianceTask], today: Optional[date] = None) -> List[TaskRead]:
    today = today or rules.today_dhaka()
    if not tasks:
        return []
    users = await users_map(db, [t.assigned_to_user_id for t in tasks])
    rows = (await db.execute(
        select(TaskEvidence.task_id, TaskEvidence.submitted_by_user_id, func.count(TaskEvidence.id))
        .where(TaskEvidence.task_id.in_([t.id for t in tasks]), TaskEvidence.withdrawn_at.is_(None))
        .group_by(TaskEvidence.task_id, TaskEvidence.submitted_by_user_id)
    )).all()
    ev: Dict[str, int] = {}
    uploaders: Dict[str, List] = {}
    for task_id, uploader, count in rows:
        ev[str(task_id)] = ev.get(str(task_id), 0) + count
        uploaders.setdefault(str(task_id), []).append(uploader)
    out = []
    for t in tasks:
        overdue = rules.is_task_overdue(t.status, t.due_date, today)
        out.append(TaskRead(
            id=t.id,
            organization_id=t.organization_id,
            compliance_item_id=t.compliance_item_id,
            title=t.title,
            description=t.description,
            assigned_to_user_id=t.assigned_to_user_id,
            assigned_to=mini(users, t.assigned_to_user_id),
            due_date=t.due_date,
            priority=t.priority,
            status=t.status,
            is_overdue=overdue,
            days_left=rules.days_left(t.due_date, today),
            cancelled_reason=t.cancelled_reason,
            evidence_count=ev.get(str(t.id), 0),
            uploader_ids=uploaders.get(str(t.id), []),
            lock_version=t.lock_version,
            created_at=utc(t.created_at),
            updated_at=utc(t.updated_at),
        ))
    return out


async def build_evidence(db: AsyncSession, rows: Sequence[TaskEvidence]) -> List[EvidenceRead]:
    if not rows:
        return []
    users = await users_map(db, [x for e in rows for x in (e.submitted_by_user_id, e.withdrawn_by_user_id)])
    return [
        EvidenceRead(
            id=e.id,
            task_id=e.task_id,
            organization_id=e.organization_id,
            submitted_by_user_id=e.submitted_by_user_id,
            submitted_by=users[str(e.submitted_by_user_id)],
            file_sha256=e.file_sha256,
            original_filename=e.original_filename,
            file_size_bytes=e.file_size_bytes,
            mime_type=e.mime_type,
            notes=e.notes,
            created_at=utc(e.created_at),
            withdrawn_at=utc(e.withdrawn_at),
            withdrawn_by=mini(users, e.withdrawn_by_user_id),
        )
        for e in rows
    ]


async def build_task_reviews(db: AsyncSession, rows: Sequence[TaskReview]) -> List[TaskReviewRead]:
    if not rows:
        return []
    users = await users_map(db, [r.reviewer_user_id for r in rows])
    return [
        TaskReviewRead(
            id=r.id, task_id=r.task_id, reviewer_user_id=r.reviewer_user_id, reviewer=users[str(r.reviewer_user_id)],
            decision=r.decision, comments=r.comments, evidence_ids=r.evidence_ids, created_at=utc(r.created_at),
        )
        for r in rows
    ]


async def build_item_reviews(db: AsyncSession, rows: Sequence[ComplianceItemReview]) -> List[ItemReviewRead]:
    if not rows:
        return []
    users = await users_map(db, [r.reviewer_user_id for r in rows])
    return [
        ItemReviewRead(
            id=r.id, item_id=r.item_id, reviewer=users[str(r.reviewer_user_id)], decision=r.decision,
            comments=r.comments, created_at=utc(r.created_at),
        )
        for r in rows
    ]


async def item_tasks(db: AsyncSession, item_id) -> List[ComplianceTask]:
    return list((await db.execute(
        select(ComplianceTask).where(ComplianceTask.compliance_item_id == item_id).order_by(ComplianceTask.created_at, ComplianceTask.id)
    )).scalars().all())


async def item_evidence(db: AsyncSession, item_id) -> List[TaskEvidence]:
    return list((await db.execute(
        select(TaskEvidence)
        .join(ComplianceTask, ComplianceTask.id == TaskEvidence.task_id)
        .where(ComplianceTask.compliance_item_id == item_id)
        .order_by(TaskEvidence.created_at, TaskEvidence.id)
    )).scalars().all())
