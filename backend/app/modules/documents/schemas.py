from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class DocumentPageRead(BaseModel):
    id: UUID
    page_number: int
    raw_text: str
    cleaned_text: Optional[str] = None
    extraction_method: str
    ocr_confidence: Optional[float] = None
    has_tables: bool
    extracted_tables: List[Any] = []
    quality_status: str = "SUCCESS_NATIVE"
    quality_score: float = 1.0
    layout_hierarchy: Dict[str, Any] = {}
    human_corrected_text: Optional[str] = None
    is_human_corrected: bool = False

    model_config = ConfigDict(from_attributes=True)


class PageCorrectionRequest(BaseModel):
    corrected_text: str
    correction_notes: Optional[str] = None


class DocumentVersionRead(BaseModel):
    id: UUID
    document_id: UUID
    version_number: int
    file_sha256: str
    file_size_bytes: int
    page_count: int
    language: str
    is_scanned: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentBase(BaseModel):
    institution_id: UUID
    department_id: Optional[UUID] = None
    reference_number: Optional[str] = None
    title: str
    title_bn: Optional[str] = None
    document_type: str = "CIRCULAR"
    publication_date: date
    effective_date: Optional[date] = None
    source_url: Optional[str] = None


class DocumentCreate(DocumentBase):
    pass


class DocumentRead(DocumentBase):
    id: UUID
    current_version_id: Optional[UUID] = None
    publication_status: str
    created_at: datetime
    updated_at: datetime
    versions: List[DocumentVersionRead] = []

    model_config = ConfigDict(from_attributes=True)


class DocumentUploadResponse(BaseModel):
    document: DocumentRead
    version: DocumentVersionRead
    pages_extracted: int
    message: str
