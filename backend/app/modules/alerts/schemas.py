from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentMini(BaseModel):
    id: UUID
    reference_number: Optional[str] = None
    title: str


class QuoteRead(BaseModel):
    text: str
    page_number: Optional[int] = None
    document_id: Optional[UUID] = None
    document_reference: Optional[str] = None


class AlertRead(BaseModel):
    id: UUID
    kind: str
    group: str
    severity: str
    organization_id: Optional[UUID] = None
    organization_name: Optional[str] = None
    title: str
    body: str
    detail: Optional[str] = None
    link: str
    document: Optional[DocumentMini] = None
    quote: Optional[QuoteRead] = None
    read_at: Optional[datetime] = None
    created_at: datetime


class SummaryRead(BaseModel):
    unread_count: int
    latest_id: Optional[str] = None
    latest_created_at: Optional[datetime] = None
    email_configured: bool
    server_time: datetime


class AlertListRead(BaseModel):
    alerts: List[AlertRead]
    next_before: Optional[datetime] = None
    unread_count: int


class AlertChangeRead(BaseModel):
    alert: AlertRead
    unread_count: int


class ReadAllBody(BaseModel):
    up_to: datetime
    group: Optional[str] = None


class ReadAllRead(BaseModel):
    updated: int
    unread_count: int


class ChannelSetting(BaseModel):
    in_app: bool
    email: str


class GroupOption(BaseModel):
    id: str
    label: str
    description: str


class DepartmentOption(BaseModel):
    code: str
    name: str


class PreferenceOptions(BaseModel):
    groups: List[GroupOption]
    department_codes: List[DepartmentOption]
    document_types: List[str]


class PreferencesWrite(BaseModel):
    channels: Dict[str, ChannelSetting] = Field(default_factory=dict)
    email_enabled: bool = True
    library_department_codes: List[str] = Field(default_factory=list)
    library_document_types: List[str] = Field(default_factory=list)
    library_keywords: List[str] = Field(default_factory=list)
    lock_version: Optional[int] = None


class PreferencesRead(BaseModel):
    channels: Dict[str, ChannelSetting]
    email_enabled: bool
    library_department_codes: List[str]
    library_document_types: List[str]
    library_keywords: List[str]
    lock_version: int
    email_configured: bool
    due_soon_days: List[int]
    digest_time: str
    options: PreferenceOptions


class OutboxCounts(BaseModel):
    pending: int
    sending: int
    sent_24h: int
    failed: int
    expired: int


class EmailStatusRead(BaseModel):
    configured: bool
    host: Optional[str] = None
    port: Optional[int] = None
    tls_mode: str
    from_address: Optional[str] = None
    username_set: bool
    password_set: bool
    worker_running: bool
    outbox: OutboxCounts
    last_error: Optional[str] = None


class TestEmailRead(BaseModel):
    ok: bool
    outcome: str
    smtp_code: Optional[int] = None
    detail: str


class OutboxRowRead(BaseModel):
    id: UUID
    kind: str
    status: str
    attempts: int
    next_attempt_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    to_masked: str


class OutboxListRead(BaseModel):
    rows: List[OutboxRowRead]
