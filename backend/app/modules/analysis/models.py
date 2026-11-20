from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from backend.app.database.base import Base, GUID


class DocumentAnalysis(Base):
    __tablename__ = "document_analyses"

    document_version_id = Column(GUID(), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    executive_summary = Column(Text, nullable=False)
    purpose = Column(Text, nullable=True)
    background = Column(Text, nullable=True)
    key_changes = Column(JSON, default=list, nullable=False)
    impact_summary = Column(JSON, default=dict, nullable=False)
    model_name = Column(String(64), nullable=False)
    prompt_version = Column(String(32), nullable=False)
    structured_payload = Column(JSON, default=dict, nullable=False)
    citation_coverage_score = Column(Float, default=1.0, nullable=False)
    raw_model_response = Column(Text, nullable=True)
    validation_errors = Column(JSON, default=list, nullable=False)
    tokens_used = Column(Integer, default=0, nullable=False)
    estimated_cost_usd = Column(Float, default=0.0, nullable=False)
    processing_time_ms = Column(Integer, default=0, nullable=False)
    publication_decision = Column(String(32), default="AWAITING_REVIEW", nullable=False)  # AWAITING_REVIEW, APPROVED, REJECTED, NEEDS_REVISION
    reviewed_by = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)

    version = relationship("DocumentVersion", back_populates="analyses")
    claims = relationship("AnalysisClaim", back_populates="analysis", cascade="all, delete-orphan")
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class AnalysisClaim(Base):
    __tablename__ = "analysis_claims"

    analysis_id = Column(GUID(), ForeignKey("document_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_type = Column(String(64), nullable=False)  # SUMMARY_STATEMENT, OBLIGATION_ASSERTION, IMPACT_CLAIM
    statement = Column(Text, nullable=False)
    verification_status = Column(String(32), default="VERIFIED", nullable=False)
    # Claim checks (docs/specs/CLAIM_CHECKS_SPEC.md): one claim per shown item, checked and hidden on its own.
    kind = Column(String(32), default="PROVISION", server_default="PROVISION", nullable=False, index=True)
    order_index = Column(Integer, default=0, server_default="0")
    fields = Column(JSON, default=dict)
    evidence = Column(JSON, default=dict)
    checks = Column(JSON, default=list)
    check_status = Column(String(32), default="CHECKING", server_default="CHECKING", nullable=False, index=True)
    review_queue = Column(String(16), nullable=True, index=True)
    is_high_stakes = Column(Boolean, default=False, server_default="0")
    obligation_id = Column(GUID(), ForeignKey("obligations.id", ondelete="SET NULL"), nullable=True)
    relationship_id = Column(GUID(), ForeignKey("document_relationships.id", ondelete="SET NULL"), nullable=True)
    fingerprint = Column(String(64), nullable=True, index=True)
    carried_from_claim_id = Column(GUID(), nullable=True)
    original_fields = Column(JSON, nullable=True)
    reviewed_by = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)
    reject_reason = Column(String(64), nullable=True)

    analysis = relationship("DocumentAnalysis", back_populates="claims")
    citations = relationship("ClaimCitation", back_populates="claim", cascade="all, delete-orphan")


class ClaimCitation(Base):
    __tablename__ = "claim_citations"

    claim_id = Column(GUID(), ForeignKey("analysis_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id = Column(GUID(), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    quoted_text = Column(Text, nullable=False)
    # Where the quote came from: sentence IDs (p3.s12) and the line boxes to highlight on the page image.
    quote_span_ids = Column(JSON, nullable=True)
    quote_boxes = Column(JSON, nullable=True)
    match_score = Column(Float, default=1.0, nullable=False)

    claim = relationship("AnalysisClaim", back_populates="citations")
    page = relationship("DocumentPage")


class AnalysisLease(Base):
    __tablename__ = "analysis_leases"

    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    owner_worker_id = Column(String(128), nullable=False)
    lease_token = Column(String(64), nullable=False)
    acquired_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    heartbeat_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(32), default="ACTIVE", nullable=False)  # ACTIVE, RELEASED, EXPIRED, FAILED

    document = relationship("Document")
