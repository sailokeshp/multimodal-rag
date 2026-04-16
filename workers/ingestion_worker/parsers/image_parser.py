"""
Image parser: metadata extraction, thumbnail generation, OCR decision.
Requires: Pillow
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

THUMBNAIL_SIZE = (512, 512)
TEXT_LIKELY_MIN_ASPECT = 0.3   # tall or wide images likely contain text


@dataclass
class ImageParseResult:
    width: int
    height: int
    format: str
    thumbnail_bytes: bytes
    text_likely: bool   # heuristic for OCR decision


def parse_image(file_bytes: bytes) -> ImageParseResult:
    """
    Load image, generate thumbnail, decide if OCR is likely useful.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(file_bytes))
    width, height = img.size
    fmt = img.format or "UNKNOWN"

    # Generate thumbnail
    thumb = img.copy()
    thumb.thumbnail(THUMBNAIL_SIZE)
    thumb_buf = io.BytesIO()
    thumb.save(thumb_buf, format="JPEG", quality=85)
    thumbnail_bytes = thumb_buf.getvalue()

    # Heuristic: documents/screenshots tend to be taller-than-wide or close to square
    aspect = width / max(height, 1)
    text_likely = aspect < 2.0  # wide panorama images rarely contain structured text

    logger.debug("Image parsed: %dx%d fmt=%s text_likely=%s", width, height, fmt, text_likely)
    return ImageParseResult(
        width=width,
        height=height,
        format=fmt,
        thumbnail_bytes=thumbnail_bytes,
        text_likely=text_likely,
    )
