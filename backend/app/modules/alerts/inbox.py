"""Reading a person's inbox. One visibility rule is used for every list, count, read and digest query."""
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.alerts.kinds import GROUPS, INBOX_GROUP_ALIASES
from backend.app.modules.alerts.models import AlertNotification
from backend.app.modules.alerts.schemas import AlertRead, DocumentMini, QuoteRead
from backend.app.modules.documents.models import Document
from backend.app.modules.organizations.models import Organization, OrganizationMember

AN = AlertNotification


def utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def visible_condition(user_id, is_superuser: bool, in_app_only: bool = True):
    """A notification is visible only to its owner, only while they are an ACTIVE member of that bank
    (and the bank is active), and review-queue alerts only while they are still platform staff."""
    member_ok = exists(
        select(OrganizationMember.id)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .where(
            OrganizationMember.organization_id == AN.organization_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.status == "ACTIVE",
            Organization.is_active.is_(True),
        )
    )
    conds = [AN.user_id == user_id, or_(AN.organization_id.is_(None), member_ok)]
    if in_app_only:
        conds.append(AN.in_app.is_(True))
    if not is_superuser:
        conds.append(AN.kind != "ADMIN_QUEUE")
    return and_(*conds)


def group_filter(group: Optional[str]):
    if not group:
        return None
    groups = INBOX_GROUP_ALIASES.get(group) or ([group] if group in GROUPS else None)
    if groups is None:
        return None
    return AN.group.in_(groups)


async def unread_count(db: AsyncSession, user) -> int:
    return int((await db.execute(
        select(func.count(AN.id)).where(visible_condition(user.id, user.is_superuser), AN.read_at.is_(None))
    )).scalar_one())


async def latest(db: AsyncSession, user):
    row = (await db.execute(
        select(AN.id, AN.created_at).where(visible_condition(user.id, user.is_superuser))
        .order_by(AN.created_at.desc(), AN.id.desc()).limit(1)
    )).first()
    return (str(row[0]), utc(row[1])) if row else (None, None)


async def get_visible(db: AsyncSession, user, alert_id) -> Optional[AlertNotification]:
    try:
        return (await db.execute(
            select(AN).where(AN.id == alert_id, visible_condition(user.id, user.is_superuser))
        )).scalar_one_or_none()
    except (ValueError, TypeError):
        return None


async def to_read(db: AsyncSession, rows: Iterable[AlertNotification]) -> List[AlertRead]:
    rows = list(rows)
    org_ids = {r.organization_id for r in rows if r.organization_id}
    doc_ids = {x for r in rows for x in (r.document_id, r.quote_document_id) if x}
    orgs: Dict[str, str] = {}
    docs: Dict[str, Document] = {}
    if org_ids:
        orgs = {str(o.id): o.name for o in (await db.execute(select(Organization).where(Organization.id.in_(org_ids)))).scalars()}
    if doc_ids:
        docs = {str(d.id): d for d in (await db.execute(select(Document).where(Document.id.in_(doc_ids)))).scalars()}
    out: List[AlertRead] = []
    for r in rows:
        d = docs.get(str(r.document_id)) if r.document_id else None
        qd = docs.get(str(r.quote_document_id)) if r.quote_document_id else None
        quote = None
        if r.quote_text:
            quote = QuoteRead(
                text=r.quote_text, page_number=r.quote_page_number,
                document_id=r.quote_document_id, document_reference=qd.reference_number if qd else None,
            )
        out.append(AlertRead(
            id=r.id, kind=r.kind, group=r.group, severity=r.severity, organization_id=r.organization_id,
            organization_name=orgs.get(str(r.organization_id)) if r.organization_id else None,
            title=r.title, body=r.body, detail=r.detail, link=r.link,
            document=DocumentMini(id=d.id, reference_number=d.reference_number, title=d.title) if d else None,
            quote=quote, read_at=utc(r.read_at), created_at=utc(r.created_at),
        ))
    return out
