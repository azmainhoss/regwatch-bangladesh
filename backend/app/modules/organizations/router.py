from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.database.session import get_async_db
from backend.app.modules.identity.deps import get_current_user
from backend.app.modules.identity.models import User
from backend.app.modules.organizations.deps import get_org_membership
from backend.app.modules.organizations.models import Department, Organization, OrganizationMember
from backend.app.modules.organizations.schemas import (
    DepartmentCreate,
    DepartmentRead,
    OrganizationCreate,
    OrganizationMemberCreate,
    OrganizationMemberRead,
    OrganizationRead,
)

router = APIRouter(prefix="/organizations", tags=["Organizations & Tenant Management"])


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


@router.get("/{organization_id}", response_model=OrganizationRead)
async def get_organization(
    organization_id: UUID,
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_async_db)
):
    """Tenant-scoped access: Retrieves organization details."""
    org = await db.get(Organization, organization_id)
    return org


@router.post("/{organization_id}/members", response_model=OrganizationMemberRead, status_code=status.HTTP_201_CREATED)
async def add_organization_member(
    organization_id: UUID,
    payload: OrganizationMemberCreate,
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_async_db)
):
    """Allows ORG_ADMIN to enroll a user into their organization."""
    if membership.role not in ["ORG_ADMIN", "COMPLIANCE_HEAD"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization administrators can add members."
        )

    # Only an ORG_ADMIN (or a platform superuser acting as one) may hand out ORG_ADMIN.
    if payload.role == "ORG_ADMIN" and membership.role != "ORG_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization administrators can grant the ORG_ADMIN role."
        )

    if payload.department_id is not None:
        dept = await db.get(Department, payload.department_id)
        if not dept or dept.organization_id != organization_id:
            raise HTTPException(status_code=400, detail="Department does not belong to this organization.")

    # Check target user
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
    await db.commit()
    await db.refresh(new_member)
    return new_member


@router.get("/{organization_id}/members", response_model=List[OrganizationMemberRead])
async def list_organization_members(
    organization_id: UUID,
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_async_db)
):
    """Tenant-scoped member listing."""
    query = (
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
        .order_by(OrganizationMember.created_at)
    )
    result = await db.execute(query)
    return result.scalars().all()

