from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import logger
from backend.app.database.session import get_async_db
from backend.app.modules.audit.models import AuditEvent
from backend.app.modules.documents.access import get_document_reader, get_visible_document
from backend.app.modules.documents.models import Document
from backend.app.modules.identity.deps import get_current_superuser
from backend.app.modules.identity.models import User
from backend.app.modules.relationships.graph import build_graph, build_status, build_timeline
from backend.app.modules.relationships.linking import link_relationship_targets
from backend.app.modules.relationships.models import DocumentRelationship
from backend.app.modules.relationships.schemas import (
    GraphRead,
    PendingLinksRead,
    RelinkResult,
    ReviewRequest,
    ReviewResult,
    StatusRead,
    TimelineRead,
)
from backend.app.modules.relationships.status import build_links, bulk_in_force, load_visible_docs, visible_to

router = APIRouter(prefix="/relationships", tags=["Relationships"])


@router.get("/document/{document_id}/graph", response_model=GraphRead)
async def get_relationship_graph(
    document_id: UUID,
    depth: int = Query(2, ge=1, le=3),
    current_user: Optional[User] = Depends(get_document_reader),
    db: AsyncSession = Depends(get_async_db),
):
    """The circulars linked to this one in both directions, up to `depth` steps (at most 3).
    Cited circulars that are not in the library appear as nodes of their own."""
    doc = await get_visible_document(db, document_id, current_user)
    return await build_graph(db, doc, current_user, depth)


@router.get("/document/{document_id}/timeline", response_model=TimelineRead)
async def get_relationship_timeline(
    document_id: UUID,
    current_user: Optional[User] = Depends(get_document_reader),
    db: AsyncSession = Depends(get_async_db),
):
    """The circulars that changed this rule, oldest first, each with the quote and page that state the change."""
    doc = await get_visible_document(db, document_id, current_user)
    return await build_timeline(db, doc, current_user)


@router.get("/document/{document_id}/status", response_model=StatusRead)
async def get_in_force_status(
    document_id: UUID,
    current_user: Optional[User] = Depends(get_document_reader),
    db: AsyncSession = Depends(get_async_db),
):
    """In force, amended, replaced or repealed, the circular that changed it, and the newest one still in force."""
    doc = await get_visible_document(db, document_id, current_user)
    return await build_status(db, doc, current_user)


@router.get("/pending", response_model=PendingLinksRead)
async def list_pending_links(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db),
):
    """Links waiting for an administrator's decision (admin only)."""
    base = (
        select(DocumentRelationship)
        .join(Document, Document.id == DocumentRelationship.source_document_id)
        .where(DocumentRelationship.verification_status == "PENDING_REVIEW", visible_to(Document, current_user))
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(
            base.order_by(Document.publication_date.desc(), DocumentRelationship.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    ids = []
    for r in rows:
        ids.append(r.source_document_id)
        ids.append(r.target_document_id)
    docs = await load_visible_docs(db, ids, current_user)
    statuses = await bulk_in_force(db, [d.id for d in docs.values()], current_user)
    return PendingLinksRead(total=total, limit=limit, offset=offset, links=await build_links(db, rows, docs, statuses))


@router.post("/relink", response_model=RelinkResult)
async def relink_everything(
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db),
):
    """Looks again for the stored circular each unlinked hint names (admin only)."""
    linked = await link_relationship_targets(db)
    remaining = (
        await db.execute(
            select(func.count())
            .select_from(DocumentRelationship)
            .where(
                DocumentRelationship.target_document_id.is_(None),
                DocumentRelationship.target_reference_hint.isnot(None),
                DocumentRelationship.target_reference_hint != "",
            )
        )
    ).scalar_one()
    return RelinkResult(linked=linked, still_unlinked=remaining, message=f"Linked {linked} relationship(s).")


async def _announce_library_change(db, doc_ids) -> None:
    """After a commit: check the banks that use these circulars. Never raises."""
    try:
        from backend.app.modules.alerts.sweeps import library_changed
        await library_changed(db, doc_ids)
    except Exception as exc:
        logger.warning("Alert not recorded: %s", type(exc).__name__)


@router.post("/{relationship_id}/review", response_model=ReviewResult)
async def review_relationship(
    relationship_id: UUID,
    payload: ReviewRequest,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db),
):
    """Confirms (VERIFIED) or rejects a link (admin only). Only confirmed links change a circular's in-force status."""
    rel = await db.get(DocumentRelationship, relationship_id)
    if rel is None:
        raise HTTPException(status_code=404, detail="Relationship not found")
    # A link stated by somebody else's private upload looks missing, even to an administrator.
    await get_visible_document(db, rel.source_document_id, current_user)

    before = rel.verification_status
    rel.verification_status = payload.decision
    rel.reviewed_by = current_user.id
    rel.reviewed_at = datetime.now(timezone.utc)
    db.add(
        AuditEvent(
            actor_user_id=current_user.id,
            action="RELATIONSHIP_REVIEWED",
            entity_type="document_relationship",
            entity_id=rel.id,
            before_state={"verification_status": before},
            after_state={
                "verification_status": payload.decision,
                "relationship_type": rel.relationship_type,
                "source_document_id": str(rel.source_document_id),
                "target_document_id": str(rel.target_document_id) if rel.target_document_id else None,
            },
        )
    )
    await db.commit()
    await _announce_library_change(db, [rel.target_document_id] if rel.target_document_id else [])
    await db.refresh(rel)

    docs = await load_visible_docs(db, [rel.source_document_id, rel.target_document_id], current_user)
    statuses = await bulk_in_force(db, [d.id for d in docs.values()], current_user)
    links = await build_links(db, [rel], docs, statuses)
    link = links[0]
    return ReviewResult(
        link=link,
        source_in_force_status=statuses[str(rel.source_document_id)].status,
        target_in_force_status=statuses[str(rel.target_document_id)].status if rel.target_document_id and str(rel.target_document_id) in statuses else None,
    )
