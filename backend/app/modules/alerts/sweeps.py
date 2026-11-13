"""Checks that turn state derived on read (deadlines, circular changes, review queues) into alert events.

Every check is idempotent: the dedupe key names the real-world state, so running it many times is harmless.
None of them commits except library_changed (which runs right after a change was committed).
"""
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

from sqlalchemy import func, select

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.modules.alerts import emit as alerts_emit
from backend.app.modules.alerts import recipients
from backend.app.modules.alerts.models import AlertEvent
from backend.app.modules.compliance import permissions as perms
from backend.app.modules.compliance import rules
from backend.app.modules.compliance.models import ComplianceItem, ComplianceTask
from backend.app.modules.compliance.service import (
    current_source_change, eff_deadline_sql, signature_for, source_context,
)
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.organizations.models import Organization, OrganizationMember
from backend.app.modules.relationships.models import DocumentRelationship
from backend.app.modules.relationships.status import STATUS_BY_TYPE
from backend.app.modules.sources.models import SourceDiscovery

MAX_ITEM_IDS = 50


def _uniq(seq: Iterable) -> List[str]:
    out: List[str] = []
    for s in seq:
        s = str(s) if s is not None else None
        if s and s not in out:
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# 4.3 A circular behind register items changed
# ---------------------------------------------------------------------------
async def ensure_source_change_events(db, organization_id) -> int:
    items = list((await db.execute(
        select(ComplianceItem).where(
            ComplianceItem.organization_id == organization_id,
            ComplianceItem.status != "EXEMPTED",
            ComplianceItem.source_document_id.is_not(None),
        ).order_by(ComplianceItem.created_at, ComplianceItem.id)
    )).scalars().all())
    if not items:
        return 0
    ctx = await source_context(db, [i.source_document_id for i in items])
    groups: Dict[tuple, List[ComplianceItem]] = {}
    for item in items:
        if current_source_change(item, ctx) is None:
            continue
        sig, *_ = signature_for(item, ctx)
        groups.setdefault((str(item.source_document_id), sig), []).append(item)
    if not groups:
        return 0
    names = await recipients.names(db, organization_id, None)
    staff = await recipients.compliance_staff_ids(db, organization_id)
    leads = await recipients.active_members(db, organization_id, [perms.LEAD])
    emitted = 0
    for (doc_id, sig), group in groups.items():
        first = group[0]
        _sig, in_force_status, doc, withdrawn, by = signature_for(first, ctx)
        kind = rules.change_kind(in_force_status, doc.current_version_id if doc else None, first.source_version_id, withdrawn)
        payload = await alerts_emit.circular_fields(db, doc) if doc is not None else {"document_id": doc_id}
        payload.update({
            "organization_id": names["organization_id"], "organization_name": names["organization_name"],
            "change_kind": kind,
            "item_ids": _uniq(i.id for i in group)[:MAX_ITEM_IDS],
            "register_ids": _uniq(i.register_id for i in group),
            "item_count": len(group),
        })
        if by is not None and kind in ("AMENDED", "REPLACED", "REPEALED"):
            payload.update({"by_document_id": str(by.id), "by_reference_number": by.reference_number, "by_title": by.title})
            types = [t for t, st in STATUS_BY_TYPE.items() if st == kind]
            rel = (await db.execute(
                select(DocumentRelationship).where(
                    DocumentRelationship.source_document_id == by.id,
                    DocumentRelationship.target_document_id == doc.id,
                    DocumentRelationship.verification_status == "VERIFIED",
                    DocumentRelationship.relationship_type.in_(types),
                ).order_by(DocumentRelationship.reviewed_at.desc(), DocumentRelationship.created_at.desc()).limit(1)
            )).scalar_one_or_none()
            if rel is not None and rel.supporting_quote:
                payload["link_quote"] = rel.supporting_quote  # copied exactly as stored
                if rel.source_page_id:
                    page = await db.get(DocumentPage, rel.source_page_id)
                    payload["link_quote_page"] = page.page_number if page else None
        dept_ids = {str(i.department_id) for i in group if i.department_id}
        who = _uniq(staff + [i.assigned_lead_id for i in group]
                    + [m.user_id for m in leads if m.department_id and str(m.department_id) in dept_ids])
        row = await alerts_emit.emit(
            db, kind="REGISTER_SOURCE_CHANGED", dedupe_key=f"SOURCE_CHANGED:{organization_id}:{doc_id}:{sig}",
            organization_id=organization_id, document_id=doc.id if doc is not None else None,
            entity_type="document", entity_id=doc.id if doc is not None else None,
            recipient_user_ids=who, payload=payload,
        )
        emitted += 1 if row is not None else 0
    return emitted


