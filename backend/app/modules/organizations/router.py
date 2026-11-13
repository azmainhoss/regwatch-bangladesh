from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.session import get_async_db
from backend.app.modules.audit import service as audit
from backend.app.modules.compliance import permissions as perms
from backend.app.modules.compliance.models import ComplianceItem
from backend.app.modules.compliance.service import utc
from backend.app.modules.identity.deps import get_current_user
from backend.app.modules.identity.models import User
from backend.app.modules.organizations.deps import get_org_membership, get_workspace_membership
from backend.app.modules.organizations.models import Department, Organization, OrganizationMember
from backend.app.modules.organizations.schemas import (
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    MeInOrg,
    MemberByEmail,
    MemberRead,
    MemberUpdate,
    MyOrg,
    OrganizationCreate,
    OrganizationMemberCreate,
    OrganizationMemberRead,
    OrganizationRead,
    UserMini,
)

router = APIRouter(prefix="/organizations", tags=["Organizations & Tenant Management"])

MEMBER_FIELDS = ("role", "department_id", "status")


def _member_read(m: OrganizationMember, user: User) -> MemberRead:
    return MemberRead(
        id=m.id,
        organization_id=m.organization_id,
        user=UserMini(id=user.id, full_name=user.full_name, email=user.email),
        role=m.role,
        department_id=m.department_id,
        status=m.status,
        created_at=utc(m.created_at),
    )


async def _require_department(db: AsyncSession, organization_id: UUID, department_id) -> None:
    if department_id is None:
        return
    dept = await db.get(Department, department_id)
    if not dept or dept.organization_id != organization_id:
        raise HTTPException(status_code=400, detail="Department does not belong to this organization.")


async def _require_member_user(db: AsyncSession, organization_id: UUID, user_id) -> None:
    if user_id is None:
        return
    found = (await db.execute(
        select(OrganizationMember.id).where(
            OrganizationMember.organization_id == organization_id, OrganizationMember.user_id == user_id
        )
    )).first()
    if not found:
        raise HTTPException(status_code=400, detail="That person is not a member of this organization.")


async def _departments_read(db: AsyncSession, organization_id: UUID, depts: List[Department]) -> List[DepartmentRead]:
    if not depts:
        return []
    ids = [d.id for d in depts]
    member_rows = (await db.execute(
        select(OrganizationMember.department_id, func.count(OrganizationMember.id))
        .where(OrganizationMember.organization_id == organization_id, OrganizationMember.department_id.in_(ids),
               OrganizationMember.status == "ACTIVE")
        .group_by(OrganizationMember.department_id)
    )).all()
    item_rows = (await db.execute(
        select(ComplianceItem.department_id, func.count(ComplianceItem.id))
        .where(ComplianceItem.organization_id == organization_id, ComplianceItem.department_id.in_(ids),
               ComplianceItem.status.notin_(("COMPLIANT", "EXEMPTED")))
        .group_by(ComplianceItem.department_id)
    )).all()
    members = {str(k): v for k, v in member_rows}
    items = {str(k): v for k, v in item_rows}
    head_ids = [d.head_user_id for d in depts if d.head_user_id]
    heads = {}
    if head_ids:
        heads = {str(u.id): u for u in (await db.execute(select(User).where(User.id.in_(head_ids)))).scalars().all()}
    out = []
    for d in depts:
        head = heads.get(str(d.head_user_id)) if d.head_user_id else None
        out.append(DepartmentRead(
            id=d.id, organization_id=d.organization_id, name=d.name, head_user_id=d.head_user_id,
            created_at=utc(d.created_at),
            head=UserMini(id=head.id, full_name=head.full_name, email=head.email) if head else None,
            member_count=members.get(str(d.id), 0),
            open_item_count=items.get(str(d.id), 0),
        ))
    return out


async def _active_admin_count(db: AsyncSession, organization_id: UUID) -> int:
    return (await db.execute(
        select(func.count(OrganizationMember.id)).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.role == "ORG_ADMIN",
            OrganizationMember.status == "ACTIVE",
        )
    )).scalar_one()


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Creates an organization and automatically assigns the creator as ORG_ADMIN.
    """
    org = Organization(
        name=payload.name,
        entity_type=payload.entity_type,
        registration_number=payload.registration_number,
        license_number=payload.license_number,
        is_active=payload.is_active
    )
    db.add(org)
    await db.flush()

    member = OrganizationMember(
        organization_id=org.id,
        user_id=current_user.id,
        role="ORG_ADMIN",
        status="ACTIVE"
    )
    db.add(member)
    await db.commit()
    await db.refresh(org)
    return org


@router.get("", response_model=List[OrganizationRead])
async def list_user_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Lists organizations the authenticated user belongs to."""
    if current_user.is_superuser:
        query = select(Organization).where(Organization.is_active == True).order_by(Organization.name)
        result = await db.execute(query)
        return result.scalars().all()

    query = (
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(
            OrganizationMember.user_id == current_user.id,
            OrganizationMember.status == "ACTIVE",
            Organization.is_active == True
        )
        .order_by(Organization.name)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/mine", response_model=List[MyOrg])
async def my_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """The workspaces the signed-in user is an active member of, with their role. No platform-staff listing."""
    rows = (await db.execute(
        select(Organization, OrganizationMember)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(
            OrganizationMember.user_id == current_user.id,
            OrganizationMember.status == "ACTIVE",
            Organization.is_active == True
        )
        .order_by(Organization.name)
    )).all()
    return [
        MyOrg(id=o.id, name=o.name, entity_type=o.entity_type, role=m.role, department_id=m.department_id)
        for o, m in rows
    ]


@router.get("/{organization_id}", response_model=OrganizationRead)
async def get_organization(
    organization_id: UUID,
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_async_db)
):
    """Tenant-scoped access: Retrieves organization details."""
    org = await db.get(Organization, organization_id)
    return org


