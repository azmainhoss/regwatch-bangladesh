from sqlalchemy import Column, DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship
from backend.app.database.base import Base, GUID


class DocumentRelationship(Base):
    __tablename__ = "document_relationships"

    source_document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    target_document_id = Column(GUID(), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    target_reference_hint = Column(String(255), nullable=True)  # Used when target circular is not yet in platform
    relationship_type = Column(
        String(32),
        nullable=False,
        index=True
    )  # AMENDS, REPEALS, SUPERSEDES, REPLACES, CLARIFIES, REFERENCES, IMPLEMENTS, RELATED_TO
    source_provision_id = Column(GUID(), ForeignKey("provisions.id", ondelete="SET NULL"), nullable=True)
    source_page_id = Column(GUID(), ForeignKey("document_pages.id", ondelete="SET NULL"), nullable=True)
    supporting_quote = Column(Text, nullable=False)
    # Where the quote came from: sentence IDs (p3.s12) and the line boxes to highlight on the page image.
    quote_span_ids = Column(JSON, nullable=True)
    quote_boxes = Column(JSON, nullable=True)
    confidence = Column(Float, default=1.0, nullable=False)
    detection_method = Column(String(32), default="DETERMINISTIC_REGEX", nullable=False)  # DETERMINISTIC_REGEX, AI_INFERRED, MANUAL_ENTRY
    verification_status = Column(String(32), default="PENDING_REVIEW", nullable=False)  # PENDING_REVIEW, VERIFIED, REJECTED
    reviewed_by = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    source_document = relationship("Document", foreign_keys=[source_document_id], back_populates="outgoing_relationships")
    target_document = relationship("Document", foreign_keys=[target_document_id], back_populates="incoming_relationships")