async def library_changed(db, doc_ids: Iterable) -> None:
    """Right after a change to the library was committed: check the banks that use these circulars.
    Never raises."""
    try:
        ids = [d for d in {str(d): d for d in doc_ids if d is not None}.values()]
        if not ids:
            return
        org_ids = [r[0] for r in (await db.execute(
            select(ComplianceItem.organization_id).where(ComplianceItem.source_document_id.in_(ids)).distinct()
        )).all()]
        for org_id in org_ids:
            await ensure_source_change_events(db, org_id)
        await db.commit()
    except Exception as exc:
        logger.warning("Alert not recorded: %s", type(exc).__name__)
        try:
            await db.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 4.7 Deadlines
# ---------------------------------------------------------------------------
def _threshold(days_left: int) -> Optional[int]:
    for t in settings.due_soon_days:
        if days_left <= t:
            return t
    return None


async def ensure_deadline_events(db, organization_id, today: Optional[date] = None) -> int:
    today = today or rules.today_dhaka()
    horizon = today + timedelta(days=max(settings.due_soon_days))
    names = await recipients.names(db, organization_id, None)
    heads = await recipients.head_ids(db, organization_id)
    base = {"organization_id": names["organization_id"], "organization_name": names["organization_name"]}
    emitted = 0

    items = list((await db.execute(
        select(ComplianceItem).where(
            ComplianceItem.organization_id == organization_id,
            ComplianceItem.status.in_(rules.ITEM_OVERDUE_STATUSES),
            eff_deadline_sql().is_not(None),
            eff_deadline_sql() <= horizon,
        )
    )).scalars().all())
    for item in items:
        deadline = rules.effective_deadline(item.internal_deadline, item.regulatory_deadline)
        payload = dict(base, item_id=str(item.id), item_title=item.obligation_title or item.source_title or "Item",
                       register_id=str(item.register_id), deadline=deadline.isoformat())
        dept_head = await recipients.department_head(db, organization_id, item.department_id)
        if deadline < today:
            who = _uniq([item.assigned_lead_id, dept_head] + heads)
            row = await alerts_emit.emit(
                db, kind="ITEM_OVERDUE", dedupe_key=f"ITEM_OVERDUE:{item.id}:{deadline}",
                organization_id=organization_id, entity_type="compliance_item", entity_id=item.id,
                recipient_user_ids=who, payload=payload,
            )
        else:
            days_left = (deadline - today).days
            t = _threshold(days_left)
            if t is None:
                continue
            who = _uniq([item.assigned_lead_id] if item.assigned_lead_id else ([dept_head] if dept_head else heads))
            row = await alerts_emit.emit(
                db, kind="ITEM_DUE_SOON", dedupe_key=f"ITEM_DUE_SOON:{item.id}:{deadline}:{t}",
                organization_id=organization_id, entity_type="compliance_item", entity_id=item.id,
                recipient_user_ids=who, payload=dict(payload, days_left=days_left),
            )
        emitted += 1 if row is not None else 0

    tasks = (await db.execute(
        select(ComplianceTask, ComplianceItem)
        .join(ComplianceItem, ComplianceItem.id == ComplianceTask.compliance_item_id)
        .where(
            ComplianceTask.organization_id == organization_id,
            ComplianceTask.status.in_(rules.TASK_OVERDUE_STATUSES),
            ComplianceTask.due_date <= horizon,
            ComplianceItem.status.notin_(["COMPLIANT", "EXEMPTED"]),
        )
    )).all()
    for task, item in tasks:
        payload = dict(base, task_id=str(task.id), task_title=task.title, item_id=str(item.id),
                       item_title=item.obligation_title or item.source_title or "Item", due_date=task.due_date.isoformat())
        who = _uniq([task.assigned_to_user_id or item.assigned_lead_id])
        if task.due_date < today:
            row = await alerts_emit.emit(
                db, kind="TASK_OVERDUE", dedupe_key=f"TASK_OVERDUE:{task.id}:{task.due_date}",
                organization_id=organization_id, entity_type="compliance_task", entity_id=task.id,
                recipient_user_ids=who, payload=payload,
            )
        else:
            days_left = (task.due_date - today).days
            t = _threshold(days_left)
            if t is None:
                continue
            row = await alerts_emit.emit(
                db, kind="TASK_DUE_SOON", dedupe_key=f"TASK_DUE_SOON:{task.id}:{task.due_date}:{t}",
                organization_id=organization_id, entity_type="compliance_task", entity_id=task.id,
                recipient_user_ids=who, payload=dict(payload, days_left=days_left),
            )
        emitted += 1 if row is not None else 0
    return emitted


