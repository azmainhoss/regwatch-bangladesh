from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class DepartmentBase(BaseModel):
    code: str
    name: str
    name_bn: Optional[str] = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentRead(DepartmentBase):
    id: UUID
    institution_id: UUID

    model_config = ConfigDict(from_attributes=True)


class InstitutionBase(BaseModel):
    code: str
    name: str
    name_bn: Optional[str] = None
    website_url: Optional[str] = None
    is_active: bool = True


class InstitutionCreate(InstitutionBase):
    pass


class InstitutionRead(InstitutionBase):
    id: UUID
    departments: List[DepartmentRead] = []

    model_config = ConfigDict(from_attributes=True)
