"""Plans: what each costs and allows, my plan and today's usage, upgrade requests, and the admin's confirm step.

Payment is not taken online yet: an upgrade is a request the platform team confirms once paid.
"""
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.database.session import get_async_db
from backend.app.modules.identity.deps import get_current_user
from backend.app.modules.identity.models import User
from backend.app.modules.organizations.models import OrganizationMember
from backend.app.modules.plans.models import DailyUsage, Subscription
from backend.app.modules.plans.plans import ENTERPRISE, ENTERPRISE_MIN_SEATS, FREE, PLANS, PRO, allows, best

router = APIRouter(prefix="/plans", tags=["Plans"])

# The older test suites act as people on the Free plan and ask many questions; the plan limits are
# switched on in tests only by the plan tests themselves (they set this to True).
ENFORCE_IN_TESTS = False


def _enforced() -> bool:
    import os
    return ENFORCE_IN_TESTS or not os.environ.get("PYTEST_CURRENT_TEST")


class PlanRead(BaseModel):
    code: str
    name: str
    price_bdt_month: int
    per: str
    min_seats: int
    questions_per_day: int
    features: List[str]


class MyPlan(BaseModel):
    plan: str
    name: str
    via_organization: bool
    questions_today: int
    questions_per_day: int
    allows: List[str]
    pending_request: Optional[str] = None


class UpgradeRequest(BaseModel):
    plan: str = Field(..., pattern="^(PRO|ENTERPRISE)$")
    seats: int = Field(1, ge=1, le=100000)
    organization_name: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=40)
    note: Optional[str] = Field(None, max_length=2000)


class RequestRead(BaseModel):
    id: UUID
    plan: str
    seats: int
    status: str
    organization_name: Optional[str] = None
    contact_phone: Optional[str] = None
    note: Optional[str] = None
    requested_by: Optional[str] = None
    created_at: datetime


def today() -> date:
    return datetime.now(ZoneInfo(settings.MONITOR_TIMEZONE)).date()


async def effective_plan(db: AsyncSession, user: Optional[User]):
    """(plan code, came from an organization?)."""
    if not user:
        return FREE, False
    if user.is_superuser:
        return ENTERPRISE, False
    own = (await db.execute(
        select(Subscription.plan).where(Subscription.user_id == user.id, Subscription.status == "ACTIVE")
    )).scalars().all()
    org_ids = (await db.execute(
        select(OrganizationMember.organization_id).where(OrganizationMember.user_id == user.id, OrganizationMember.status == "ACTIVE")
    )).scalars().all()
    org = []
    if org_ids:
        org = (await db.execute(
            select(Subscription.plan).where(Subscription.organization_id.in_(org_ids), Subscription.status == "ACTIVE")
        )).scalars().all()
    mine = best(*own) if own else FREE
    theirs = best(*org) if org else FREE
    plan = best(mine, theirs)
    return plan, plan != mine


async def questions_today(db: AsyncSession, user: User) -> int:
    row = (await db.execute(
        select(DailyUsage.count).where(DailyUsage.user_id == user.id, DailyUsage.day == today(), DailyUsage.kind == "QUESTION")
    )).scalar_one_or_none()
    return int(row or 0)


async def use_question(db: AsyncSession, user: Optional[User]) -> None:
    """Counts one question; refuses it (HTTP 402) once a Free plan's daily questions are used up."""
    if not user:
        return
    plan, _ = await effective_plan(db, user)
    limit = PLANS[plan].questions_per_day
    row = (await db.execute(
        select(DailyUsage).where(DailyUsage.user_id == user.id, DailyUsage.day == today(), DailyUsage.kind == "QUESTION")
    )).scalar_one_or_none()
    if limit and row and row.count >= limit and _enforced():
        raise HTTPException(
            status_code=402,
            detail=f"You have used today's {limit} free questions. They come back tomorrow, or move to Pro for unlimited questions.",
        )
    if row:
        row.count += 1
    else:
        db.add(DailyUsage(user_id=user.id, day=today(), kind="QUESTION", count=1))
    await db.commit()