# ---------------------------------------------------------------------------
# 4.8 Admin review queues
# ---------------------------------------------------------------------------
async def queue_counts(db) -> Dict[str, int]:
    discoveries = (await db.execute(
        select(func.count(SourceDiscovery.id)).where(SourceDiscovery.status == "VALIDATED")
    )).scalar_one()
    analyses = (await db.execute(
        select(func.count(Document.id)).where(Document.owner_user_id.is_(None), Document.publication_status == "AWAITING_REVIEW")
    )).scalar_one()
    links = (await db.execute(
        select(func.count(DocumentRelationship.id))
        .join(Document, Document.id == DocumentRelationship.source_document_id)
        .where(DocumentRelationship.verification_status == "PENDING_REVIEW", Document.owner_user_id.is_(None))
    )).scalar_one()
    pages = (await db.execute(
        select(func.count(DocumentPage.id))
        .join(DocumentVersion, DocumentVersion.id == DocumentPage.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(DocumentPage.quality_status == "NEEDS_HUMAN_REVIEW", Document.owner_user_id.is_(None))
    )).scalar_one()
    return {"discoveries": int(discoveries), "analyses": int(analyses), "links": int(links), "pages": int(pages)}


async def ensure_admin_queue_events(db, today: Optional[date] = None) -> int:
    today = today or rules.today_dhaka()
    emitted = 0
    for queue, count in (await queue_counts(db)).items():
        if count <= 0:
            continue
        row = await alerts_emit.emit(
            db, kind="ADMIN_QUEUE", dedupe_key=f"ADMIN_QUEUE:{queue}:{today}",
            entity_type="admin_queue", payload={"queue": queue, "count": count},
        )
        emitted += 1 if row is not None else 0
    return emitted


# ---------------------------------------------------------------------------
# 4.2 Safety net: a shared circular was published by a path that did not announce it
# ---------------------------------------------------------------------------
async def sweep_published(db, now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=settings.ALERTS_PUBLISH_SWEEP_HOURS)
    docs = list((await db.execute(
        select(Document).where(
            Document.owner_user_id.is_(None),
            Document.publication_status.like("PUBLISHED%"),
            Document.updated_at >= cutoff,
        )
    )).scalars().all())
    if not docs:
        return 0
    keys = {f"CIRCULAR_PUBLISHED:{d.id}": d for d in docs}
    have = {r[0] for r in (await db.execute(select(AlertEvent.dedupe_key).where(AlertEvent.dedupe_key.in_(list(keys))))).all()}
    emitted = 0
    for key, doc in keys.items():
        if key in have:
            continue
        if await alerts_emit.circular_published(db, doc) is not None:
            emitted += 1
    return emitted
