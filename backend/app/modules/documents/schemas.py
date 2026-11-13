from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
import json

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


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
    # One entry per line: {"text": str, "box_2d": [ymin, xmin, ymax, xmax]} on a 0-1000 page scale.
    line_boxes: Optional[List[Dict[str, Any]]] = None
    vision_attempts: int = 0
    vision_error: Optional[str] = None
    # The latest correction: who, when and why. Earlier ones stay in the page_corrections table.
    correction_reason: Optional[str] = None
    corrected_by_name: Optional[str] = None
    corrected_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("line_boxes", mode="before")
    @classmethod
    def _coerce_boxes(cls, value: Any) -> Optional[List[Dict[str, Any]]]:
        value = _decode_json_text(value)
        return value if isinstance(value, list) else None

    @field_validator("extracted_tables", mode="before")
    @classmethod
    def _coerce_tables(cls, value: Any) -> List[Any]:
        return as_table_list(value)

    @field_validator("layout_hierarchy", mode="before")
    @classmethod
    def _coerce_layout(cls, value: Any) -> Dict[str, Any]:
        value = _decode_json_text(value)
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            # Older extractions stored the outline as a bare list of headings.
            return {"blocks": value}
        return {}


def _decode_json_text(value: Any) -> Any:
    """Pages imported from older seed files can hold JSON as a string; decode it."""
    if isinstance(value, (str, bytes)):
        text = value.strip() if isinstance(value, str) else value.decode("utf-8", "ignore").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None
    return value


def as_table_list(value: Any) -> List[Any]:
    """A page's extracted tables as a list, whatever form they were stored in."""
    value = _decode_json_text(value)
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return value if isinstance(value, list) else []


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
    status: Optional[str] = "CURRENT"
    source_url: Optional[str] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    fetched_at: Optional[datetime] = None
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
    owner_user_id: Optional[UUID] = None
    is_synthetic_fixture: Optional[bool] = Field(default=False, exclude=True)
    # IN_FORCE, AMENDED, REPLACED or REPEALED, from confirmed links only. None where it was not worked out
    # (for example right after an upload). The circular that changed this one is named next to it.
    in_force_status: Optional[str] = None
    in_force_by_id: Optional[UUID] = None
    in_force_by_reference: Optional[str] = None

    @computed_field
    @property
    def is_synthetic(self) -> bool:
        from backend.app.modules.documents.synthetic import is_synthetic_document
        return is_synthetic_document(
            self.title,
            self.reference_number,
            flag=self.is_synthetic_fixture,
            status=self.publication_status,
            version_count=len(self.versions),
        )

    @computed_field
    @property
    def is_private(self) -> bool:
        return self.owner_user_id is not None

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
    already_in_library: bool = False


class SearchSnippet(BaseModel):
    """A short piece of a page's stored text around the search words. `text` is an exact substring of the page."""
    page_number: int
    version_id: UUID
    language: str = "en"
    text: str
    # [start, end) of each search word inside `text`, counted in UTF-16 units (what a browser slices with).
    matches: List[List[int]] = []
    starts_mid_text: bool = False
    ends_mid_text: bool = False


class SearchHit(BaseModel):
    document_id: UUID
    reference_number: Optional[str] = None
    title: str
    title_bn: Optional[str] = None
    publication_date: date
    publication_status: str
    document_type: str
    department_code: Optional[str] = None
    current_version_id: Optional[UUID] = None
    is_private: bool = False
    title_match: bool = False
    matching_pages: int = 0
    snippets: List[SearchSnippet] = []


class SearchResponse(BaseModel):
    query: str
    terms: List[str] = []
    total: int
    limit: int
    offset: int
    results: List[SearchHit] = []


class CompareSide(BaseModel):
    version_id: UUID
    document_id: UUID
    reference_number: Optional[str] = None
    title: str
    version_number: int
    language: str = "en"
    page_count: int = 0
    pages_compared: int = 0


class CompareWord(BaseModel):
    op: str  # equal, insert or delete
    text: str


class CompareOp(BaseModel):
    op: str  # equal, insert, delete or replace
    left_text: Optional[str] = None
    right_text: Optional[str] = None
    left_page: Optional[int] = None
    right_page: Optional[int] = None
    words: List[CompareWord] = []


class ComparePageSummary(BaseModel):
    left_page: Optional[int] = None
    right_page: Optional[int] = None
    inserted: int = 0
    deleted: int = 0
    changed: int = 0
    unchanged: int = 0


class CompareStats(BaseModel):
    equal: int = 0
    insert: int = 0
    delete: int = 0
    replace: int = 0


class CompareResponse(BaseModel):
    left: CompareSide
    right: CompareSide
    truncated: bool = False
    stats: CompareStats
    pages: List[ComparePageSummary] = []
    ops: List[CompareOp] = []
