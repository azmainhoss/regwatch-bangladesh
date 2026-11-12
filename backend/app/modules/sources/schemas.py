from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_validator

from backend.app.modules.sources.url_policy import validate_source_url


def _check_base_url(value: Optional[str]) -> Optional[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return validate_source_url(value)


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
    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: Optional[str]) -> Optional[str]:
        return _check_base_url(value)


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    polling_frequency_minutes: Optional[int] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: Optional[str]) -> Optional[str]:
        return _check_base_url(value)


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
    outcome: Optional[str] = None
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
    language: Optional[str] = None
    publication_type: Optional[str] = "CIRCULAR"
    file_hash: Optional[str] = None
    file_size: Optional[int] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    fetched_at: Optional[datetime] = None
    retry_count: int = 0
    last_attempted_at: Optional[datetime] = None
    error_message: Optional[str] = None
    discovered_metadata: Dict[str, Any] = {}
    rejection_reason: Optional[str] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RejectDiscoveryRequest(BaseModel):
    reason: str


class SourceStatsResponse(BaseModel):
    source_id: UUID
    source_name: str
    is_active: bool
    total_discovered: int
    total_ingested: int
    total_pending: int
    total_duplicates: int
    total_failed: int
    department_breakdown: Dict[str, int]
    year_breakdown: Dict[str, int]
    language_breakdown: Dict[str, int]
    last_polled_at: Optional[datetime] = None
    last_successful_run_at: Optional[datetime] = None
    access_restriction_status: str


class BackfillRequest(BaseModel):
    batch_size: int = 10
    department: Optional[str] = None
    year: Optional[int] = None
    language: Optional[str] = None


class BackfillResponse(BaseModel):
    status: str
    message: str
    attempted: int
    successful: int
    duplicates: int
    failed: int
    ingested_documents: List[Dict[str, Any]] = []
