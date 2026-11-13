from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.database.base import Base, GUID


class ComplianceRegister(Base):
    __tablename__ = "compliance_registers"

    organization_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    organization = relationship("Organization", back_populates="registers")
    items = relationship("ComplianceItem", back_populates="register", cascade="all, delete-orphan")


class ComplianceItem(Base):
    __tablename__ = "compliance_items"

    register_id = Column(GUID(), ForeignKey("compliance_registers.id", ondelete="CASCADE"), nullable=False, index=True)
    # Only a hint. The snapshot columns below are the record, so re-reading a circular never breaks an item.
    obligation_id = Column(GUID(), ForeignKey("obligations.id", ondelete="SET NULL"), nullable=True, index=True)
    organization_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    internal_code = Column(String(64), nullable=True)
    department_id = Column(GUID(), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_lead_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(
        String(32),
        default="NOT_STARTED",
        nullable=False,
        index=True
    )  # NOT_STARTED, IN_PROGRESS, EVIDENCE_SUBMITTED, COMPLIANT, EXEMPTED (overdue is worked out, never stored)
    internal_deadline = Column(Date, nullable=True)

    # Snapshot of the obligation and its source, copied once when the item is created and never changed.
    source_document_id = Column(GUID(), ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True, index=True)
    source_version_id = Column(GUID(), ForeignKey("document_versions.id", ondelete="RESTRICT"), nullable=True)
    source_file_sha256 = Column(String(64), nullable=True)
    source_reference_number = Column(String(128), nullable=True)
    source_title = Column(Text, nullable=True)
    source_publication_date = Column(Date, nullable=True)
    source_page_number = Column(Integer, nullable=True)
    source_quote = Column(Text, nullable=True)
    source_quote_span_ids = Column(JSON, nullable=True)
    source_quote_boxes = Column(JSON, nullable=True)
    source_key = Column(String(64), nullable=True)
    obligation_title = Column(Text, nullable=True)
    requirement_description = Column(Text, nullable=True)
    obligation_type = Column(String(32), nullable=True)
    applicability_summary = Column(Text, nullable=True)
    regulatory_deadline = Column(Date, nullable=True)
    deadline_description = Column(Text, nullable=True)
    frequency = Column(String(32), nullable=True)

    # Workflow
    notes = Column(Text, nullable=True)
    exemption_reason = Column(Text, nullable=True)
    submitted_for_signoff_by_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_for_signoff_at = Column(DateTime(timezone=True), nullable=True)
    signed_off_by_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    signed_off_at = Column(DateTime(timezone=True), nullable=True)
    source_ack_signature = Column(String(255), nullable=True)
    source_ack_at = Column(DateTime(timezone=True), nullable=True)
    source_ack_by_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source_ack_note = Column(Text, nullable=True)
    lock_version = Column(Integer, nullable=False, default=1, server_default="1")

    register = relationship("ComplianceRegister", back_populates="items")
    obligation = relationship("Obligation", back_populates="compliance_items")
    organization = relationship("Organization", back_populates="compliance_items")
    department = relationship("Department", back_populates="compliance_items")
    assigned_lead = relationship("User", foreign_keys=[assigned_lead_id])
    tasks = relationship("ComplianceTask", back_populates="compliance_item", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("register_id", "source_key", name="uq_register_item_source"),
        Index("ix_compliance_items_org_updated", "organization_id", "updated_at"),
    )


class ComplianceItemReview(Base):
    """A sign-off decision on a whole item. Add-only."""
    __tablename__ = "compliance_item_reviews"

    item_id = Column(GUID(), ForeignKey("compliance_items.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_user_id = Column(GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision = Column(String(32), nullable=False)  # APPROVED, REJECTED
    comments = Column(Text, nullable=False)


class ComplianceTask(Base):
    __tablename__ = "compliance_tasks"

    compliance_item_id = Column(GUID(), ForeignKey("compliance_items.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    assigned_to_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    due_date = Column(Date, nullable=False, index=True)
    priority = Column(String(16), default="MEDIUM", nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    status = Column(
        String(32),
        default="PENDING",
        nullable=False,
        index=True
    )  # PENDING, IN_PROGRESS, SUBMITTED, APPROVED, REJECTED, CANCELLED
    cancelled_reason = Column(Text, nullable=True)
    lock_version = Column(Integer, nullable=False, default=1, server_default="1")

    __table_args__ = (Index("ix_compliance_tasks_org_updated", "organization_id", "updated_at"),)

    compliance_item = relationship("ComplianceItem", back_populates="tasks")
    organization = relationship("Organization", back_populates="tasks")
    assigned_to_user = relationship("User", foreign_keys=[assigned_to_user_id], back_populates="assigned_tasks")
    evidence = relationship("TaskEvidence", back_populates="task", cascade="all, delete-orphan")
    reviews = relationship("TaskReview", back_populates="task", cascade="all, delete-orphan")
    events = relationship("TaskEvent", back_populates="task", cascade="all, delete-orphan")


class TaskEvidence(Base):
    __tablename__ = "task_evidence"

    task_id = Column(GUID(), ForeignKey("compliance_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    submitted_by_user_id = Column(GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    file_sha256 = Column(String(64), nullable=False)
    storage_path = Column(String(512), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    notes = Column(Text, nullable=True)
    mime_type = Column(String(128), nullable=True)
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    withdrawn_by_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    task = relationship("ComplianceTask", back_populates="evidence")
    submitted_by_user = relationship("User", back_populates="submitted_evidence", foreign_keys=[submitted_by_user_id])


class TaskReview(Base):
    __tablename__ = "task_reviews"

    task_id = Column(GUID(), ForeignKey("compliance_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(GUID(), nullable=True, index=True)
    reviewer_user_id = Column(GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision = Column(String(32), nullable=False)  # APPROVED, CHANGES_REQUESTED, REJECTED
    comments = Column(Text, nullable=False)
    evidence_ids = Column(JSON, nullable=True)  # the evidence files the reviewer saw

    task = relationship("ComplianceTask", back_populates="reviews")
    reviewer_user = relationship("User", back_populates="reviews")


class TaskEvent(Base):
    __tablename__ = "task_events"

    task_id = Column(GUID(), ForeignKey("compliance_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(64), nullable=False)  # TASK_CREATED, STATUS_CHANGED, EVIDENCE_ADDED, REVIEW_SUBMITTED
    event_payload = Column(JSON, default=dict, nullable=False)

    task = relationship("ComplianceTask", back_populates="events")
