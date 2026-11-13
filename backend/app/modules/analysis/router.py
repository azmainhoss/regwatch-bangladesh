from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.database.session import get_async_db
from backend.app.modules.identity.deps import get_current_superuser, get_current_user
from backend.app.modules.identity.models import User
from backend.app.modules.analysis.models import DocumentAnalysis, AnalysisClaim, ClaimCitation
from backend.app.modules.analysis.schemas import (
    AnalyzeDocumentRequest,
    DocumentAnalysisRead,
    ObligationRead,
    ProvisionRead,
    RelationshipRead,
    ReviewDocumentRequest,
)
from backend.app.modules.analysis.service import AnalysisService
from backend.app.modules.documents.access import get_document_reader, get_visible_document
from backend.app.modules.documents.models import Document
from backend.app.modules.obligations.models import Obligation
from backend.app.modules.organizations.models import OrganizationMember
from backend.app.modules.provisions.models import Provision
from backend.app.modules.relationships.models import DocumentRelationship

router = APIRouter(prefix="/documents", tags=["AI Intelligence & Analysis"])


@router.get("/provider-status")
async def get_provider_status():
    """
    Returns the active AI provider, model identifier, and configuration health.
    Safe public telemetry with zero credentials exposed.
    """
    from backend.app.modules.analysis.providers.factory import get_active_provider_info
    return get_active_provider_info()


@router.post("/provider-test")
async def test_provider_connection(current_user: User = Depends(get_current_superuser)):
    """
    Quick connection check: one tiny call on a cheap model, no retries, short timeout.
    A busy (429/503) or slow service answers "busy" at once instead of waiting through retries.
    The outcome is recorded as the health of the configured analysis model.
    """
    from backend.app.modules.analysis.providers import health
    from backend.app.modules.analysis.providers.factory import (
        get_active_provider_info,
        get_probe_provider,
        probe_message,
        update_provider_health,
    )
    try:
        provider = get_probe_provider()
    except ValueError as e:
        # Missing or unknown configuration: nothing was called, so no health result is recorded.
        info = get_active_provider_info()
        info["test_result"] = {
            "success": False,
            "busy": False,
            "error": str(e),
            "message": "The AI service is not set up on the server yet.",
        }
        return info

    res = await provider.generate_structured_json(
        system_prompt="Health check.",
        user_prompt='Reply with {"status": "ok"}.',
    )
    last = health.current()
    status_name = health.CONNECTED_TESTED if res.success else (last.get("status") or health.TEMPORARILY_UNAVAILABLE)
    if not res.success and last.get("last_status_code") is None:
        status_name = health.TEMPORARILY_UNAVAILABLE  # timeout or network drop
    update_provider_health(
        status=status_name,
        latency_ms=res.latency_ms,
        status_code=last.get("last_status_code"),
        error=res.error,
    )
    info = get_active_provider_info()
    info["test_result"] = {
        "success": res.success,
        "busy": status_name in (health.QUOTA_EXCEEDED, health.TEMPORARILY_UNAVAILABLE),
        "latency_ms": res.latency_ms,
        "error": res.error,
        "message": probe_message(status_name, res.success, res.latency_ms),
    }
    return info


