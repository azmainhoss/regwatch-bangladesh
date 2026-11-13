from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.modules.organizations.schemas import UserMini

ItemStatus = Literal["NOT_STARTED", "IN_PROGRESS", "EVIDENCE_SUBMITTED", "COMPLIANT", "EXEMPTED"]
Priority = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
TaskReviewDecision = Literal["APPROVED", "CHANGES_REQUESTED", "REJECTED"]
SignoffDecision = Literal["APPROVED", "REJECTED"]


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class Stripped(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _strip_strings(cls, v):
        return _strip(v)


# --- registers ---------------------------------------------------------------
class RegisterCreate(Stripped):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)


class RegisterUpdate(Stripped):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    is_active: Optional[bool] = None


class ItemCounts(BaseModel):
    total: int = 0
    not_started: int = 0
    in_progress: int = 0
    evidence_submitted: int = 0
    compliant: int = 0
    exempted: int = 0
    overdue: int = 0
    flagged: int = 0


class RegisterRead(BaseModel):
    id: UUID
    organization_id: UUID
    title: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    item_counts: ItemCounts = ItemCounts()
    source_document_ids: List[UUID] = []


# --- items -----------------------------------------------------------------
class DocRef(BaseModel):
    id: UUID
    reference_number: Optional[str] = None
    title: str


class SourceRef(BaseModel):
    document_id: Optional[UUID] = None
    version_id: Optional[UUID] = None
    reference_number: Optional[str] = None
    title: Optional[str] = None
    publication_date: Optional[date] = None
    page_number: Optional[int] = None
    quote: Optional[str] = None
    quote_span_ids: Optional[Any] = None
    quote_boxes: Optional[Any] = None
    file_sha256: Optional[str] = None
    page_link: Optional[str] = None
    in_force_status: str = "IN_FORCE"
    in_force_by: Optional[DocRef] = None
    current_version_id: Optional[UUID] = None
    is_withdrawn: bool = False


class SourceChange(BaseModel):
    kind: Literal["AMENDED", "REPLACED", "REPEALED", "NEW_VERSION", "WITHDRAWN"]
    by: Optional[DocRef] = None
    detail: str


class TaskCounts(BaseModel):
    total: int = 0
    open: int = 0
    submitted: int = 0
    approved: int = 0
    overdue: int = 0


class ItemRead(BaseModel):
    id: UUID
    organization_id: UUID
    register_id: UUID
    internal_code: Optional[str] = None
    obligation_id: Optional[UUID] = None
    obligation_title: Optional[str] = None
    requirement_description: Optional[str] = None
    obligation_type: Optional[str] = None
    applicability_summary: Optional[str] = None
    frequency: Optional[str] = None
    regulatory_deadline: Optional[date] = None
    deadline_description: Optional[str] = None
    internal_deadline: Optional[date] = None
    effective_deadline: Optional[date] = None
    status: str
    display_status: str
    is_overdue: bool
    days_left: Optional[int] = None
    department_id: Optional[UUID] = None
    assigned_lead: Optional[UserMini] = None
    notes: Optional[str] = None
    exemption_reason: Optional[str] = None
    submitted_for_signoff_by: Optional[UserMini] = None
    submitted_for_signoff_at: Optional[datetime] = None
    signed_off_by: Optional[UserMini] = None
    signed_off_at: Optional[datetime] = None
    source: SourceRef
    source_change: Optional[SourceChange] = None
    task_counts: TaskCounts = TaskCounts()
    evidence_count: int = 0
    lock_version: int
    created_at: datetime
    updated_at: datetime


class ItemCreate(Stripped):
    register_id: UUID
    obligation_id: UUID
    internal_code: Optional[str] = Field(default=None, max_length=64)
    department_id: Optional[UUID] = None
    assigned_lead_id: Optional[UUID] = None
    internal_deadline: Optional[date] = None


class ItemUpdate(Stripped):
    department_id: Optional[UUID] = None
    assigned_lead_id: Optional[UUID] = None
    internal_deadline: Optional[date] = None
    internal_code: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=5000)
    lock_version: Optional[int] = None


class ItemStatusChange(Stripped):
    to: Literal["NOT_STARTED", "IN_PROGRESS", "EVIDENCE_SUBMITTED", "EXEMPTED"]
    reason: Optional[str] = Field(default=None, max_length=2000)
    lock_version: Optional[int] = None


class ItemSignoff(Stripped):
    decision: SignoffDecision
    comments: str = Field(default="", max_length=2000)


class AcknowledgeChange(Stripped):
    note: str = Field(min_length=1, max_length=2000)


class ReopenItem(Stripped):
    reason: str = Field(min_length=1, max_length=2000)


class FromDocument(Stripped):
    document_id: UUID
    obligation_ids: Optional[List[UUID]] = None


class RegisterFromDocument(FromDocument):
    title: Optional[str] = Field(default=None, max_length=255)


class Skipped(BaseModel):
    obligation_id: UUID
    reason: str


class ItemsAdded(BaseModel):
    items: List[ItemRead]
    skipped: List[Skipped] = []


class RegisterCreated(BaseModel):
    register: RegisterRead
    items: List[ItemRead]
    skipped: List[Skipped] = []


class ItemList(BaseModel):
    items: List[ItemRead]
    total: int
    as_of: date
    server_time: datetime


