import io
from pathlib import Path
import pytest
import fitz
from PIL import Image

from backend.app.modules.extraction.service import extraction_service
from backend.app.modules.extraction.ocr import ocr_manager
from backend.app.modules.extraction.tables import TableExtractor
from backend.app.modules.extraction.layout import LayoutAwareExtractor
from backend.app.modules.extraction.quality import ExtractionQualityAssessor
from backend.app.modules.extraction.bijoy import BijoyConverter
from backend.app.tests.fixtures.gold_corpus_manifest import GOLD_CORPUS_MANIFEST

CORPUS_DIR = Path("backend/app/tests/fixtures/corpus")


def test_tesseract_ocr_dependency_and_bengali_support():
    """Verifies that Tesseract is available and configured with English and Bengali support."""
    assert ocr_manager.has_english_support, "English language support must be present"
    assert ocr_manager.has_bengali_support, "Bengali (ben) language pack must be present and configured"
    selected_lang = ocr_manager.select_ocr_language("bn")
    assert selected_lang == "ben"
    selected_mixed = ocr_manager.select_ocr_language("mixed")
    assert "ben" in selected_mixed and "eng" in selected_mixed


def test_native_digital_extraction_and_clause_hierarchy():
    """Tests native digital PDF extraction, verifying clause hierarchy and table extraction."""
    pdf_path = CORPUS_DIR / "gold_en_digital_master_policy.pdf"
    assert pdf_path.exists(), f"Fixture missing: {pdf_path}"

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    pages = extraction_service.extract_document_pages(pdf_bytes, ocr_fallback=True)
    assert len(pages) == 2, "Expected 2 pages"

    # Page 1: Native digital text
    p1 = pages[0]
    assert p1["extraction_method"] == "PYMUPDF_NATIVE"
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


def test_legacy_bijoy_conversion_on_gold_corpus():
    """Tests automatic detection and conversion of legacy ANSI Bijoy SutonnyMJ text."""
    pdf_path = CORPUS_DIR / "gold_legacy_bijoy.pdf"
    assert pdf_path.exists(), f"Fixture missing: {pdf_path}"

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    pages = extraction_service.extract_document_pages(pdf_bytes, ocr_fallback=True)
    assert len(pages) == 1
    p1 = pages[0]
    
    # Must be recognized as Bijoy converted
    assert p1["extraction_method"] == "BIJOY_UNICODE_CONVERTED"
    assert p1["quality_status"] == "SUCCESS_NORMALIZED"
    
    # Converted text should contain genuine Bengali Unicode characters
    converted_text = p1["raw_text"]
    has_unicode_bangla = any(0x0980 <= ord(c) <= 0x09FF for c in converted_text)
    assert has_unicode_bangla, "Converted text must contain Unicode Bengali characters"
    assert "বাংলাদেশ ব্যাংক" in converted_text or "বাংলাদেশ" in converted_text or "সার্কুলার" in converted_text


def test_scanned_english_pdf_ocr_execution():
    """Tests OCR fallback on a bitmap-only PDF with 0 native character streams."""
    pdf_path = CORPUS_DIR / "gold_scanned_english.pdf"
    assert pdf_path.exists(), f"Fixture missing: {pdf_path}"

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    # Verify that native PyMuPDF alone returns empty text
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    native_text = doc[0].get_text("text").strip()
    assert len(native_text) == 0, "Scanned PDF fixture must have 0 native characters"
    doc.close()

    # Now run extraction with OCR fallback
    pages = extraction_service.extract_document_pages(pdf_bytes, ocr_fallback=True, preferred_language="en")
    assert len(pages) == 1
    p1 = pages[0]
    
    assert p1["extraction_method"] == "OCR_TESSERACT"
    assert p1["ocr_confidence"] is not None and p1["ocr_confidence"] > 0.50
    assert "BANGLADESH BANK" in p1["raw_text"].upper()
    assert "CASH RESERVE" in p1["raw_text"].upper() or "SLR" in p1["raw_text"] or "LIQUIDITY" in p1["raw_text"].upper()


def test_scanned_bangla_pdf_bengali_ocr():
    """Tests OCR fallback on a Bengali image-only PDF using Tesseract 'ben' language data."""
    pdf_path = CORPUS_DIR / "gold_scanned_bangla.pdf"
    assert pdf_path.exists(), f"Fixture missing: {pdf_path}"

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    pages = extraction_service.extract_document_pages(pdf_bytes, ocr_fallback=True, preferred_language="bn")
    assert len(pages) == 1
    p1 = pages[0]

    assert p1["extraction_method"] == "OCR_TESSERACT"
    assert p1["ocr_confidence"] is not None
    # Verify Bengali characters are present in extracted OCR output
    has_bangla = any(0x0980 <= ord(c) <= 0x09FF for c in p1["raw_text"])
    assert has_bangla, "Bengali OCR must produce Unicode Bengali text"


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
        extraction_method="PYMUPDF_NATIVE"
    )
    assert empty_metric.status == "EMPTY"
    assert empty_metric.quality_score == 0.0

    # Low confidence OCR page
    low_conf_metric = ExtractionQualityAssessor.assess_page(
        page_number=2,
        raw_text="garbled ??? \ufffd\ufffd text",
        extraction_method="OCR_TESSERACT",
        ocr_confidence=0.42
    )
    assert low_conf_metric.status in ("LOW_CONFIDENCE", "NEEDS_HUMAN_REVIEW")
    assert low_conf_metric.quality_score < 0.65


def test_gold_corpus_manifest_integrity():
    """Verifies that all gold corpus manifest entries point to authentic or clearly labelled synthetic fixtures."""
    assert len(GOLD_CORPUS_MANIFEST) >= 5
    for entry in GOLD_CORPUS_MANIFEST:
        assert entry["provenance_type"] in ("SYNTHETIC_BENCHMARK", "AUTHENTIC_PUBLICATION")
        file_path = CORPUS_DIR / entry["filename"]
        assert file_path.exists(), f"Manifest file missing: {file_path}"
        assert entry["page_count"] > 0
        assert entry["language"] in ("en", "bn", "mixed")
