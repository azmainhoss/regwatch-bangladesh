from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
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

    analysis = relationship("DocumentAnalysis", back_populates="claims")
    citations = relationship("ClaimCitation", back_populates="claim", cascade="all, delete-orphan")


class ClaimCitation(Base):
    __tablename__ = "claim_citations"

    claim_id = Column(GUID(), ForeignKey("analysis_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id = Column(GUID(), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    quoted_text = Column(Text, nullable=False)
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
