from pathlib import Path
import pytest
from backend.app.modules.extraction.service import ExtractionService


def test_page_by_page_extraction_on_corpus():
    pdf_path = Path("backend/app/tests/fixtures/corpus/bb_brpd_2024_15.pdf")
    assert pdf_path.exists()
    
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    service = ExtractionService()
    pages = service.extract_document_pages(pdf_bytes)

    # BRPD 15 has exactly 2 pages
    assert len(pages) == 2

    # Check page 1
    p1 = pages[0]
    assert p1["page_number"] == 1
    assert "BANGLADESH BANK" in p1["raw_text"]
    assert "BRPD Circular No. 15" in p1["raw_text"]
    assert "IFRS 9" in p1["raw_text"]
    assert p1["extraction_method"] == "TEXT_LAYER"
    assert p1["quality_status"] == "SUCCESS_NATIVE"
    assert p1["line_boxes"], "text-layer pages carry one box per line"

    # Check page 2
    p2 = pages[1]
    assert p2["page_number"] == 2
    assert "Annexure: Reporting Template" in p2["raw_text"]
    assert "Bank Company Act, 1991" in p2["raw_text"]
    assert p2["has_tables"] is True

