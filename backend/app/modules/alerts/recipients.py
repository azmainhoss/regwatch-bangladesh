"""Who an alert goes to. Role rules come from compliance/permissions.py so they stay in one place."""
from typing import Dict, Iterable, List, Optional, Set
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.compliance import permissions as perms
from backend.app.modules.compliance.models import TaskEvidence
from backend.app.modules.compliance.service import item_evidence
from backend.app.modules.identity.models import User
from backend.app.modules.organizations.models import Department, Organization, OrganizationMember


async def active_members(db: AsyncSession, org_id, roles: Optional[Iterable[str]] = None) -> List[OrganizationMember]:
    q = (
        select(OrganizationMember)
        .join(User, User.id == OrganizationMember.user_id)
        .where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.status == "ACTIVE",
            User.is_active.is_(True),
        )
    )
    if roles:
        q = q.where(OrganizationMember.role.in_(list(roles)))
    return list((await db.execute(q.order_by(OrganizationMember.created_at, OrganizationMember.id))).scalars().all())


async def active_member_ids(db: AsyncSession, org_id, user_ids: Iterable) -> Set[str]:
    """Of these people, the ones who are ACTIVE members of this (active) organization right now."""
    ids = [str(u) for u in user_ids if u is not None]
    if not ids:
        return set()
    rows = (await db.execute(
        select(OrganizationMember.user_id)
        .join(User, User.id == OrganizationMember.user_id)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id.in_(ids),
            OrganizationMember.status == "ACTIVE",
            User.is_active.is_(True),
            Organization.is_active.is_(True),
        )
    )).all()
    return {str(r[0]) for r in rows}


async def active_superuser_ids(db: AsyncSession) -> List[str]:
    rows = (await db.execute(
        select(User.id).where(User.is_superuser.is_(True), User.is_active.is_(True)).order_by(User.created_at)
    )).all()
    return [str(r[0]) for r in rows]


async def names(db: AsyncSession, org_id, actor_user_id) -> Dict[str, Optional[str]]:
    org = await db.get(Organization, org_id) if org_id else None
    actor = await db.get(User, actor_user_id) if actor_user_id else None
    return {
        "organization_id": str(org_id) if org_id else None,
        "organization_name": org.name if org else None,
        "actor_name": actor.full_name if actor else None,
    }


async def reviewers_for_task(db: AsyncSession, org_id, task, item) -> List[str]:
    """People who can decide on this task's evidence: heads, reviewers and the item's department lead.
    Bank admins only when none of those can."""
    evidence = list((await db.execute(
        select(TaskEvidence).where(TaskEvidence.task_id == task.id)
    )).scalars().all())
    members = await active_members(db, org_id)

    def ok(m) -> bool:
        return perms.can_review_task(m, item) and perms.task_review_block(m.user_id, task, evidence) is None

    first = [m for m in members if m.role in (perms.HEAD, perms.REVIEWER, perms.LEAD) and ok(m)]
    if not first:
        first = [m for m in members if m.role == perms.ADMIN and ok(m)]
    return [str(m.user_id) for m in first]


async def signers_for_item(db: AsyncSession, org_id, item) -> List[str]:
    evidence = await item_evidence(db, item.id)
    members = await active_members(db, org_id)

    def ok(m) -> bool:
        return perms.signoff_block(m.user_id, item, evidence) is None

    first = [m for m in members if m.role in (perms.HEAD, perms.REVIEWER) and ok(m)]
    if not first:
        first = [m for m in members if m.role == perms.ADMIN and ok(m)]
    return [str(m.user_id) for m in first]


async def department_head(db: AsyncSession, org_id, department_id) -> Optional[str]:
    if not department_id:
        return None
    dept = await db.get(Department, department_id)
    if not dept or not dept.head_user_id:
        return None
    ok = await active_member_ids(db, org_id, [dept.head_user_id])
    return str(dept.head_user_id) if ok else None


async def head_ids(db: AsyncSession, org_id) -> List[str]:
    return [str(m.user_id) for m in await active_members(db, org_id, [perms.HEAD])]


async def compliance_staff_ids(db: AsyncSession, org_id) -> List[str]:
    return [str(m.user_id) for m in await active_members(db, org_id, [perms.ADMIN, perms.HEAD, perms.OFFICER])]
