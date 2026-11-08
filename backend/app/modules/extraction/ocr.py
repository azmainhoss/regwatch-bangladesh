import io
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pymupdf as fitz
from PIL import Image
import pytesseract

from backend.app.core.config import settings
from backend.app.core.logging import logger


class MissingTrainedDataError(RuntimeError):
    """Raised when required Tesseract OCR language traineddata is missing from the environment."""
    pass


def get_container_available_memory_mb() -> float:
    """Returns available memory in MB respecting Linux cgroups (Docker/Render) limits."""
    # Check cgroup v2
    try:
        max_path = Path("/sys/fs/cgroup/memory.max")
        curr_path = Path("/sys/fs/cgroup/memory.current")
        if max_path.exists() and curr_path.exists():
            max_str = max_path.read_text().strip()
            if max_str != "max":
                limit_bytes = int(max_str)
                curr_bytes = int(curr_path.read_text().strip())
                return max(0.0, (limit_bytes - curr_bytes) / (1024 * 1024))
    except Exception:
        pass

    # Check cgroup v1
    try:
        lim_path = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
        use_path = Path("/sys/fs/cgroup/memory/memory.usage_in_bytes")
        if lim_path.exists() and use_path.exists():
            limit_bytes = int(lim_path.read_text().strip())
            curr_bytes = int(use_path.read_text().strip())
            if limit_bytes < 100 * 1024 * 1024 * 1024:
                return max(0.0, (limit_bytes - curr_bytes) / (1024 * 1024))
    except Exception:
        pass

    # Fallback to psutil
    try:
        import psutil
        return psutil.virtual_memory().available / (1024 * 1024)
    except Exception:
        return 512.0


class OCRManager:
    def __init__(self):
        self._initialized = False
        self._available_languages: List[str] = []
        self._setup_tesseract()

    def _setup_tesseract(self) -> None:
        # Check Tesseract binary
        tess_bin = settings.TESSERACT_CMD
        if Path(tess_bin).exists():
            pytesseract.pytesseract.tesseract_cmd = tess_bin
        elif Path("/usr/bin/tesseract").exists():
            pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

        # Check TESSDATA_PREFIX candidates
        project_root = Path(__file__).resolve().parents[4]
        candidate_tessdata = [
            project_root / "data" / "tessdata",
            Path(settings.TESSDATA_PREFIX) if settings.TESSDATA_PREFIX else None,
            Path("/opt/homebrew/share/tessdata"),
            Path("/usr/share/tesseract-ocr/5/tessdata"),
            Path("/usr/share/tesseract-ocr/4.00/tessdata"),
            Path("/usr/share/tessdata"),
        ]

        for p in candidate_tessdata:
            if p and p.exists() and (p / "eng.traineddata").exists():
                os.environ["TESSDATA_PREFIX"] = str(p)
                logger.info(f"Tesseract tessdata directory configured at: {p}")
                break

        try:
            self._available_languages = pytesseract.get_languages()
            self._initialized = True
            logger.info(f"Tesseract OCR initialized. Available languages: {self._available_languages}")
        except Exception as e:
            logger.warning(f"Tesseract initialization check encountered issue: {e}")
            self._available_languages = ["eng"]

    @property
    def has_bengali_support(self) -> bool:
        return "ben" in self._available_languages

    @property
    def has_english_support(self) -> bool:
        return "eng" in self._available_languages

    def select_ocr_language(self, hint: str = "auto", strict: bool = False) -> str:
        """
        Determines the optimal OCR language configuration.
        hint: 'en', 'bn', 'mixed', or 'auto'
        If strict=True, raises MissingTrainedDataError if the requested language is unavailable.
        """
        has_ben = self.has_bengali_support
        has_eng = self.has_english_support

        if hint == "bn":
            if not has_ben:
                if strict:
                    raise MissingTrainedDataError(
                        "Bengali OCR language data ('ben.traineddata') is missing from Tesseract tessdata."
                    )
                logger.warning("Bengali OCR requested but 'ben' traineddata missing; falling back to English.")
                return "eng" if has_eng else settings.OCR_DEFAULT_LANG
            return "ben"

        if hint == "en":
            if not has_eng:
                if strict:
                    raise MissingTrainedDataError(
                        "English OCR language data ('eng.traineddata') is missing from Tesseract tessdata."
                    )
            return "eng"

        if hint in ("mixed", "auto"):
            if has_ben and has_eng:
                return "ben+eng"
            if has_ben:
                return "ben"
            if has_eng:
                return "eng"

        if strict and hint not in self._available_languages:
            raise MissingTrainedDataError(f"Requested OCR language '{hint}' is not available in Tesseract tessdata.")

        return settings.OCR_DEFAULT_LANG

    def render_page_to_image(self, page: fitz.Page, dpi: int = 200) -> Image.Image:
        """Renders a PyMuPDF PDF page into a PIL Image."""
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return Image.open(io.BytesIO(pix.tobytes("png")))

    def perform_page_ocr(
        self,
        page: fitz.Page,
        language_hint: str = "auto",
        dpi: int = 140
    ) -> Dict[str, Any]:
        """
        Executes memory-efficient OCR on a single PDF page.
        Returns:
        {
            "ocr_text": str,
            "mean_confidence": float (0.0 to 1.0),
            "word_confidences": List[float],
            "language_used": str,
            "success": bool,
            "error": Optional[str]
        }
        """
        lang = self.select_ocr_language(language_hint)
        # Memory constraint safeguard: skip heavy Tesseract in production container or if container has <300MB free RAM
        avail_mb = get_container_available_memory_mb()
        if getattr(settings, "ENVIRONMENT", "development") == "production" or avail_mb < 300.0:
            logger.warning(f"Skipping Tesseract OCR for page {page.number + 1}: memory safeguard active (available: {avail_mb:.1f}MB, environment: {getattr(settings, 'ENVIRONMENT', 'development')}).")
            return {
                "ocr_text": "",
                "mean_confidence": 0.0,
                "word_confidences": [],
                "language_used": lang,
                "success": False,
                "error": "Memory constrained; OCR deferred."
            }

        try:
            img = self.render_page_to_image(page, dpi=dpi)

            # Extract detailed word-level data to compute genuine confidence metrics
            ocr_data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
            confs = []
            extracted_words = []
            for text_val, conf_val in zip(ocr_data.get("text", []), ocr_data.get("conf", [])):
                try:
                    c_float = float(conf_val)
                    if c_float >= 0:
                        confs.append(c_float / 100.0)  # scale 0..1
                except (ValueError, TypeError):
                    continue
                if text_val and text_val.strip():
                    extracted_words.append(text_val.strip())

            mean_conf = float(sum(confs) / len(confs)) if confs else 0.0

            # Use words from data if present to avoid redundant second OCR pass, or fallback to string
            if extracted_words:
                ocr_text = " ".join(extracted_words)
            else:
                ocr_text = pytesseract.image_to_string(img, lang=lang).strip()

            return {
                "ocr_text": ocr_text,
                "mean_confidence": round(mean_conf, 4),
                "word_confidences": confs,
                "language_used": lang,
                "success": True,
                "error": None
            }
        except Exception as err:
            logger.error(f"OCR failed for page {page.number + 1}: {err}")
            return {
                "ocr_text": "",
                "mean_confidence": 0.0,
                "word_confidences": [],
                "language_used": lang,
                "success": False,
                "error": str(err)
            }


ocr_manager = OCRManager()
