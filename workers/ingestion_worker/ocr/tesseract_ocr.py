"""
Tesseract OCR adapter.
Requires: pytesseract, Pillow, and system Tesseract binary.
Install: brew install tesseract  /  apt-get install tesseract-ocr
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)


def run_ocr(image_bytes: bytes) -> str:
    """
    Run Tesseract OCR on raw image bytes.
    Returns extracted text or empty string on failure.
    """
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img, lang="eng")
        cleaned = text.strip()
        logger.debug("Tesseract OCR: extracted %d chars", len(cleaned))
        return cleaned
    except ImportError:
        logger.warning("pytesseract not installed — OCR skipped. Run: pip install pytesseract")
        return ""
    except Exception as exc:
        logger.error("Tesseract OCR failed: %s", exc, exc_info=True)
        return ""


def ocr_needed(text: str, min_chars: int = 50) -> bool:
    """Return True if the extracted text is too sparse to be useful."""
    return len(text.strip()) < min_chars
