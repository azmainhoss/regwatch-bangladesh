import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from backend.app.core.config import settings
from backend.app.core.logging import logger

try:
    from bijoy2unicode import converter
    _bijoy = converter.Unicode()
except Exception:
    _bijoy = None


class ExtractionService:
    def __init__(self):
        # Configure tesseract if executable is present
        if Path(settings.TESSERACT_CMD).exists():
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

    @staticmethod
    def is_bijoy_encoded(text: str) -> bool:
        """
        Heuristic check for legacy Bijoy ANSI encoding in Bangla PDFs
        (commonly using ASCII symbols like Av, wK, Ges, cÖwZ etc.).
        """
        bijoy_markers = ["Av", "wK", "Ges", "cÖ", "hvi", "n‡e", "Kv‡Q"]
        count = sum(1 for m in bijoy_markers if m in text)
        return count >= 3

    @staticmethod
    def convert_bijoy_if_needed(text: str) -> Tuple[str, bool]:
        if _bijoy and ExtractionService.is_bijoy_encoded(text):
            try:
                converted = _bijoy.convert(text)
                return converted, True
            except Exception as e:
                logger.warning(f"Bijoy conversion error: {e}")
        return text, False

    def extract_document_pages(
        self,
        pdf_bytes: bytes,
        ocr_fallback: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Page-by-page extraction from PDF bytes.
        Returns a list of dicts:
        [{
            "page_number": int,
            "raw_text": str,
            "cleaned_text": str,
            "extraction_method": str,
            "ocr_confidence": float,
            "has_tables": bool,
            "extracted_tables": list,
        }]
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_result = []

        for page_idx in range(len(doc)):
            page_no = page_idx + 1
            page = doc[page_idx]
            
            # 1. Native text extraction via PyMuPDF
            native_text = page.get_text("text").strip()
            extraction_method = "PYMUPDF_NATIVE"
            ocr_conf = None

            # Detect if Bijoy encoded
            converted_text, was_bijoy = self.convert_bijoy_if_needed(native_text)
            if was_bijoy:
                extraction_method = "BIJOY_UNICODE_CONVERTED"
                final_text = converted_text
            else:
                final_text = native_text

            # 2. Check if page is essentially scanned (low or empty text)
            if len(final_text.strip()) < 30 and ocr_fallback:
                logger.debug(f"Page {page_no} has minimal text ({len(final_text)} chars); triggering OCR...")
                try:
                    pix = page.get_pixmap(dpi=200)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    
                    # Run OCR
                    # Use English or bilingual if configured
                    lang = settings.OCR_DEFAULT_LANG
                    ocr_data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
                    
                    # Calculate mean confidence of recognized non-empty words
                    confs = [float(c) for c in ocr_data["conf"] if float(c) >= 0]
                    ocr_conf = sum(confs) / len(confs) if confs else 0.0
                    
                    ocr_text = pytesseract.image_to_string(img, lang=lang).strip()
                    if len(ocr_text) > len(final_text):
                        final_text = ocr_text
                        extraction_method = "OCR_TESSERACT"
                except Exception as ocr_err:
                    logger.warning(f"OCR failed for page {page_no}: {ocr_err}")

            # 3. Table heuristic (lines with dashes/dividers, tab separation, or table keywords)
            has_tables = bool(
                re.search(r"(\-{4,}|\={4,}|Table\s+\d+|Annexure|Schedule)", final_text, re.IGNORECASE) or
                re.search(r"(\d+(\.\d+)?[\s\t]{2,}){2,}", final_text)
            )

            cleaned_text = re.sub(r"\n{3,}", "\n\n", final_text).strip()

            pages_result.append({
                "page_number": page_no,
                "raw_text": final_text,
                "cleaned_text": cleaned_text,
                "extraction_method": extraction_method,
                "ocr_confidence": ocr_conf,
                "has_tables": has_tables,
                "extracted_tables": []
            })

        doc.close()
        return pages_result


extraction_service = ExtractionService()