@router.post("/{document_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
async def analyze_document(
    document_id: UUID,
    payload: AnalyzeDocumentRequest = AnalyzeDocumentRequest(),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Starts the analysis in the background and answers at once with its state.
    Poll GET /documents/{id}/analysis-status until it is DONE, FAILED or UNCHANGED.
    """
    from backend.app.modules.analysis import jobs
    doc = await get_visible_document(db, document_id, current_user)
    if not doc.current_version_id:
        raise HTTPException(status_code=404, detail="This circular has no version to analyse.")
    provider_name = payload.provider if not settings.is_production else None
    from backend.app.modules.analysis.auto import pages_waiting
    waiting = await pages_waiting(db, doc.current_version_id)
    if waiting:
        return jobs.mark_waiting_for_pages(document_id, waiting)
    if not payload.force and not payload.force_human_review:
        if await jobs.unchanged_since_last_run(db, document_id, provider_name):
            return jobs.mark_unchanged(document_id)
    return jobs.start(document_id, provider_name=provider_name, force_human_review=payload.force_human_review)


@router.get("/{document_id}/reading-status")
async def get_reading_status(
    document_id: UUID,
    current_user: Optional[User] = Depends(get_document_reader),
    db: AsyncSession = Depends(get_async_db)
):
    """What the circular is waiting for (page reading, daily limit) and roughly how long it will take."""
    from backend.app.modules.analysis.auto import reading_status
    doc = await get_visible_document(db, document_id, current_user)
    return await reading_status(db, doc)


@router.get("/{document_id}/analysis-status")
async def get_analysis_status(
    document_id: UUID,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db)
):
    """State of the latest background analysis: IDLE, RUNNING, DONE, FAILED or UNCHANGED."""
    from backend.app.modules.analysis import jobs
    await get_visible_document(db, document_id, current_user)
    return await jobs.status(db, document_id)


@router.get("/{document_id}/analysis", response_model=DocumentAnalysisRead)
async def get_document_analysis(
    document_id: UUID,
    current_user: Optional[User] = Depends(get_document_reader),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieves the latest structured regulatory analysis for a document.
    """
    doc = await get_visible_document(db, document_id, current_user)
    if not doc.current_version_id:
        raise HTTPException(status_code=404, detail="Document or active version not found")

    query = (
        select(DocumentAnalysis)
        .options(
            selectinload(DocumentAnalysis.claims).selectinload(AnalysisClaim.citations)
        )
        .where(DocumentAnalysis.document_version_id == doc.current_version_id)
        .order_by(DocumentAnalysis.created_at.desc())
    )
    result = await db.execute(query)
    analysis = result.scalars().first()
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis found for this document")
    return analysis


@router.post("/{document_id}/publish")
async def publish_or_review_document(
    document_id: UUID,
    payload: ReviewDocumentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Submits a human review decision and updates document publication status.

    Regulatory documents are shared by every organization (they belong to the
    regulator, not to a tenant), so publishing or withdrawing one is a
    platform-level action reserved for superusers.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: only platform administrators can publish or withdraw regulatory documents."
        )

    doc = await get_visible_document(db, document_id, current_user)
    if doc.owner_user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Private circulars cannot be published to the shared library."
        )

    try:
        updated_doc = await AnalysisService.review_and_publish_analysis(
            db=db,
            document_id=document_id,
            reviewer_id=current_user.id,
            decision=payload.decision,
            review_notes=payload.review_notes
        )
        return {
            "message": f"Document status updated to {updated_doc.publication_status}.",
            "document_id": updated_doc.id,
            "publication_status": updated_doc.publication_status
        }
    except ValueError as ve:
        err_msg = str(ve)
        if "not found" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)


@router.get("/{document_id}/provisions", response_model=List[ProvisionRead])
async def list_document_provisions(
    document_id: UUID,
    current_user: Optional[User] = Depends(get_document_reader),
    db: AsyncSession = Depends(get_async_db)
):
    doc = await get_visible_document(db, document_id, current_user)
    if not doc.current_version_id:
        raise HTTPException(status_code=404, detail="Document not found")

    query = (
        select(Provision)
        .where(Provision.document_version_id == doc.current_version_id)
        .order_by(Provision.order_index)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{document_id}/obligations", response_model=List[ObligationRead])
async def list_document_obligations(
    document_id: UUID,
    current_user: Optional[User] = Depends(get_document_reader),
    db: AsyncSession = Depends(get_async_db)
):
    doc = await get_visible_document(db, document_id, current_user)
    if not doc.current_version_id:
        raise HTTPException(status_code=404, detail="Document not found")

    query = (
        select(Obligation)
        .where(Obligation.document_version_id == doc.current_version_id)
        .order_by(Obligation.created_at)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{document_id}/relationships", response_model=List[RelationshipRead])
async def list_document_relationships(
    document_id: UUID,
    current_user: Optional[User] = Depends(get_document_reader),
    db: AsyncSession = Depends(get_async_db)
):
    await get_visible_document(db, document_id, current_user)
    query = (
        select(DocumentRelationship)
        .where(DocumentRelationship.source_document_id == document_id)
        .order_by(DocumentRelationship.confidence.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()
