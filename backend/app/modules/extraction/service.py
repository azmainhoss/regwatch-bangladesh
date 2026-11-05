import io
import re
from typing import Any, Dict, List, Optional, Tuple
import fitz  # PyMuPDF

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.modules.extraction.ocr import ocr_manager
from backend.app.modules.extraction.tables import TableExtractor
from backend.app.modules.extraction.layout import LayoutAwareExtractor, DocumentLayout
from backend.app.modules.extraction.quality import ExtractionQualityAssessor, PageQualityMetric, DocumentCompletenessReport
from backend.app.modules.extraction.bijoy import BijoyConverter


class ExtractionService:
    def __init__(self):
        self.ocr_manager = ocr_manager
        self.table_extractor = TableExtractor()
        self.quality_assessor = ExtractionQualityAssessor()

    @staticmethod
    def is_bijoy_encoded(text: str) -> bool:
        return BijoyConverter.is_bijoy_encoded(text)

    @staticmethod
    def convert_bijoy_if_needed(text: str) -> Tuple[str, bool]:
        return BijoyConverter.convert_to_unicode(text)

    def extract_document_pages(
        self,
        pdf_bytes: bytes,
        ocr_fallback: bool = True,
        preferred_language: str = "auto"
    ) -> List[Dict[str, Any]]:
        """
        Extracts all pages from PDF bytes with multi-stage fallbacks:
        1. Native extraction (PyMuPDF).
        2. Bijoy conversion if ANSI encoding detected.
        3. OCR fallback if page is scanned or text density < threshold.
        4. Structured table extraction.
        5. Quality metric assessment.
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_result: List[Dict[str, Any]] = []

        for page_idx in range(len(doc)):
            page_no = page_idx + 1
            page = doc[page_idx]
            
            # Step 1: Native PDF text extraction
            native_text = page.get_text("text").strip()
            chosen_text = native_text
            extraction_method = "PYMUPDF_NATIVE"
            ocr_text: Optional[str] = None
            ocr_confidence: Optional[float] = None

            # Step 2: Bijoy detection and conversion
            converted_text, was_bijoy = BijoyConverter.convert_to_unicode(native_text)
            if was_bijoy:
                extraction_method = "BIJOY_UNICODE_CONVERTED"
                chosen_text = converted_text

            # Step 3: Determine if OCR is required
            # Trigger OCR if page is essentially blank (< 30 characters) or corrupted
            needs_ocr = (len(chosen_text.strip()) < 30) and ocr_fallback

            if needs_ocr:
                logger.debug(f"Page {page_no} has low character density ({len(chosen_text)} chars). Initiating OCR fallback...")
                ocr_result = self.ocr_manager.perform_page_ocr(
                    page=page,
                    language_hint=preferred_language
                )
                if ocr_result["success"] and len(ocr_result["ocr_text"].strip()) > len(chosen_text.strip()):
                    ocr_text = ocr_result["ocr_text"]
                    ocr_confidence = ocr_result["mean_confidence"]
                    chosen_text = ocr_text
                    extraction_method = "OCR_TESSERACT"
                elif ocr_result["ocr_text"]:
                    ocr_text = ocr_result["ocr_text"]
                    ocr_confidence = ocr_result["mean_confidence"]

            # Step 4: Table extraction
            extracted_tables = self.table_extractor.extract_tables_from_page(
                pdf_bytes=pdf_bytes,
                page_number=page_no,
                raw_page_text=chosen_text
            )
            has_tables = len(extracted_tables) > 0

            # Step 5: Cleaned text
            cleaned_text = re.sub(r"\n{3,}", "\n\n", chosen_text).strip()

            # Step 6: Quality Assessment
            metric = self.quality_assessor.assess_page(
                page_number=page_no,
                raw_text=chosen_text,
                extraction_method=extraction_method,
                ocr_confidence=ocr_confidence,
                has_tables=has_tables
            )

            pages_result.append({
                "page_number": page_no,
                "raw_text": chosen_text,
                "native_text": native_text,
                "ocr_text": ocr_text,
                "cleaned_text": cleaned_text,
                "extraction_method": extraction_method,
                "ocr_confidence": ocr_confidence,
                "has_tables": has_tables,
                "extracted_tables": extracted_tables,
                "quality_status": metric.status,
                "quality_score": metric.quality_score,
                "issues": metric.issues,
                "layout_hierarchy": {},
                "human_corrected_text": None,
                "is_human_corrected": False
            })

        doc.close()

        # Step 7: Parse Layout Hierarchy across all extracted pages
        try:
            doc_layout = LayoutAwareExtractor.parse_document_pages_layout(pages_result)
            layout_dict = doc_layout.model_dump()
            # Distribute clause hierarchy back to pages
            for p in pages_result:
                p_no = p["page_number"]
                page_clauses = [
                    c for c in layout_dict.get("clauses", []) if c.get("page_number") == p_no
                ]
                p["layout_hierarchy"] = {
                    "clauses": page_clauses,
                    "subject": layout_dict.get("subject"),
                    "annexures": [a for a in layout_dict.get("annexures", []) if a.get("page_number") == p_no]
                }
        except Exception as e:
            logger.warning(f"Failed to compute layout hierarchy: {e}")

        return pages_result

    def generate_document_report(
        self,
        extracted_pages: List[Dict[str, Any]]
    ) -> DocumentCompletenessReport:
        """
        Builds a complete quality and completeness report for all pages.
        """
        metrics: List[PageQualityMetric] = []
        total_tables = sum(len(p.get("extracted_tables", [])) for p in extracted_pages)

        for p in extracted_pages:
            metric = self.quality_assessor.assess_page(
                page_number=p["page_number"],
                raw_text=p["raw_text"],
                extraction_method=p["extraction_method"],
                ocr_confidence=p.get("ocr_confidence"),
                has_tables=p.get("has_tables", False)
            )
            metrics.append(metric)

        return self.quality_assessor.assess_document(
            page_metrics=metrics,
            tables_detected=total_tables,
            tables_extracted=total_tables
        )


extraction_service = ExtractionService()
