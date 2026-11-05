from sqlalchemy import Column, Float, ForeignKey, Integer, JSON, String, Text
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

    version = relationship("DocumentVersion", back_populates="analyses")
    claims = relationship("AnalysisClaim", back_populates="analysis", cascade="all, delete-orphan")


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
