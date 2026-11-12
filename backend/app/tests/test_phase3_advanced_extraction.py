from pathlib import Path
import pytest
import pymupdf as fitz

from backend.app.modules.extraction.service import extraction_service
from backend.app.modules.extraction.tables import TableExtractor
from backend.app.modules.extraction.layout import LayoutAwareExtractor
from backend.app.modules.extraction.quality import ExtractionQualityAssessor
from backend.app.tests.fixtures.gold_corpus_manifest import GOLD_CORPUS_MANIFEST

CORPUS_DIR = Path("backend/app/tests/fixtures/corpus")


def test_native_digital_extraction_and_clause_hierarchy():
    """Tests native digital PDF extraction, verifying clause hierarchy and table extraction."""
    pdf_path = CORPUS_DIR / "gold_en_digital_master_policy.pdf"
    assert pdf_path.exists(), f"Fixture missing: {pdf_path}"

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    pages = extraction_service.extract_document_pages(pdf_bytes)
    assert len(pages) == 2, "Expected 2 pages"

    # Page 1: Native digital text
    p1 = pages[0]
    assert p1["extraction_method"] == "TEXT_LAYER"
    assert "BRPD Circular No. 15" in p1["raw_text"]
    assert "Mandatory Staging Framework" in p1["raw_text"]
    assert p1["quality_status"] == "SUCCESS_NATIVE"
    assert p1["quality_score"] >= 0.85

    # Check Clause Hierarchy
    hierarchy = p1.get("layout_hierarchy", {})
    clauses = hierarchy.get("clauses", [])
    assert len(clauses) > 0, "Hierarchical clauses must be detected"
    
    # Check clause numbers
    clause_nums = [c["clause_number"] for c in clauses]
    assert "1." in clause_nums or any("1" in num for num in clause_nums)

    # Page 2: Table Extraction
    p2 = pages[1]
    assert p2["has_tables"] is True
    assert len(p2["extracted_tables"]) >= 1
    table = p2["extracted_tables"][0]
    assert table["has_financial_data"] is True
    assert "headers" in table
    assert len(table["raw_rows"]) >= 3


def test_legacy_bijoy_page_goes_to_vision_queue():
    """A legacy Bijoy page is not converted locally: it waits for page-image reading, with no text."""
    pdf_bytes = (CORPUS_DIR / "gold_legacy_bijoy.pdf").read_bytes()
    pages = extraction_service.extract_document_pages(pdf_bytes)
    assert len(pages) == 1
    p1 = pages[0]
    assert p1["quality_status"] == "PENDING_VISION"
    assert p1["extraction_method"] == "GEMINI_VISION"
    assert p1["raw_text"] == ""
    assert p1["route_reason"] in ("legacy_bangla_font", "legacy_bangla_glyphs")


def test_scanned_pages_wait_for_vision_without_placeholder_text():
    """Image-only pages are never filled with placeholder text; they wait as PENDING_VISION."""
    for name in ("gold_scanned_english.pdf", "gold_scanned_bangla.pdf"):
        pdf_bytes = (CORPUS_DIR / name).read_bytes()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        assert len(doc[0].get_text("text").strip()) == 0, "Scanned fixture must have no text layer"
        doc.close()

        pages = extraction_service.extract_document_pages(pdf_bytes)
        assert len(pages) == 1
        p1 = pages[0]
        assert p1["quality_status"] == "PENDING_VISION"
        assert p1["route_reason"] == "near_empty"
        assert p1["raw_text"] == ""
        assert "Scanned document page" not in p1["cleaned_text"]


def test_table_heavy_regulatory_extraction():
    """Tests multi-table extraction with financial thresholds and capital adequacy metrics."""
    pdf_path = CORPUS_DIR / "gold_table_heavy_capital.pdf"
    assert pdf_path.exists(), f"Fixture missing: {pdf_path}"

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    pages = extraction_service.extract_document_pages(pdf_bytes)
    assert len(pages) == 1
    p1 = pages[0]
    assert p1["has_tables"] is True
    assert len(p1["extracted_tables"]) >= 2, "Expected 2 financial tables extracted"

    # Verify table 1 (Capital metrics)
    t1 = p1["extracted_tables"][0]
    assert t1["has_financial_data"] is True
    assert any("Common Equity" in str(row) or "CET1" in str(row) for row in t1["raw_rows"])

    # Verify table 2 (Penal sanctions)
    t2 = p1["extracted_tables"][1]
    assert any("Deficiency" in str(row) or "Dividend" in str(row) for row in t2["raw_rows"])


def test_document_completeness_report_and_quality_gates():
    """Tests document completeness reporting and risk-based human review triggering."""
    # Good native document: should not require human review
    good_pdf = CORPUS_DIR / "gold_en_digital_master_policy.pdf"
    with open(good_pdf, "rb") as f:
        pages = extraction_service.extract_document_pages(f.read())
    report = extraction_service.generate_document_report(pages)
    assert report.total_pages == 2
    assert report.extracted_pages == 2
    assert report.extraction_completion_percentage == 100.0
    assert report.requires_human_review is False

    # Empty page quality assessment
    empty_metric = ExtractionQualityAssessor.assess_page(
        page_number=1,
        raw_text="",
        extraction_method="TEXT_LAYER"
    )
    assert empty_metric.status == "EMPTY"
    assert empty_metric.quality_score == 0.0

    # Damaged text-layer page
    damaged_metric = ExtractionQualityAssessor.assess_page(
        page_number=2,
        raw_text="garbled ??? \ufffd\ufffd text",
        extraction_method="TEXT_LAYER",
    )
    assert damaged_metric.status in ("PARTIAL", "NEEDS_HUMAN_REVIEW")
    assert damaged_metric.quality_score < 0.65

    # A page waiting for page-image reading counts as not extracted yet
    pending = [dict(pages[0], raw_text="", quality_status="PENDING_VISION", extraction_method="GEMINI_VISION")]
    pending_report = extraction_service.generate_document_report(pending)
    assert pending_report.extracted_pages == 0
    assert pending_report.requires_human_review is True


def test_gold_corpus_manifest_integrity():
    """Verifies that all gold corpus manifest entries point to authentic or clearly labelled synthetic fixtures."""
    assert len(GOLD_CORPUS_MANIFEST) >= 5
    for entry in GOLD_CORPUS_MANIFEST:
        assert entry["provenance_type"] in ("SYNTHETIC_BENCHMARK", "AUTHENTIC_PUBLICATION")
        file_path = CORPUS_DIR / entry["filename"]
        assert file_path.exists(), f"Manifest file missing: {file_path}"
        assert entry["page_count"] > 0
        assert entry["language"] in ("en", "bn", "mixed")
