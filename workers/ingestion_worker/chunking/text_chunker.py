"""
Structure-aware text chunker.
Splits first by heading/section, then by paragraph groups.
Target chunk size: 400-800 tokens. Overlap: ~15%.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TARGET_TOKENS = 600
OVERLAP_TOKENS = 90   # ~15%
AVG_CHARS_PER_TOKEN = 4  # rough estimate for English text

TARGET_CHARS = TARGET_TOKENS * AVG_CHARS_PER_TOKEN
OVERLAP_CHARS = OVERLAP_TOKENS * AVG_CHARS_PER_TOKEN

HEADING_RE = re.compile(r"^(#{1,6}\s+.+|[A-Z][A-Z\s]{4,}:?)$", re.MULTILINE)


@dataclass
class TextChunk:
    content: str
    chunk_type: str   # text_chunk | ocr_text | page_summary | table_summary | image_caption
    section_title: str | None
    chunk_index: int
    page_start: int | None = None
    page_end: int | None = None
    token_count: int = 0


def chunk_text(
    text: str,
    section_title: str | None = None,
    chunk_type: str = "text_chunk",
    page_start: int | None = None,
    page_end: int | None = None,
    start_index: int = 0,
) -> list[TextChunk]:
    """
    Chunk text into overlapping segments, preserving section context.
    """
    if not text.strip():
        return []

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[TextChunk] = []
    current = ""
    chunk_index = start_index

    for para in paragraphs:
        # Detect heading
        if HEADING_RE.match(para) and current:
            _flush(chunks, current, chunk_type, section_title, chunk_index, page_start, page_end)
            chunk_index += 1
            section_title = para
            current = ""
            continue

        if len(current) + len(para) + 2 > TARGET_CHARS and current:
            _flush(chunks, current, chunk_type, section_title, chunk_index, page_start, page_end)
            chunk_index += 1
            # Overlap: keep tail of previous chunk
            current = current[-OVERLAP_CHARS:] + "\n\n" + para
        else:
            current = (current + "\n\n" + para).strip()

    if current:
        _flush(chunks, current, chunk_type, section_title, chunk_index, page_start, page_end)

    logger.debug("Chunked into %d chunks (type=%s)", len(chunks), chunk_type)
    return chunks


def _flush(
    chunks: list[TextChunk],
    content: str,
    chunk_type: str,
    section_title: str | None,
    chunk_index: int,
    page_start: int | None,
    page_end: int | None,
) -> None:
    chunks.append(
        TextChunk(
            content=content.strip(),
            chunk_type=chunk_type,
            section_title=section_title,
            chunk_index=chunk_index,
            page_start=page_start,
            page_end=page_end,
            token_count=len(content) // AVG_CHARS_PER_TOKEN,
        )
    )
