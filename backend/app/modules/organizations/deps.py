from uuid import UUID
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.session import get_async_db
from backend.app.modules.identity.deps import get_current_user
from backend.app.modules.identity.models import User
from backend.app.modules.organizations.models import Organization, OrganizationMember


async def get_org_membership(
    organization_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
) -> OrganizationMember:
    """
    Enforces server-side tenant isolation:
    Verifies that the calling authenticated user belongs to the requested organization.
    Superusers are granted platform-wide administrative override.
    """
    org = await db.get(Organization, organization_id)
    if not org or not org.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found or inactive"
        )

    # Superuser bypass for platform audit
    if current_user.is_superuser:
        # Return synthetic membership for superuser if not explicitly enrolled
        query = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == current_user.id
        )
        membership = (await db.execute(query)).scalar_one_or_none()
        if membership:
            return membership
        # Temporary admin object
        synthetic = OrganizationMember(
            organization_id=organization_id,
            user_id=current_user.id,
            role="ORG_ADMIN",
            status="ACTIVE"
        )
        return synthetic

    query = select(OrganizationMember).where(
        OrganizationMember.organization_id == organization_id,
        OrganizationMember.user_id == current_user.id,
        OrganizationMember.status == "ACTIVE"
    )
    membership = (await db.execute(query)).scalar_one_or_none()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access forbidden: You are not an active member of this organization."
        )

    return membership



async def get_workspace_membership(
    organization_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
) -> OrganizationMember:
    """Membership check for the bank workspace.

    Same answers as `get_org_membership` (404 for an unknown organization, 403 for a non-member), but there is
    no platform-staff bypass: a bank's data is only open to people the bank added, and the member must be ACTIVE.
    """
    org = await db.get(Organization, organization_id)
    if not org or not org.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found or inactive"
        )
    membership = (await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == current_user.id,
            OrganizationMember.status == "ACTIVE"
        )
    )).scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access forbidden: You are not an active member of this organization."
        )
    return membership
