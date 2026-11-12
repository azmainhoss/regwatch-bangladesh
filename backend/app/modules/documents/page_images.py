"""Page images for the source-page viewer.

A page of a stored PDF is rendered with PyMuPDF and kept on disk, keyed by document version,
page number and resolution, so each image is only drawn once. Quote boxes are stored on a
0-1000 scale of the page, so they line up with the image at any resolution.
"""
import io
import os
from pathlib import Path
from typing import Optional, Tuple

import pymupdf as fitz

from backend.app.core.config import settings
from backend.app.core.logging import logger

# Resolutions the viewer may ask for. Requests snap to the nearest one so the cache stays small.
ALLOWED_DPI = (96, 144, 192)
DEFAULT_DPI = 144
FORMATS = {"webp": "image/webp", "png": "image/png"}


class PageNotFound(Exception):
    """The PDF has no page with that number."""


def snap_dpi(dpi: Optional[int]) -> int:
    if not dpi:
        return DEFAULT_DPI
    return min(ALLOWED_DPI, key=lambda d: abs(d - dpi))


def cache_dir() -> Path:
    root = settings.PAGE_IMAGE_CACHE_DIR or os.path.join(settings.STORAGE_LOCAL_ROOT, "page_images")
    return Path(root).resolve()


def cache_path(version_id: str, page_number: int, dpi: int, fmt: str) -> Path:
    return cache_dir() / str(version_id) / f"p{page_number}-{dpi}.{fmt}"


def render_page_image(pdf_bytes: bytes, page_number: int, dpi: int, fmt: str) -> bytes:
    """Draws one 1-indexed page. WebP when Pillow can write it, otherwise PNG."""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        if page_number < 1 or page_number > len(doc):
            raise PageNotFound(page_number)
        pix = doc[page_number - 1].get_pixmap(dpi=dpi, alpha=False)
        if fmt == "png":
            return pix.tobytes("png")
        from PIL import Image

        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        out = io.BytesIO()
        img.save(out, format="WEBP", quality=82, method=4)
        return out.getvalue()


def get_page_image(
    version_id: str,
    page_number: int,
    dpi: int,
    fmt: str,
    load_pdf,
) -> Tuple[bytes, bool]:
    """Returns (image bytes, served from cache). `load_pdf` is called only on a cache miss."""
    path = cache_path(version_id, page_number, dpi, fmt)
    if path.is_file():
        try:
            return path.read_bytes(), True
        except OSError:
            pass
    data = render_page_image(load_pdf(), page_number, dpi, fmt)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except OSError as e:
        logger.warning(f"Could not cache page image {path}: {e}")
    return data, False
