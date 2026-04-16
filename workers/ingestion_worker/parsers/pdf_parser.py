"""
PDF parser: text extraction, page detection, inline image extraction.
Requires: pymupdf (fitz)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from io import BytesIO

logger = logging.getLogger(__name__)

MIN_TEXT_CHARS_PER_PAGE = 50  # below this, OCR is likely needed


@dataclass
class PageData:
    page_number: int
    text: str
    needs_ocr: bool
    image_bytes: list[bytes] = field(default_factory=list)  # inline images


@dataclass
class PDFParseResult:
    pages: list[PageData]
    page_count: int


def parse_pdf(file_bytes: bytes, max_pages: int = 300) -> PDFParseResult:
    """
    Extract text and inline images from a PDF.
    Marks pages that need OCR (too little extracted text).
    """
    import fitz  # pymupdf

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages: list[PageData] = []

    for page_index in range(min(len(doc), max_pages)):
        page = doc[page_index]
        text = page.get_text("text").strip()
        needs_ocr = len(text) < MIN_TEXT_CHARS_PER_PAGE

        inline_images: list[bytes] = []
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                inline_images.append(base_image["image"])
            except Exception as exc:
                logger.debug("Could not extract inline image xref=%d: %s", xref, exc)

        pages.append(
            PageData(
                page_number=page_index + 1,
                text=text,
                needs_ocr=needs_ocr,
                image_bytes=inline_images,
            )
        )
        logger.debug(
            "PDF page %d: chars=%d needs_ocr=%s inline_images=%d",
            page_index + 1, len(text), needs_ocr, len(inline_images),
        )

    doc.close()
    return PDFParseResult(pages=pages, page_count=len(pages))