async def require(db: AsyncSession, user: User, feature: str, what: str) -> None:
    if not _enforced():
        return
    plan, _ = await effective_plan(db, user)
    if not allows(plan, feature):
        need = "Enterprise" if feature in ("assign", "workspace") else "Pro"
        raise HTTPException(status_code=402, detail=f"{what} is part of the {need} plan.")


@router.get("", response_model=List[PlanRead], dependencies=[Depends(get_current_user)])
async def list_plans():
    return [PlanRead(code=p.code, name=p.name, price_bdt_month=p.price_bdt_month, per=p.per, min_seats=p.min_seats,
                     questions_per_day=p.questions_per_day, features=p.features) for p in PLANS.values()]


@router.get("/me", response_model=MyPlan)
async def my_plan(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    plan, via_org = await effective_plan(db, user)
    pending = (await db.execute(
        select(Subscription.plan).where(Subscription.requested_by_user_id == user.id, Subscription.status == "REQUESTED")
        .order_by(Subscription.created_at.desc())
    )).scalars().first()
    p = PLANS[plan]
    return MyPlan(plan=plan, name=p.name, via_organization=via_org, questions_today=await questions_today(db, user),
                  questions_per_day=p.questions_per_day, allows=p.allows, pending_request=pending)


@router.post("/request", response_model=MyPlan, status_code=201)
async def request_upgrade(body: UpgradeRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    if body.plan == ENTERPRISE:
        if body.seats < ENTERPRISE_MIN_SEATS:
            raise HTTPException(status_code=422, detail=f"Enterprise starts at {ENTERPRISE_MIN_SEATS} seats.")
        if not (body.organization_name or "").strip():
            raise HTTPException(status_code=422, detail="Give your bank's or company's name.")
    org_id = None
    if body.plan == ENTERPRISE:
        org_id = (await db.execute(
            select(OrganizationMember.organization_id).where(OrganizationMember.user_id == user.id, OrganizationMember.status == "ACTIVE")
        )).scalars().first()
    db.add(Subscription(
        user_id=None if body.plan == ENTERPRISE and org_id else user.id,
        organization_id=org_id if body.plan == ENTERPRISE else None,
        plan=body.plan, seats=body.seats if body.plan == ENTERPRISE else 1, status="REQUESTED",
        requested_by_user_id=user.id, organization_name=(body.organization_name or "").strip() or None,
        contact_phone=(body.contact_phone or "").strip() or None, note=(body.note or "").strip() or None,
    ))
    await db.commit()
    return await my_plan(user, db)


def _admin(user: User) -> None:
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Administrators only.")


@router.get("/requests", response_model=List[RequestRead])
async def list_requests(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    _admin(user)
    rows = (await db.execute(select(Subscription).order_by(Subscription.created_at.desc()).limit(200))).scalars().all()
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_({r.requested_by_user_id for r in rows if r.requested_by_user_id})))).scalars().all()} if rows else {}
    return [RequestRead(id=r.id, plan=r.plan, seats=r.seats, status=r.status, organization_name=r.organization_name,
                        contact_phone=r.contact_phone, note=r.note,
                        requested_by=(users[r.requested_by_user_id].email if r.requested_by_user_id in users else None),
                        created_at=r.created_at) for r in rows]


@router.post("/requests/{request_id}/{decision}", response_model=RequestRead)
async def decide_request(request_id: UUID, decision: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    """decision: activate (payment received) or end."""
    _admin(user)
    if decision not in ("activate", "end"):
        raise HTTPException(status_code=404, detail="Unknown decision.")
    sub = await db.get(Subscription, request_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Not found.")
    sub.status = "ACTIVE" if decision == "activate" else "ENDED"
    await db.commit()
    await db.refresh(sub)
    return next(r for r in await list_requests(user, db) if r.id == sub.id)
