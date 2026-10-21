"""OCR for scanned PDF pages, via PyMuPDF's built-in Tesseract integration.

Tesseract is optional: the Docker image includes it; on other installs it is
used when present (`brew install tesseract`, `apt-get install tesseract-ocr`).
Everything runs locally — page images never leave the machine.

Settings (environment): OCR_ENABLED (default true), OCR_LANGUAGE (eng),
OCR_DPI (300), OCR_MAX_PAGES (100 per document).
"""

import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

OCR_ENABLED = os.getenv("OCR_ENABLED", "true").strip().lower() not in ("0", "false", "no")
OCR_LANGUAGE = os.getenv("OCR_LANGUAGE", "eng")
OCR_DPI = int(os.getenv("OCR_DPI", "300"))
OCR_MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "100"))
# A page with fewer extractable characters than this is treated as scanned.
MIN_TEXT_CHARS = 20

INSTALL_HINT = ("Install Tesseract OCR to index scanned documents "
                "(macOS: `brew install tesseract`; Debian/Ubuntu: `apt-get install tesseract-ocr`), "
                "or run the Docker image, which includes it.")


@lru_cache(maxsize=1)
def tessdata_path() -> Optional[str]:
    """Location of Tesseract's language data, or None when OCR isn't available."""
    if not OCR_ENABLED:
        return None
    try:
        import pymupdf
        path = pymupdf.get_tessdata()
    except Exception as e:  # Tesseract not installed / no language data found
        logger.info(f"OCR unavailable: {e}")
        return None
    if path and not os.path.exists(os.path.join(path, f"{OCR_LANGUAGE}.traineddata")):
        logger.warning(f"OCR unavailable: no '{OCR_LANGUAGE}' language data in {path}")
        return None
    return path


def ocr_available() -> bool:
    return tessdata_path() is not None


def ocr_page(page) -> str:
    """Recognise the text on one PyMuPDF page (raises if OCR is unavailable)."""
    path = tessdata_path()
    if path is None:
        raise RuntimeError("OCR is not available. " + INSTALL_HINT)
    textpage = page.get_textpage_ocr(language=OCR_LANGUAGE, dpi=OCR_DPI, full=True, tessdata=path)
    return page.get_text(textpage=textpage)
