from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentRef(BaseModel):
    """A circular named inside a link. Only circulars the caller may read ever appear."""
    id: UUID
    reference_number: Optional[str] = None
    title: str
    publication_date: Optional[date] = None
    current_version_id: Optional[UUID] = None
    # True only for the caller's own private uploads.
    is_private: bool = False
    in_force_status: Optional[str] = None


class LinkRead(BaseModel):
    """One relationship with the exact quote and page that support it."""
    id: UUID
    relationship_type: str
    verification_status: str
    confidence: float = 1.0
    detection_method: Optional[str] = None
    supporting_quote: str
    # The page (of the source circular's file) where the quote is printed.
    page_number: Optional[int] = None
    source_version_id: Optional[UUID] = None
    quote_span_ids: Optional[List[str]] = None
    quote_boxes: Optional[List[Dict[str, Any]]] = None
    source: DocumentRef
    target: Optional[DocumentRef] = None
    target_reference_hint: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class StatusRead(BaseModel):
    document_id: UUID
    # IN_FORCE, AMENDED, REPLACED or REPEALED. Counts only links a person or the quote check confirmed.
    in_force_status: str
    # The circular that changed this one (the latest one, for the status shown).
    in_force_by: Optional[DocumentRef] = None
    # The newest circular that is still in force, following replacements forward.
    current_version: Optional[DocumentRef] = None
    chain_has_cycle: bool = False
    verified_incoming: List[LinkRead] = []
    # Awaiting review. Never changes in_force_status.
    unconfirmed_incoming: List[LinkRead] = []
    # What this circular says about earlier ones (confirmed and awaiting review), for the compare buttons.
    outgoing: List[LinkRead] = []


class GraphNode(BaseModel):
    key: str
    document_id: Optional[UUID] = None
    reference_number: Optional[str] = None
    title: str
    publication_date: Optional[date] = None
    in_force_status: Optional[str] = None
    in_library: bool = True
    is_private: bool = False
    is_center: bool = False
    current_version_id: Optional[UUID] = None


class GraphEdge(BaseModel):
    id: UUID
    source: str
    target: str
    relationship_type: str
    verification_status: str
    supporting_quote: str
    page_number: Optional[int] = None
    source_version_id: Optional[UUID] = None
    source_document_id: UUID
    target_document_id: Optional[UUID] = None
    target_reference_hint: Optional[str] = None
    confidence: float = 1.0


class GraphRead(BaseModel):
    document_id: UUID
    depth: int
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
    truncated: bool = False


class TimelineItem(BaseModel):
    document: DocumentRef
    is_selected: bool = False
    is_current: bool = False
    # What this circular does to earlier ones (links it states), each with its quote and page.
    changes: List[LinkRead] = []


class TimelineRead(BaseModel):
    document_id: UUID
    in_force_status: str
    in_force_by: Optional[DocumentRef] = None
    current_version: Optional[DocumentRef] = None
    chain_has_cycle: bool = False
    has_unconfirmed: bool = False
    items: List[TimelineItem] = []


class ReviewRequest(BaseModel):
    decision: Literal["VERIFIED", "REJECTED"]


class ReviewResult(BaseModel):
    link: LinkRead
    # New in-force status of the two circulars the link touches, so screens can redraw at once.
    source_in_force_status: Optional[str] = None
    target_in_force_status: Optional[str] = None


class PendingLinksRead(BaseModel):
    total: int
    limit: int
    offset: int
    links: List[LinkRead] = []


class RelinkResult(BaseModel):
    linked: int
    still_unlinked: int
    message: str

    model_config = ConfigDict(from_attributes=True)