@router.get("/{organization_id}/me", response_model=MeInOrg)
async def get_me_in_org(
    organization_id: UUID,
    membership: OrganizationMember = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
):
    return MeInOrg(membership=_member_read(membership, current_user), permissions=perms.org_permissions(membership))


@router.post("/{organization_id}/members", response_model=OrganizationMemberRead, status_code=status.HTTP_201_CREATED)
async def add_organization_member(
    organization_id: UUID,
    payload: OrganizationMemberCreate,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    """Allows ORG_ADMIN to enroll a user into their organization."""
    if not perms.can_manage_members(membership):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization administrators can add members."
        )

    # Only an ORG_ADMIN may hand out ORG_ADMIN.
    if payload.role == "ORG_ADMIN" and membership.role != "ORG_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization administrators can grant the ORG_ADMIN role."
        )

    await _require_department(db, organization_id, payload.department_id)

    target_user = await db.get(User, payload.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

    existing = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == payload.user_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already a member of this organization.")

    new_member = OrganizationMember(
        organization_id=organization_id,
        user_id=payload.user_id,
        department_id=payload.department_id,
        role=payload.role,
        status=payload.status
    )
    db.add(new_member)
    await db.flush()
    audit.record(
        db, organization_id=organization_id, actor_user_id=membership.user_id, action="MEMBER_ADDED",
        entity_type="member", entity_id=new_member.id,
        after={"user_id": str(payload.user_id), "role": payload.role, "department_id": audit._safe(payload.department_id)},
        request=request,
    )
    await db.commit()
    await db.refresh(new_member)
    return new_member


@router.get("/{organization_id}/members", response_model=List[MemberRead])
async def list_organization_members(
    organization_id: UUID,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    """Tenant-scoped member listing, with names and emails."""
    rows = (await db.execute(
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == organization_id)
        .order_by(OrganizationMember.created_at, OrganizationMember.id)
    )).all()
    return [_member_read(m, u) for m, u in rows]


@router.post("/{organization_id}/members/by-email", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
async def add_member_by_email(
    organization_id: UUID,
    payload: MemberByEmail,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    if not perms.can_manage_members(membership):
        raise HTTPException(status_code=403, detail="Insufficient permissions: only admins and compliance heads can add members.")
    if payload.role == "ORG_ADMIN" and membership.role != "ORG_ADMIN":
        raise HTTPException(status_code=403, detail="Only organization administrators can grant the ORG_ADMIN role.")
    await _require_department(db, organization_id, payload.department_id)
    email = payload.email.strip().lower()
    user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="No RegWatch account uses that email. Ask them to sign up first.")
    existing = (await db.execute(
        select(OrganizationMember.id).where(
            OrganizationMember.organization_id == organization_id, OrganizationMember.user_id == user.id
        )
    )).first()
    if existing:
        raise HTTPException(status_code=400, detail="That person is already a member of this workspace.")
    member = OrganizationMember(
        organization_id=organization_id, user_id=user.id, department_id=payload.department_id,
        role=payload.role, status="ACTIVE",
    )
    db.add(member)
    await db.flush()
    audit.record(
        db, organization_id=organization_id, actor_user_id=membership.user_id, action="MEMBER_ADDED",
        entity_type="member", entity_id=member.id,
        after={"user_id": str(user.id), "email": user.email, "role": payload.role,
               "department_id": audit._safe(payload.department_id)},
        request=request,
    )
    await db.commit()
    await db.refresh(member)
    return _member_read(member, user)


@router.patch("/{organization_id}/members/{member_id}", response_model=MemberRead)
async def update_member(
    organization_id: UUID,
    member_id: UUID,
    payload: MemberUpdate,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    if not perms.can_manage_members(membership):
        raise HTTPException(status_code=403, detail="Insufficient permissions: only admins and compliance heads can change members.")
    member = await db.get(OrganizationMember, member_id)
    if not member or member.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Member not found in this workspace.")
    if membership.role != "ORG_ADMIN":
        if member.role == "ORG_ADMIN":
            raise HTTPException(status_code=403, detail="Only organization administrators can change an administrator.")
        if payload.role == "ORG_ADMIN":
            raise HTTPException(status_code=403, detail="Only organization administrators can grant the ORG_ADMIN role.")
    fields = payload.model_fields_set
    if "department_id" in fields:
        await _require_department(db, organization_id, payload.department_id)
    before = audit.pick(member, MEMBER_FIELDS)
    new_role = payload.role if "role" in fields and payload.role else member.role
    new_status = payload.status if "status" in fields and payload.status else member.status
    was_admin = member.role == "ORG_ADMIN" and member.status == "ACTIVE"
    will_be_admin = new_role == "ORG_ADMIN" and new_status == "ACTIVE"
    if was_admin and not will_be_admin and await _active_admin_count(db, organization_id) <= 1:
        raise HTTPException(status_code=400, detail="A workspace needs at least one active administrator.")
    member.role = new_role
    member.status = new_status
    if "department_id" in fields:
        member.department_id = payload.department_id
    b, a = audit.changed(before, audit.pick(member, MEMBER_FIELDS))
    if a:
        audit.record(
            db, organization_id=organization_id, actor_user_id=membership.user_id, action="MEMBER_UPDATED",
            entity_type="member", entity_id=member.id, before=b, after=a, request=request,
        )
    await db.commit()
    await db.refresh(member)
    user = await db.get(User, member.user_id)
    return _member_read(member, user)


@router.get("/{organization_id}/departments", response_model=List[DepartmentRead])
async def list_departments(
    organization_id: UUID,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    depts = (await db.execute(
        select(Department).where(Department.organization_id == organization_id).order_by(Department.name)
    )).scalars().all()
    return await _departments_read(db, organization_id, list(depts))


@router.post("/{organization_id}/departments", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED)
async def create_department(
    organization_id: UUID,
    payload: DepartmentCreate,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    if not perms.can_manage_departments(membership):
        raise HTTPException(status_code=403, detail="Insufficient permissions: only admins and compliance heads can add departments.")
    await _require_member_user(db, organization_id, payload.head_user_id)
    clash = (await db.execute(
        select(Department.id).where(Department.organization_id == organization_id, func.lower(Department.name) == payload.name.lower())
    )).first()
    if clash:
        raise HTTPException(status_code=409, detail="A department with that name already exists.")
    dept = Department(organization_id=organization_id, name=payload.name, head_user_id=payload.head_user_id)
    db.add(dept)
    await db.flush()
    audit.record(
        db, organization_id=organization_id, actor_user_id=membership.user_id, action="DEPARTMENT_CREATED",
        entity_type="department", entity_id=dept.id,
        after={"name": dept.name, "head_user_id": audit._safe(dept.head_user_id)}, request=request,
    )
    await db.commit()
    await db.refresh(dept)
    return (await _departments_read(db, organization_id, [dept]))[0]


@router.patch("/{organization_id}/departments/{department_id}", response_model=DepartmentRead)
async def update_department(
    organization_id: UUID,
    department_id: UUID,
    payload: DepartmentUpdate,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    if not perms.can_manage_departments(membership):
        raise HTTPException(status_code=403, detail="Insufficient permissions: only admins and compliance heads can change departments.")
    dept = await db.get(Department, department_id)
    if not dept or dept.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Department not found in this workspace.")
    fields = payload.model_fields_set
    before = audit.pick(dept, ("name", "head_user_id"))
    if "name" in fields and payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name is required.")
        clash = (await db.execute(
            select(Department.id).where(
                Department.organization_id == organization_id,
                func.lower(Department.name) == name.lower(),
                Department.id != dept.id,
            )
        )).first()
        if clash:
            raise HTTPException(status_code=409, detail="A department with that name already exists.")
        dept.name = name
    if "head_user_id" in fields:
        await _require_member_user(db, organization_id, payload.head_user_id)
        dept.head_user_id = payload.head_user_id
    b, a = audit.changed(before, audit.pick(dept, ("name", "head_user_id")))
    if a:
        audit.record(
            db, organization_id=organization_id, actor_user_id=membership.user_id, action="DEPARTMENT_UPDATED",
            entity_type="department", entity_id=dept.id, before=b, after=a, request=request,
        )
    await db.commit()
    await db.refresh(dept)
    return (await _departments_read(db, organization_id, [dept]))[0]


@router.delete("/{organization_id}/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(
    organization_id: UUID,
    department_id: UUID,
    request: Request,
    membership: OrganizationMember = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_async_db)
):
    if not perms.can_delete_department(membership):
        raise HTTPException(status_code=403, detail="Insufficient permissions: only administrators can delete departments.")
    dept = await db.get(Department, department_id)
    if not dept or dept.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Department not found in this workspace.")
    used = (await db.execute(
        select(ComplianceItem.id).where(ComplianceItem.organization_id == organization_id, ComplianceItem.department_id == dept.id).limit(1)
    )).first()
    if used:
        raise HTTPException(status_code=409, detail="Move its items first.")
    members = (await db.execute(
        select(OrganizationMember).where(OrganizationMember.organization_id == organization_id, OrganizationMember.department_id == dept.id)
    )).scalars().all()
    for m in members:
        m.department_id = None
    audit.record(
        db, organization_id=organization_id, actor_user_id=membership.user_id, action="DEPARTMENT_DELETED",
        entity_type="department", entity_id=dept.id, before={"name": dept.name}, request=request,
    )
    await db.delete(dept)
    await db.commit()
