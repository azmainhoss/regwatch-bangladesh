from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class SourceBase(BaseModel):
    institution_id: UUID
    department_id: Optional[UUID] = None
    name: str
    source_type: str = "WEB_CRAWLER"
    monitoring_method: str = "POLLING_HTTP"
    base_url: Optional[str] = None
    polling_frequency_minutes: int = 60
    config: Dict[str, Any] = {}
    is_active: bool = True


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    polling_frequency_minutes: Optional[int] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class SourceRead(SourceBase):
    id: UUID
    last_checked_at: Optional[datetime] = None
    last_attempted_run_at: Optional[datetime] = None
    last_successful_run_at: Optional[datetime] = None
    last_discovered_publication_at: Optional[datetime] = None
    last_error: Optional[str] = None
    access_restriction_status: str

    model_config = ConfigDict(from_attributes=True)


class SourceRunRead(BaseModel):
    id: UUID
    source_id: UUID
    run_type: str
    status: str
    discovered_count: int = 0
    downloaded_count: int = 0
    pages_inspected: int
    candidate_links_discovered: int
    valid_documents_discovered: int
    downloads_attempted: int
    downloads_successful: int
    duplicate_count: int
    access_restricted: bool
    access_restriction_details: Dict[str, Any] = {}
    retry_count: int
    error_count: int
    error_log: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SourceDiscoveryRead(BaseModel):
    id: UUID
    source_run_id: UUID
    document_id: Optional[UUID] = None
    source_url: str
    file_url: Optional[str] = None
    title: Optional[str] = None
    department_code: Optional[str] = None
    reference_number: Optional[str] = None
    publication_date: Optional[date] = None
    discovered_metadata: Dict[str, Any] = {}
    rejection_reason: Optional[str] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RejectDiscoveryRequest(BaseModel):
    reason: str
