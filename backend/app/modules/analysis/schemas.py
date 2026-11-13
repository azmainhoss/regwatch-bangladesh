from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class CitationRead(BaseModel):
    id: UUID
    page_id: UUID
    quoted_text: str
    match_score: float
    quote_span_ids: Optional[List[str]] = None
    quote_boxes: Optional[List[Dict[str, Any]]] = None

    model_config = ConfigDict(from_attributes=True)


class ClaimRead(BaseModel):
    id: UUID
    claim_type: str
    statement: str
    verification_status: str
    citations: List[CitationRead] = []

    model_config = ConfigDict(from_attributes=True)


class DocumentAnalysisRead(BaseModel):
    id: UUID
    document_version_id: UUID
    executive_summary: str
    purpose: Optional[str] = None
    background: Optional[str] = None
    key_changes: List[Any] = []
    impact_summary: Dict[str, Any] = {}
    model_name: str
    prompt_version: str
    structured_payload: Dict[str, Any] = {}
    citation_coverage_score: float
    tokens_used: int = 0
    estimated_cost_usd: float = 0.0
    processing_time_ms: int = 0
    publication_decision: str
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    claims: List[ClaimRead] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnalyzeDocumentRequest(BaseModel):
    provider: Optional[str] = None  # mock, gemini
    force_human_review: bool = False
    force: bool = False  # run again even when the pages and model are unchanged


class ReviewDocumentRequest(BaseModel):
    decision: str  # PUBLISHED_HUMAN_REVIEWED, REJECTED, NEEDS_REVISION
    review_notes: Optional[str] = None


class ProvisionRead(BaseModel):
    id: UUID
    page_id: UUID
    provision_number: Optional[str] = None
    heading: Optional[str] = None
    verbatim_text: str
    order_index: int
    quote_span_ids: Optional[List[str]] = None
    quote_boxes: Optional[List[Dict[str, Any]]] = None

    model_config = ConfigDict(from_attributes=True)


class ObligationRead(BaseModel):
    id: UUID
    page_id: UUID
    provision_id: Optional[UUID] = None
    obligation_type: str
    title: str
    requirement_description: str
    supporting_text: str
    quote_span_ids: Optional[List[str]] = None
    quote_boxes: Optional[List[Dict[str, Any]]] = None
    applicability_summary: str
    explicit_deadline: Optional[date] = None
    frequency: str
    verification_status: str

    model_config = ConfigDict(from_attributes=True)


class RelationshipRead(BaseModel):
    id: UUID
    source_document_id: UUID
    target_document_id: Optional[UUID] = None
    target_reference_hint: Optional[str] = None
    relationship_type: str
    supporting_quote: str
    quote_span_ids: Optional[List[str]] = None
    quote_boxes: Optional[List[Dict[str, Any]]] = None
    confidence: float
    verification_status: str

    model_config = ConfigDict(from_attributes=True)
