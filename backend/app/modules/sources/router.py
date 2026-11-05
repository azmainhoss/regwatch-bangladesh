from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.session import get_async_db
from backend.app.modules.identity.deps import get_current_user
from backend.app.modules.identity.models import User
from backend.app.modules.sources.models import Source, SourceDiscovery, SourceRun
from backend.app.modules.sources.schemas import (
    RejectDiscoveryRequest,
    SourceCreate,
    SourceDiscoveryRead,
    SourceRead,
    SourceRunRead,
    SourceUpdate,
)
from backend.app.modules.sources.service import source_monitoring_service

router = APIRouter(prefix="/sources", tags=["Sources & Crawling"])


@router.get("", response_model=List[SourceRead])
async def list_sources(db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(Source).order_by(Source.name))
    return result.scalars().all()


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    source = Source(
        institution_id=payload.institution_id,
        department_id=payload.department_id,
        name=payload.name,
        source_type=payload.source_type,
        monitoring_method=payload.monitoring_method,
        base_url=payload.base_url,
        polling_frequency_minutes=payload.polling_frequency_minutes,
        config=payload.config,
        is_active=payload.is_active
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


@router.get("/runs", response_model=List[SourceRunRead])
async def list_source_runs(
    source_id: Optional[UUID] = Query(None),
    limit: int = 50,
    db: AsyncSession = Depends(get_async_db)
):
    query = select(SourceRun).order_by(SourceRun.started_at.desc()).limit(limit)
    if source_id:
        query = query.where(SourceRun.source_id == source_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/discoveries", response_model=List[SourceDiscoveryRead])
async def list_discoveries(
    status_filter: Optional[str] = Query(None),
    limit: int = 50,
    db: AsyncSession = Depends(get_async_db)
):
    """Admin Discovery Review Queue: Lists candidate circulars awaiting approval or review."""
    query = select(SourceDiscovery).order_by(SourceDiscovery.created_at.desc()).limit(limit)
    if status_filter:
        query = query.where(SourceDiscovery.status == status_filter)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/discoveries/{discovery_id}/approve", status_code=status.HTTP_200_OK)
async def approve_discovery(
    discovery_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Approves a candidate publication from the review queue and triggers ingestion."""
    try:
        doc = await source_monitoring_service.approve_and_ingest_discovery(db=db, discovery_id=discovery_id)
        return {
            "status": "APPROVED",
            "message": f"Successfully ingested '{doc.title}'",
            "document_id": str(doc.id)
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/discoveries/{discovery_id}/reject", response_model=SourceDiscoveryRead)
async def reject_discovery(
    discovery_id: UUID,
    payload: RejectDiscoveryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Rejects an ineligible or duplicate discovery with human-reviewed rationale."""
    try:
        disc = await source_monitoring_service.reject_discovery(
            db=db,
            discovery_id=discovery_id,
            reason=payload.reason
        )
        return disc
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{source_id}", response_model=SourceRead)
async def get_source(source_id: UUID, db: AsyncSession = Depends(get_async_db)):
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.patch("/{source_id}", response_model=SourceRead)
async def update_source(
    source_id: UUID,
    payload: SourceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(source, field, val)

    await db.commit()
    await db.refresh(source)
    return source


@router.post("/{source_id}/trigger", response_model=SourceRunRead)
async def trigger_source_monitoring(
    source_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Triggers an immediate discovery and monitoring run for the designated source.
    Returns the executed SourceRun with diagnostic telemetry and anti-bot checks.
    """
    try:
        run = await source_monitoring_service.execute_source_monitoring(
            db=db,
            source_id=source_id,
            run_type="MANUAL_TRIGGER"
        )
        return run
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Source execution failed: {str(e)}")
