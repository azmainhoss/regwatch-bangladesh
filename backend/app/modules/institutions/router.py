from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.database.session import get_async_db
from backend.app.modules.institutions.models import Institution, InstitutionDepartment
from backend.app.modules.institutions.schemas import DepartmentCreate, DepartmentRead, InstitutionCreate, InstitutionRead

router = APIRouter(prefix="/institutions", tags=["Institutions"])


@router.get("", response_model=List[InstitutionRead])
async def list_institutions(db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(
        select(Institution)
        .options(selectinload(Institution.departments))
        .order_by(Institution.name)
    )
    return result.scalars().all()


@router.post("", response_model=InstitutionRead, status_code=status.HTTP_201_CREATED)
async def create_institution(
    payload: InstitutionCreate,
    db: AsyncSession = Depends(get_async_db)
):
    existing = await db.execute(select(Institution).where(Institution.code == payload.code.upper()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Institution with code '{payload.code}' already exists.")
    
    inst = Institution(
        code=payload.code.upper(),
        name=payload.name,
        name_bn=payload.name_bn,
        website_url=payload.website_url,
        is_active=payload.is_active
    )
    db.add(inst)
    await db.commit()
    
    # Reload with departments eager loaded for async Pydantic serialization
    reloaded = await db.execute(
        select(Institution)
        .options(selectinload(Institution.departments))
        .where(Institution.id == inst.id)
    )
    return reloaded.scalar_one()


@router.post("/{institution_id}/departments", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED)
async def add_department(
    institution_id: UUID,
    payload: DepartmentCreate,
    db: AsyncSession = Depends(get_async_db)
):
    inst = await db.get(Institution, institution_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")
    
    dept = InstitutionDepartment(
        institution_id=institution_id,
        code=payload.code.upper(),
        name=payload.name,
        name_bn=payload.name_bn
    )
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return dept
