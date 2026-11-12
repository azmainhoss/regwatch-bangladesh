from sqlalchemy import Boolean, Column, Date, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship
from backend.app.database.base import Base, GUID


class Obligation(Base):
    __tablename__ = "obligations"

    document_version_id = Column(GUID(), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    provision_id = Column(GUID(), ForeignKey("provisions.id", ondelete="SET NULL"), nullable=True, index=True)
    page_id = Column(GUID(), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    obligation_type = Column(
        String(32),
        nullable=False,
        index=True
    )  # MANDATORY, CONDITIONAL, PROHIBITION, PERMISSION, RECOMMENDATION, REPORTING, RECORD_RETENTION, APPROVAL, DISCLOSURE
    title = Column(Text, nullable=False)
    requirement_description = Column(Text, nullable=False)
    supporting_text = Column(Text, nullable=False)
    # Where the quote came from: sentence IDs (p3.s12) and the line boxes to highlight on the page image.
    quote_span_ids = Column(JSON, nullable=True)
    quote_boxes = Column(JSON, nullable=True)
    applicability_summary = Column(Text, nullable=False)
    explicit_deadline = Column(Date, nullable=True)
    deadline_description = Column(Text, nullable=True)
    frequency = Column(String(32), default="ONE_TIME", nullable=False)  # ONE_TIME, DAILY, WEEKLY, MONTHLY, QUARTERLY, BI_ANNUAL, ANNUAL, EVENT_DRIVEN
    inferable_responsible_dept = Column(String(128), nullable=True)
    is_inferred = Column(Boolean, default=True, nullable=False)
    verification_status = Column(String(32), default="PENDING_REVIEW", nullable=False)  # PENDING_REVIEW, VERIFIED, REJECTED

    version = relationship("DocumentVersion", back_populates="obligations")
    provision = relationship("Provision", back_populates="obligations")
    page = relationship("DocumentPage", back_populates="obligations")
    applicabilities = relationship("ObligationApplicability", back_populates="obligation", cascade="all, delete-orphan")
    compliance_items = relationship("ComplianceItem", back_populates="obligation")


class ObligationApplicability(Base):
    __tablename__ = "obligation_applicability"

    obligation_id = Column(GUID(), ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(
        String(64),
        nullable=False,
        index=True
    )  # SCHEDULED_COMMERCIAL_BANK, ISLAMIC_BANK, NBFI, FOREIGN_BANK, PAYMENT_SERVICE_PROVIDER, MOBILE_FINANCIAL_SERVICE
    conditions = Column(Text, nullable=True)
    is_exempt = Column(Boolean, default=False, nullable=False)

    obligation = relationship("Obligation", back_populates="applicabilities")
