from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.database.session import get_async_db
from backend.app.modules.identity.deps import get_current_user
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


@router.post("/{document_id}/analyze", response_model=DocumentAnalysisRead, status_code=status.HTTP_200_OK)
async def analyze_document(
    document_id: UUID,
    payload: AnalyzeDocumentRequest = AnalyzeDocumentRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Executes the multi-stage AI intelligence pipeline on a document.
    Extracts summary, provisions, obligations, relationships, and runs deterministic citation validation.
    """
    try:
        analysis = await AnalysisService.analyze_document_version(
            db=db,
            document_id=document_id,
            provider_name=payload.provider,
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
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieves the latest structured regulatory analysis for a document.
    """
    doc = await db.get(Document, document_id)
    if not doc or not doc.current_version_id:
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
    Requires authenticated compliance reviewer or superuser authorization.
    """
    # Authorization verification: superuser or active ORG_ADMIN/COMPLIANCE_HEAD
    is_authorized = current_user.is_superuser
    if not is_authorized:
        membership_query = select(OrganizationMember).where(
            OrganizationMember.user_id == current_user.id,
            OrganizationMember.status == "ACTIVE",
            OrganizationMember.role.in_(["ORG_ADMIN", "COMPLIANCE_HEAD"])
        )
        memberships = (await db.execute(membership_query)).scalars().all()
        if memberships:
            is_authorized = True

    if not is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: User lacks compliance reviewer or administrative authorization to publish regulatory intelligence."
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
    db: AsyncSession = Depends(get_async_db)
):
    doc = await db.get(Document, document_id)
    if not doc or not doc.current_version_id:
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
    db: AsyncSession = Depends(get_async_db)
):
    doc = await db.get(Document, document_id)
    if not doc or not doc.current_version_id:
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
    db: AsyncSession = Depends(get_async_db)
):
    query = (
        select(DocumentRelationship)
        .where(DocumentRelationship.source_document_id == document_id)
        .order_by(DocumentRelationship.confidence.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()
