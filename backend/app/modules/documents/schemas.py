from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, computed_field


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

    @computed_field
    @property
    def is_synthetic(self) -> bool:
        title_lower = (self.title or "").lower()
        ref_lower = (self.reference_number or "").lower()
        if "sample" in title_lower or "brpd(p)" in ref_lower:
            return True
        if self.publication_status == "DRAFT" and len(self.versions) == 0:
            return True
        return False

    @computed_field
    @property
    def corpus_type(self) -> str:
        return "SYNTHETIC_SAMPLE" if self.is_synthetic else "GENUINE"

    model_config = ConfigDict(from_attributes=True)


class DashboardStatsRead(BaseModel):
    total_documents: int
    genuine_documents_count: int
    genuine_pages_count: int
    synthetic_documents_count: int
    synthetic_pages_count: int
    verified_publications_count: int
    awaiting_review_count: int
    draft_documents_count: int
    total_pages_extracted: int
    departments_monitored_count: int
    departments_codes: List[str] = []
    primary_authority: str
    source_monitoring_status: str
    source_monitoring_message: str


class DocumentUploadResponse(BaseModel):
    document: DocumentRead
    version: DocumentVersionRead
    pages_extracted: int
    message: str
