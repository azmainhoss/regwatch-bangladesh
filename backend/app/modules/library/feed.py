"""The home screen: circulars filtered by period, department, category, saved list and search words,
plus the numbers on the four boxes at the top (Today, This week, This month, Read later)."""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.database.session import get_async_db
from backend.app.modules.documents.access import get_document_reader, visible_documents_condition
from backend.app.modules.documents.models import Document
from backend.app.modules.documents.schemas import DocumentRead
from backend.app.modules.documents.search import _like, document_matches_condition, meta_matches_condition, query_terms
from backend.app.modules.documents.synthetic import synthetic_sql_condition
from backend.app.modules.identity.models import User
from backend.app.modules.institutions.models import InstitutionDepartment
from backend.app.modules.library.models import UserList, UserListItem
from backend.app.modules.topics.models import DocumentTopic
from backend.app.modules.topics.taxonomy import TOPICS

router = APIRouter(prefix="/feed", tags=["Home screen"])


class FeedPage(BaseModel):
    total: int
    items: List[DocumentRead]


class Choice(BaseModel):
    code: str
    label: str
    count: int


class FeedCounts(BaseModel):
    today: int
    week: int
    month: int
    read_later: int
    favourites: int
    departments: List[Choice]
    topics: List[Choice]


def today_local() -> date:
    return datetime.now(ZoneInfo(settings.MONITOR_TIMEZONE)).date()


def period_start(period: Optional[str], today: Optional[date] = None) -> Optional[date]:
    """today = this date; week = since Sunday (the Bangladesh working week starts on Sunday); month = since the 1st."""
    today = today or today_local()
    p = (period or "").lower()
    if p == "today":
        return today
    if p == "week":
        return today - timedelta(days=(today.weekday() + 1) % 7)
    if p == "month":
        return today.replace(day=1)
    return None


def _dept_condition(code: str):
    return or_(
        Document.department_id.in_(select(InstitutionDepartment.id).where(func.upper(InstitutionDepartment.code) == code.upper())),
        func.coalesce(Document.reference_number, "").ilike(_like(code + " "), escape="\\"),
    )


async def _kind_list_id(db: AsyncSession, user: Optional[User], kind: str) -> Optional[UUID]:
    if not user:
        return None
    return (await db.execute(select(UserList.id).where(UserList.user_id == user.id, UserList.kind == kind))).scalars().first()


def _base(user: Optional[User]):
    return [visible_documents_condition(user), ~synthetic_sql_condition()]


@router.get("", response_model=FeedPage)
async def feed(
    period: Optional[str] = Query(None, description="today, week or month"),
    department: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    list_id: Optional[UUID] = Query(None, description="One of your saved lists"),
    saved: Optional[str] = Query(None, description="READ_LATER or FAVOURITES"),
    q: Optional[str] = Query(None, max_length=200),
    analysed: Optional[bool] = Query(None, description="Only circulars that have a checked summary"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: Optional[User] = Depends(get_document_reader),
    db: AsyncSession = Depends(get_async_db),
):
    conditions = _base(user)
    start = period_start(period)
    if start:
        conditions.append(Document.publication_date >= start)
    if department and department.upper() != "ALL":
        conditions.append(_dept_condition(department))
    if topic and topic.upper() != "ALL":
        conditions.append(exists(select(1).where(DocumentTopic.document_id == Document.id, DocumentTopic.topic == topic.upper())))
    if saved and not list_id:
        list_id = await _kind_list_id(db, user, saved.upper())
        if not list_id:
            return FeedPage(total=0, items=[])
    if list_id:
        if not user:
            return FeedPage(total=0, items=[])
        conditions.append(exists(
            select(1).select_from(UserListItem).join(UserList, UserList.id == UserListItem.list_id)
            .where(UserListItem.document_id == Document.id, UserList.id == list_id, UserList.user_id == user.id)
        ))
    if analysed:
        conditions.append(Document.publication_status.like("PUBLISHED%"))
    terms = query_terms(q or "")
    order = [Document.publication_date.desc(), Document.created_at.desc(), Document.id]
    if terms and sum(len(t) for t in terms) >= 2:
        conditions.append(document_matches_condition(terms))
        # Circulars whose number or title holds every word come first ("BRPD 39" finds BRPD ... No. 39 at the top).
        order = [case((meta_matches_condition(terms), 0), else_=1)] + order

    total = (await db.execute(select(func.count()).select_from(Document).where(*conditions))).scalar_one()
    docs = (await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(*conditions)
        .order_by(*order)
        .limit(limit).offset(offset)
    )).scalars().all()
    from backend.app.modules.documents.router import _with_in_force
    return FeedPage(total=total, items=await _with_in_force(db, docs, user))


@router.get("/counts", response_model=FeedCounts)
async def feed_counts(user: Optional[User] = Depends(get_document_reader), db: AsyncSession = Depends(get_async_db)):
    base = _base(user)
    today = today_local()

    async def count_since(d: date) -> int:
        return (await db.execute(select(func.count()).select_from(Document).where(*base, Document.publication_date >= d))).scalar_one()

    async def count_saved(kind: str) -> int:
        lid = await _kind_list_id(db, user, kind)
        if not lid:
            return 0
        return (await db.execute(
            select(func.count()).select_from(UserListItem).join(Document, Document.id == UserListItem.document_id)
            .where(UserListItem.list_id == lid, *base)
        )).scalar_one()

    dept_rows = (await db.execute(
        select(InstitutionDepartment.code, func.count(Document.id))
        .join(Document, Document.department_id == InstitutionDepartment.id)
        .where(*base)
        .group_by(InstitutionDepartment.code)
        .order_by(func.count(Document.id).desc())
    )).all()
    topic_rows = dict((await db.execute(
        select(DocumentTopic.topic, func.count(DocumentTopic.id))
        .join(Document, Document.id == DocumentTopic.document_id)
        .where(*base)
        .group_by(DocumentTopic.topic)
    )).all())
    return FeedCounts(
        today=await count_since(today),
        week=await count_since(period_start("week", today)),
        month=await count_since(today.replace(day=1)),
        read_later=await count_saved("READ_LATER"),
        favourites=await count_saved("FAVOURITES"),
        # Department codes as the circulars carry them; tiny one-off codes (typos in old circulars) are left out.
        departments=[Choice(code=c, label=c, count=n) for c, n in dept_rows if n >= 5 and c and " " not in c and "." not in c],
        topics=[Choice(code=t.code, label=t.label, count=int(topic_rows.get(t.code, 0))) for t in TOPICS if topic_rows.get(t.code)],
    )


@router.get("/topics", response_model=List[Choice])
async def topic_names():
    """Every subject category with its label (count 0: the list is fixed)."""
    return [Choice(code=t.code, label=t.label, count=0) for t in TOPICS]
