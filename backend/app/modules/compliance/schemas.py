from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class ComplianceRegisterBase(BaseModel):
    title: str
    description: Optional[str] = None
    is_active: bool = True


class ComplianceRegisterCreate(ComplianceRegisterBase):
    pass


class ComplianceRegisterRead(ComplianceRegisterBase):
    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ComplianceItemBase(BaseModel):
    register_id: UUID
    obligation_id: UUID
    internal_code: Optional[str] = None
    department_id: Optional[UUID] = None
    assigned_lead_id: Optional[UUID] = None
    status: str = "NOT_STARTED"
    internal_deadline: Optional[date] = None


class ComplianceItemCreate(ComplianceItemBase):
    pass


class ComplianceItemRead(ComplianceItemBase):
    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ComplianceTaskBase(BaseModel):
    compliance_item_id: UUID
    title: str
    description: Optional[str] = None
    assigned_to_user_id: Optional[UUID] = None
    due_date: date
    priority: str = "MEDIUM"
    status: str = "PENDING"


class ComplianceTaskCreate(ComplianceTaskBase):
    pass


class ComplianceTaskRead(ComplianceTaskBase):
    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskEvidenceRead(BaseModel):
    id: UUID
    task_id: UUID
    organization_id: UUID
    submitted_by_user_id: UUID
    file_sha256: str
    original_filename: str
    file_size_bytes: int
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskReviewCreate(BaseModel):
    decision: str  # APPROVED, CHANGES_REQUESTED, REJECTED
    comments: str


class TaskReviewRead(BaseModel):
    id: UUID
    task_id: UUID
    reviewer_user_id: UUID
    decision: str
    comments: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
