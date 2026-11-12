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
    Executes an active on-demand handshake probe against the configured AI provider.
    Updates runtime telemetry without exposing credentials.
    """
    from backend.app.modules.analysis.providers.factory import get_ai_provider, get_active_provider_info
    try:
        provider = get_ai_provider()
        res = await provider.generate_structured_json(
            system_prompt="You are a health probe assistant.",
            user_prompt="Reply with a JSON having key 'status' and value 'healthy'."
        )
        info = get_active_provider_info()
        info["test_result"] = {
            "success": res.success,
            "latency_ms": res.latency_ms,
            "error": res.error
        }
        return info
    except ValueError as e:
        # Missing or unknown configuration: nothing was called, so no health result is recorded.
        info = get_active_provider_info()
        info["test_result"] = {
            "success": False,
            "error": str(e)
        }
        return info
    except Exception as e:
        from backend.app.modules.analysis.providers.factory import update_provider_health
        update_provider_health(status="TEMPORARILY_UNAVAILABLE", error=str(e))
        info = get_active_provider_info()
        info["test_result"] = {
            "success": False,
            "error": str(e)
        }
        return info


@router.post("/{document_id}/analyze", response_model=DocumentAnalysisRead, status_code=status.HTTP_200_OK)
async def analyze_document(
    document_id: UUID,
    payload: AnalyzeDocumentRequest = AnalyzeDocumentRequest(),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Executes the multi-stage AI intelligence pipeline on a document.
    Extracts summary, provisions, obligations, relationships, and runs deterministic citation validation.
    """
    await get_visible_document(db, document_id, current_user)
    try:
        analysis = await AnalysisService.analyze_document_version(
            db=db,
            document_id=document_id,
            provider_name=payload.provider if not settings.is_production else None,
            force_human_review=payload.force_human_review
        )
        # Reload with claims and citations for serialization
        query = (
            select(DocumentAnalysis)
            .options(
                selectinload(DocumentAnalysis.claims).selectinload(AnalysisClaim.citations)
            )
            .where(DocumentAnalysis.id == analysis.id)
        )
        result = await db.execute(query)
        return result.scalar_one()
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis pipeline execution error: {str(e)}")


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
