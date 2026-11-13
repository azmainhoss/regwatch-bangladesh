from datetime import datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal[
    "ORG_ADMIN", "COMPLIANCE_HEAD", "COMPLIANCE_OFFICER", "DEPARTMENT_LEAD",
    "REVIEWER", "ANALYST", "AUDITOR", "VIEWER",
]
MemberStatus = Literal["ACTIVE", "INVITED", "SUSPENDED"]


class UserMini(BaseModel):
    id: UUID
    full_name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class DepartmentBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    head_user_id: Optional[UUID] = None

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required.")
        return v


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    head_user_id: Optional[UUID] = None


class DepartmentRead(DepartmentBase):
    id: UUID
    organization_id: UUID
    created_at: datetime
    head: Optional[UserMini] = None
    member_count: int = 0
    open_item_count: int = 0

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
    role: Role = "ANALYST"
    status: MemberStatus = "ACTIVE"


class OrganizationMemberCreate(OrganizationMemberBase):
    pass


class OrganizationMemberRead(OrganizationMemberBase):
    id: UUID
    organization_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemberRead(BaseModel):
    id: UUID
    organization_id: UUID
    user: UserMini
    role: str
    department_id: Optional[UUID] = None
    status: str
    created_at: datetime


class MemberByEmail(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: Role = "ANALYST"
    department_id: Optional[UUID] = None


class MemberUpdate(BaseModel):
    role: Optional[Role] = None
    department_id: Optional[UUID] = None
    status: Optional[Literal["ACTIVE", "SUSPENDED"]] = None


class MyOrg(BaseModel):
    id: UUID
    name: str
    entity_type: str
    role: str
    department_id: Optional[UUID] = None


class MeInOrg(BaseModel):
    membership: MemberRead
    permissions: Dict[str, bool]
