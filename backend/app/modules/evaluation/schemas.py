from datetime import date
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DocumentProvenance(BaseModel):
    filename: str
    provenance_type: str  # SYNTHETIC_BENCHMARK, GENUINE_REGULATORY_DOCUMENT
    authority: str = "Bangladesh Bank"
    department: str
    circular_number: Optional[str] = None
    publication_date: Optional[str] = None
    title: str
    page_count: int
    file_sha256: str
    source_url: Optional[str] = None
    acquisition_method: str = "SYNTHETIC_GENERATOR"  # SYNTHETIC_GENERATOR, MANUAL_DEPOSIT, AUTHORIZED_INGEST
    acquisition_date: Optional[str] = None
    manual_verification_level: str = "UNVERIFIED"  # UNVERIFIED, PARTIAL_HUMAN_CHECKED, GOLD_HUMAN_VERIFIED
    known_limitations: Optional[str] = None


class GroundTruthClause(BaseModel):
    clause_number: str
    parent_clause: Optional[str] = None
    heading: Optional[str] = None
    verbatim_text: str
    page_number: int


class GroundTruthTable(BaseModel):
    page_number: int
    table_index: int
    headers: List[str]
    row_count: int
    col_count: int
    cell_values: List[List[str]]
    financial_figures: List[str] = Field(default_factory=list)


class DocumentGroundTruth(BaseModel):
    provenance: DocumentProvenance
    ground_truth_pages: Dict[int, str] = Field(default_factory=dict)
    ground_truth_clauses: List[GroundTruthClause] = Field(default_factory=list)
    ground_truth_tables: List[GroundTruthTable] = Field(default_factory=list)
    effective_dates: List[str] = Field(default_factory=list)
    referenced_circulars: List[str] = Field(default_factory=list)


class ExtractionBenchmarkMetrics(BaseModel):
    document_filename: str
    provenance_type: str
    page_completeness_ratio: float
    text_accuracy_score: Optional[float] = None
    bengali_ocr_accuracy: Optional[float] = None
    english_ocr_accuracy: Optional[float] = None
    clause_number_recognition_rate: Optional[float] = None
    clause_hierarchy_accuracy: Optional[float] = None
    table_cell_accuracy: Optional[float] = None
    financial_figure_accuracy: Optional[float] = None
    date_reference_accuracy: Optional[float] = None
    status: str = "MEASURED"  # MEASURED, NOT_YET_ESTABLISHED
    status_reason: Optional[str] = None