class AddableObligation(BaseModel):
    id: UUID
    title: str
    obligation_type: str
    page_number: Optional[int] = None
    quote: str
    regulatory_deadline: Optional[date] = None
    verification_status: str
    addable: bool
    reason_not_addable: Optional[str] = None
    already_in_register_ids: List[UUID] = []


class AddableDocument(BaseModel):
    id: UUID
    reference_number: Optional[str] = None
    title: str
    publication_status: str
    in_force_status: str
    in_force_by: Optional[DocRef] = None
    current_version_id: Optional[UUID] = None


class AddableObligations(BaseModel):
    document: AddableDocument
    obligations: List[AddableObligation]


# --- tasks -----------------------------------------------------------------
class TaskCreate(Stripped):
    compliance_item_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    assigned_to_user_id: Optional[UUID] = None
    due_date: date
    priority: Priority = "MEDIUM"


class TaskUpdate(Stripped):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    assigned_to_user_id: Optional[UUID] = None
    due_date: Optional[date] = None
    priority: Optional[Priority] = None
    status: Optional[Literal["PENDING", "IN_PROGRESS"]] = None
    lock_version: Optional[int] = None


class TaskCancel(Stripped):
    reason: str = Field(min_length=1, max_length=2000)


class TaskRead(BaseModel):
    id: UUID
    organization_id: UUID
    compliance_item_id: UUID
    title: str
    description: Optional[str] = None
    assigned_to_user_id: Optional[UUID] = None
    assigned_to: Optional[UserMini] = None
    due_date: date
    priority: str
    status: str
    is_overdue: bool = False
    days_left: Optional[int] = None
    cancelled_reason: Optional[str] = None
    evidence_count: int = 0
    uploader_ids: List[UUID] = []
    lock_version: int
    created_at: datetime
    updated_at: datetime


class TaskList(BaseModel):
    tasks: List[TaskRead]
    total: int
    as_of: date
    server_time: datetime


class EvidenceRead(BaseModel):
    id: UUID
    task_id: UUID
    organization_id: UUID
    submitted_by_user_id: UUID
    submitted_by: UserMini
    file_sha256: str
    original_filename: str
    file_size_bytes: int
    mime_type: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    withdrawn_at: Optional[datetime] = None
    withdrawn_by: Optional[UserMini] = None


class EvidenceWithdraw(Stripped):
    reason: str = Field(min_length=1, max_length=2000)


class TaskReviewCreate(Stripped):
    decision: TaskReviewDecision
    comments: str = Field(default="", max_length=2000)


class TaskReviewRead(BaseModel):
    id: UUID
    task_id: UUID
    reviewer_user_id: UUID
    reviewer: UserMini
    decision: str
    comments: str
    evidence_ids: Optional[List[str]] = None
    created_at: datetime


class ItemReviewRead(BaseModel):
    id: UUID
    item_id: UUID
    reviewer: UserMini
    decision: str
    comments: str
    created_at: datetime


class TaskWriteResult(BaseModel):
    task: TaskRead
    item: ItemRead


class EvidenceWriteResult(BaseModel):
    evidence: EvidenceRead
    task: TaskRead
    item: ItemRead


class TaskReviewResult(BaseModel):
    review: TaskReviewRead
    task: TaskRead
    item: ItemRead


class ItemSignoffResult(BaseModel):
    item: ItemRead
    review: ItemReviewRead


class ItemDetail(BaseModel):
    item: ItemRead
    tasks: List[TaskRead]
    evidence: List[EvidenceRead]
    task_reviews: List[TaskReviewRead]
    item_reviews: List[ItemReviewRead]


# --- audit and report ----------------------------------------------------------
class AuditRead(BaseModel):
    id: UUID
    action: str
    entity_type: str
    entity_id: UUID
    actor: Optional[UserMini] = None
    before: Optional[Any] = None
    after: Optional[Any] = None
    created_at: datetime


class AuditPage(BaseModel):
    events: List[AuditRead]
    next_before: Optional[datetime] = None


class DepartmentTotals(BaseModel):
    department_id: Optional[UUID] = None
    name: str
    total: int = 0
    open: int = 0
    overdue: int = 0
    evidence_submitted: int = 0
    compliant: int = 0
    exempted: int = 0


class ReportTotals(BaseModel):
    total: int = 0
    open: int = 0
    not_started: int = 0
    in_progress: int = 0
    overdue: int = 0
    evidence_submitted: int = 0
    compliant: int = 0
    exempted: int = 0
    flagged: int = 0


class ReportOrg(BaseModel):
    id: UUID
    name: str


class ReportRead(BaseModel):
    organization: ReportOrg
    generated_at: datetime
    as_of: date
    generated_by: UserMini
    register_id: Optional[UUID] = None
    register_title: Optional[str] = None
    totals: ReportTotals
    by_department: List[DepartmentTotals]
    overdue_items: List[ItemRead]
    upcoming_items: List[ItemRead]
    flagged_items: List[ItemRead]
    items: List[ItemRead]


# Backwards-compatible names used by older imports.
ComplianceRegisterCreate = RegisterCreate
ComplianceRegisterRead = RegisterRead
ComplianceItemRead = ItemRead
ComplianceItemCreate = ItemCreate
ComplianceTaskRead = TaskRead
ComplianceTaskCreate = TaskCreate
TaskEvidenceRead = EvidenceRead
