import gc
import re
from typing import Any, Dict, List

import pymupdf as fitz

from backend.app.core.logging import logger
from backend.app.modules.extraction.layout import LayoutAwareExtractor
from backend.app.modules.extraction.page_router import TEXT_LAYER, PageRoute, route_page
from backend.app.modules.extraction.quality import DocumentCompletenessReport, ExtractionQualityAssessor, PageQualityMetric
from backend.app.modules.extraction.tables import TableExtractor

# extraction_method values
METHOD_TEXT_LAYER = "TEXT_LAYER"
METHOD_VISION = "GEMINI_VISION"
METHOD_MANUAL = "MANUAL_SUBSCRIPTION_READING"
METHOD_HUMAN = "HUMAN_CORRECTED"

# quality_status values
STATUS_NATIVE = "SUCCESS_NATIVE"
STATUS_VISION = "SUCCESS_VISION"
STATUS_VISION_MANUAL = "SUCCESS_VISION_MANUAL"
STATUS_PENDING_VISION = "PENDING_VISION"
STATUS_NEEDS_REVIEW = "NEEDS_HUMAN_REVIEW"

# Pages whose text came from reading the page image (by the API or by hand).
VISION_DONE_STATUSES = (STATUS_VISION, STATUS_VISION_MANUAL)


class ExtractionService:
    def __init__(self):
        self.table_extractor = TableExtractor()
        self.quality_assessor = ExtractionQualityAssessor()

    def route_document_pages(self, pdf_bytes: bytes) -> List[PageRoute]:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            return [route_page(doc[i]) for i in range(len(doc))]

    def extract_document_pages(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Reads every page of a PDF, choosing the method per page from its fonts and text:
        - clean English text layer: PyMuPDF text, method TEXT_LAYER, status SUCCESS_NATIVE
          (NEEDS_HUMAN_REVIEW when the text looks damaged), with one box per line;
        - Bangla, legacy-font, broken or scanned page: left empty with status PENDING_VISION
          for the background page-image job (vision_jobs). Never filled with placeholder text.
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_result: List[Dict[str, Any]] = []
        try:
            for page_idx in range(len(doc)):
                page_no = page_idx + 1
                page = doc[page_idx]
                route = route_page(page)
                native_text = route.text.strip()

                if route.route != TEXT_LAYER:
                    logger.debug(f"Page {page_no}: {route.reason} (fonts: {route.fonts[:4]}); queued for page-image reading.")
                    pages_result.append(self._pending_vision_page(page_no, native_text, route))
                    continue

                extracted_tables = self.table_extractor.extract_tables_from_page(
                    pdf_bytes=pdf_bytes,
                    page_number=page_no,
                    raw_page_text=native_text,
                    page=page
                )
                has_tables = len(extracted_tables) > 0
                cleaned_text = re.sub(r"\n{3,}", "\n\n", native_text).strip()
                metric = self.quality_assessor.assess_page(
                    page_number=page_no,
                    raw_text=native_text,
                    extraction_method=METHOD_TEXT_LAYER,
                    has_tables=has_tables
                )
                status = STATUS_NEEDS_REVIEW if metric.status == STATUS_NEEDS_REVIEW else STATUS_NATIVE

                pages_result.append({
                    "page_number": page_no,
                    "raw_text": native_text,
                    "native_text": native_text,
                    "ocr_text": None,
                    "cleaned_text": cleaned_text,
                    "extraction_method": METHOD_TEXT_LAYER,
                    "route_reason": route.reason,
                    "language": route.language,
                    "ocr_confidence": None,
                    "has_tables": has_tables,
                    "extracted_tables": extracted_tables,
                    "quality_status": status,
                    "quality_score": metric.quality_score,
                    "issues": metric.issues,
                    "line_boxes": route.line_boxes,
                    "layout_hierarchy": {},
                    "human_corrected_text": None,
                    "is_human_corrected": False
                })
        finally:
            doc.close()
            gc.collect()

        self._attach_layout(pages_result)
        return pages_result

    @staticmethod
    def _pending_vision_page(page_no: int, native_text: str, route: PageRoute) -> Dict[str, Any]:
        return {
            "page_number": page_no,
            "raw_text": "",
            "native_text": native_text or None,
            "ocr_text": None,
            "cleaned_text": "",
            "extraction_method": METHOD_VISION,
            "route_reason": route.reason,
            "language": route.language,
            "ocr_confidence": None,
            "has_tables": False,
            "extracted_tables": [],
            "quality_status": STATUS_PENDING_VISION,
            "quality_score": 0.0,
            "issues": [f"Waiting for page-image reading ({route.reason})"],
            "line_boxes": None,
            "layout_hierarchy": {},
            "human_corrected_text": None,
            "is_human_corrected": False
        }

    @staticmethod
    def _attach_layout(pages_result: List[Dict[str, Any]]) -> None:
        """Parses the clause hierarchy across all pages and hands each page its part."""
        try:
            doc_layout = LayoutAwareExtractor.parse_document_pages_layout(pages_result)
            layout_dict = doc_layout.model_dump()
            for p in pages_result:
                p_no = p["page_number"]
                p["layout_hierarchy"] = {
                    "clauses": [c for c in layout_dict.get("clauses", []) if c.get("page_number") == p_no],
                    "subject": layout_dict.get("subject"),
                    "annexures": [a for a in layout_dict.get("annexures", []) if a.get("page_number") == p_no]
                }
        except Exception as e:
            logger.warning(f"Failed to compute layout hierarchy: {e}")

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
            if p.get("quality_status") == STATUS_PENDING_VISION:
                metric.status = STATUS_PENDING_VISION
            metrics.append(metric)

        return self.quality_assessor.assess_document(
            page_metrics=metrics,
            tables_detected=total_tables,
            tables_extracted=total_tables
        )


extraction_service = ExtractionService()
