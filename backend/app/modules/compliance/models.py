from sqlalchemy import BigInteger, Boolean, Column, Date, ForeignKey, JSON, String, Text
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
    obligation_id = Column(GUID(), ForeignKey("obligations.id", ondelete="RESTRICT"), nullable=False, index=True)
    organization_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    internal_code = Column(String(64), nullable=True)
    department_id = Column(GUID(), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_lead_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(
        String(32),
        default="NOT_STARTED",
        nullable=False,
        index=True
    )  # NOT_STARTED, IN_PROGRESS, EVIDENCE_SUBMITTED, COMPLIANT, OVERDUE, EXEMPTED
    internal_deadline = Column(Date, nullable=True)

    register = relationship("ComplianceRegister", back_populates="items")
    obligation = relationship("Obligation", back_populates="compliance_items")
    organization = relationship("Organization", back_populates="compliance_items")
    department = relationship("Department", back_populates="compliance_items")
    assigned_lead = relationship("User", foreign_keys=[assigned_lead_id])
    tasks = relationship("ComplianceTask", back_populates="compliance_item", cascade="all, delete-orphan")


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
    )  # PENDING, IN_PROGRESS, SUBMITTED, APPROVED, REJECTED

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

    task = relationship("ComplianceTask", back_populates="evidence")
    submitted_by_user = relationship("User", back_populates="submitted_evidence")


class TaskReview(Base):
    __tablename__ = "task_reviews"

    task_id = Column(GUID(), ForeignKey("compliance_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_user_id = Column(GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision = Column(String(32), nullable=False)  # APPROVED, CHANGES_REQUESTED, REJECTED
    comments = Column(Text, nullable=False)

    task = relationship("ComplianceTask", back_populates="reviews")
    reviewer_user = relationship("User", back_populates="reviews")


class TaskEvent(Base):
    __tablename__ = "task_events"

    task_id = Column(GUID(), ForeignKey("compliance_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(64), nullable=False)  # TASK_CREATED, STATUS_CHANGED, EVIDENCE_ADDED, REVIEW_SUBMITTED
    event_payload = Column(JSON, default=dict, nullable=False)

    task = relationship("ComplianceTask", back_populates="events")
