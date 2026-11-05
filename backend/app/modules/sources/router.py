from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.session import get_async_db
from backend.app.modules.sources.models import Source, SourceRun
from backend.app.modules.sources.schemas import SourceCreate, SourceRead, SourceRunRead

router = APIRouter(prefix="/sources", tags=["Sources & Crawling"])


@router.get("", response_model=List[SourceRead])
async def list_sources(db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(Source).order_by(Source.name))
    return result.scalars().all()


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceCreate,
    db: AsyncSession = Depends(get_async_db)
):
    source = Source(
        institution_id=payload.institution_id,
        name=payload.name,
        source_type=payload.source_type,
        base_url=payload.base_url,
        config=payload.config,
        is_active=payload.is_active
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


@router.get("/runs", response_model=List[SourceRunRead])
async def list_source_runs(
    limit: int = 50,
    db: AsyncSession = Depends(get_async_db)
):
    result = await db.execute(
        select(SourceRun)
        .order_by(SourceRun.started_at.desc())
        .limit(limit)
    )
    return result.scalars().all()
