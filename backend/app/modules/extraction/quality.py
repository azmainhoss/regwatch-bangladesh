import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PageQualityMetric(BaseModel):
    page_number: int
    char_count: int
    word_count: int
    printable_ratio: float
    replacement_char_count: int
    garbled_char_count: int
    detected_language: str
    ocr_confidence: Optional[float] = None
    extraction_method: str
    status: str
    quality_score: float
    issues: List[str] = Field(default_factory=list)


class DocumentCompletenessReport(BaseModel):
    total_pages: int
    extracted_pages: int
    ocr_processed_pages: int
    empty_pages: int
    failed_pages: int
    low_confidence_pages: int
    missing_page_numbers: List[int] = Field(default_factory=list)
    duplicate_page_numbers: List[int] = Field(default_factory=list)
    tables_detected: int
    tables_extracted: int
    primary_language: str
    overall_quality_score: float
    extraction_completion_percentage: float
    requires_human_review: bool
    page_metrics: List[PageQualityMetric] = Field(default_factory=list)
    quality_summary: str


class ExtractionQualityAssessor:
    """
    Computes deterministic page-level and document-level quality scores
    for regulatory text extractions.
    """

    REPLACEMENT_CHARS_PATTERN = re.compile(r"[\ufffd\u25a1\u0000-\u0008\u000b\u000c\u000e-\u001f]")
    GARBLED_PUNCT_PATTERN = re.compile(r"([^\w\s\.\,\;\:\-\(\)\'\"]{3,})")

    @classmethod
    def assess_page(
        cls,
        page_number: int,
        raw_text: str,
        extraction_method: str,
        ocr_confidence: Optional[float] = None,
        has_tables: bool = False
    ) -> PageQualityMetric:
        issues: List[str] = []
        text = raw_text.strip()
        char_count = len(text)
        word_count = len(text.split())

        # 1. Empty Check
        if char_count == 0:
            return PageQualityMetric(
                page_number=page_number,
                char_count=0,
                word_count=0,
                printable_ratio=0.0,
                replacement_char_count=0,
                garbled_char_count=0,
                detected_language="unknown",
                ocr_confidence=ocr_confidence,
                extraction_method=extraction_method,
                status="EMPTY",
                quality_score=0.0,
                issues=["Page is completely blank or no text extracted"]
            )

        # 2. Language Detection
        bangla_chars = sum(1 for c in text if 0x0980 <= ord(c) <= 0x09FF)
        english_chars = sum(1 for c in text if c.isalpha() and ord(c) < 128)
        
        if bangla_chars > 0 and english_chars > 0:
            detected_lang = "mixed"
        elif bangla_chars > 0:
            detected_lang = "bn"
        elif english_chars > 0:
            detected_lang = "en"
        else:
            detected_lang = "unknown"

        # 3. Artifact & Garbled Character Count
        rep_matches = cls.REPLACEMENT_CHARS_PATTERN.findall(text)
        rep_count = len(rep_matches)
        if rep_count > 0:
            issues.append(f"Found {rep_count} replacement/control characters")

        garbled_matches = cls.GARBLED_PUNCT_PATTERN.findall(text)
        garbled_count = sum(len(g) for g in garbled_matches)
        if garbled_count > 5:
            issues.append(f"High frequency of garbled symbols ({garbled_count})")

        # 4. Printable ratio
        printable_count = sum(1 for c in text if c.isprintable() or c in ("\n", "\r", "\t"))
        printable_ratio = round(printable_count / max(char_count, 1), 4)

        # 5. Compute deterministic quality score (0.0 to 1.0)
        density_factor = min(word_count / 50.0, 1.0)  # expect at least 50 words on a normal page
        penalty = min((rep_count + garbled_count) / 20.0, 0.4)
        
        if extraction_method == "OCR_TESSERACT" and ocr_confidence is not None:
            base_score = (printable_ratio * 0.35) + (density_factor * 0.35) + (ocr_confidence * 0.30) - penalty
        else:
            base_score = (printable_ratio * 0.50) + (density_factor * 0.50) - penalty

        quality_score = max(0.0, min(1.0, round(base_score, 4)))

        # 6. Status Determination
        if extraction_method == "BIJOY_UNICODE_CONVERTED":
            status = "SUCCESS_NORMALIZED"
        elif extraction_method == "OCR_TESSERACT":
            if ocr_confidence is not None and ocr_confidence < 0.60:
                status = "LOW_CONFIDENCE"
                issues.append(f"Low OCR confidence ({ocr_confidence:.2f})")
            else:
                status = "SUCCESS_OCR"
        elif quality_score >= 0.80 and word_count >= 30:
            status = "SUCCESS_NATIVE"
        elif word_count < 30 and not has_tables:
            status = "PARTIAL"
            issues.append(f"Minimal text density ({word_count} words)")
        elif rep_count > 10 or garbled_count > 15:
            status = "NEEDS_HUMAN_REVIEW"
        else:
            status = "SUCCESS_NATIVE"

        if quality_score < 0.65 and status not in ("LOW_CONFIDENCE", "EMPTY"):
            status = "NEEDS_HUMAN_REVIEW"

        return PageQualityMetric(
            page_number=page_number,
            char_count=char_count,
            word_count=word_count,
            printable_ratio=printable_ratio,
            replacement_char_count=rep_count,
            garbled_char_count=garbled_count,
            detected_language=detected_lang,
            ocr_confidence=ocr_confidence,
            extraction_method=extraction_method,
            status=status,
            quality_score=quality_score,
            issues=issues
        )

    @classmethod
    def assess_document(
        cls,
        page_metrics: List[PageQualityMetric],
        tables_detected: int = 0,
        tables_extracted: int = 0
    ) -> DocumentCompletenessReport:
        total_pages = len(page_metrics)
        if total_pages == 0:
            return DocumentCompletenessReport(
                total_pages=0,
                extracted_pages=0,
                ocr_processed_pages=0,
                empty_pages=0,
                failed_pages=0,
                low_confidence_pages=0,
                tables_detected=0,
                tables_extracted=0,
                primary_language="unknown",
                overall_quality_score=0.0,
                extraction_completion_percentage=0.0,
                requires_human_review=True,
                page_metrics=[],
                quality_summary="Document has no pages."
            )

        empty_pages = sum(1 for p in page_metrics if p.status == "EMPTY")
        ocr_pages = sum(1 for p in page_metrics if p.extraction_method == "OCR_TESSERACT")
        low_conf_pages = sum(1 for p in page_metrics if p.status in ("LOW_CONFIDENCE", "NEEDS_HUMAN_REVIEW"))
        failed_pages = sum(1 for p in page_metrics if p.status == "FAILED")
        extracted_pages = total_pages - empty_pages - failed_pages

        # Check page continuity and duplicates
        seen_pages = set()
        duplicate_pages = []
        page_numbers = []
        for p in page_metrics:
            p_no = p.page_number
            if p_no in seen_pages:
                duplicate_pages.append(p_no)
            seen_pages.add(p_no)
            page_numbers.append(p_no)

        missing_pages = []
        if page_numbers:
            min_p = min(page_numbers)
            max_p = max(page_numbers)
            expected_set = set(range(min_p, max_p + 1))
            missing_pages = sorted(list(expected_set - seen_pages))

        avg_score = round(sum(p.quality_score for p in page_metrics) / total_pages, 4)
        completion_pct = round((extracted_pages / total_pages) * 100.0, 1)

        # Primary language
        langs = [p.detected_language for p in page_metrics if p.detected_language != "unknown"]
        if langs:
            primary_lang = max(set(langs), key=langs.count)
        else:
            primary_lang = "unknown"

        # Review requirement
        requires_review = (
            completion_pct < 90.0 or
            low_conf_pages > 0 or
            failed_pages > 0 or
            avg_score < 0.75 or
            len(missing_pages) > 0 or
            len(duplicate_pages) > 0
        )

        summary = (
            f"{extracted_pages}/{total_pages} pages extracted ({completion_pct}%). "
            f"Average quality score: {avg_score:.2f}. "
            f"Language: {primary_lang}. "
            f"{f'Missing pages: {missing_pages}. ' if missing_pages else ''}"
            f"{f'Duplicate pages: {duplicate_pages}. ' if duplicate_pages else ''}"
            f"{'Flagged for human review' if requires_review else 'Passed quality gate'}."
        )

        return DocumentCompletenessReport(
            total_pages=total_pages,
            extracted_pages=extracted_pages,
            ocr_processed_pages=ocr_pages,
            empty_pages=empty_pages,
            failed_pages=failed_pages,
            low_confidence_pages=low_conf_pages,
            missing_page_numbers=missing_pages,
            duplicate_page_numbers=duplicate_pages,
            tables_detected=tables_detected,
            tables_extracted=tables_extracted,
            primary_language=primary_lang,
            overall_quality_score=avg_score,
            extraction_completion_percentage=completion_pct,
            requires_human_review=requires_review,
            page_metrics=page_metrics,
            quality_summary=summary
        )
