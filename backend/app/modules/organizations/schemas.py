from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class DepartmentBase(BaseModel):
    name: str
    head_user_id: Optional[UUID] = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentRead(DepartmentBase):
    id: UUID
    organization_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationBase(BaseModel):
    name: str
    entity_type: str = "COMMERCIAL_BANK"
    registration_number: Optional[str] = None
    license_number: Optional[str] = None
    is_active: bool = True


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationRead(OrganizationBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationMemberBase(BaseModel):
    user_id: UUID
    department_id: Optional[UUID] = None
    role: str = "ANALYST"  # ORG_ADMIN, COMPLIANCE_HEAD, DEPARTMENT_LEAD, ANALYST, AUDITOR, VIEWER
    status: str = "ACTIVE"


class OrganizationMemberCreate(OrganizationMemberBase):
    pass


class OrganizationMemberRead(OrganizationMemberBase):
    id: UUID
    organization_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

