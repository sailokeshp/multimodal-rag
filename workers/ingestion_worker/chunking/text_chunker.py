"""
Sentence-aware semantic text chunker.

Industry-grade chunking strategy:
  1. Split text into atomic units (sentences) using a hierarchy of separators
  2. Group sentences into chunks respecting the token budget
  3. Overlap at the sentence level — not character slice — so context is coherent
  4. Skip micro-chunks (page numbers, OCR noise) below MIN_CHUNK_TOKENS
  5. Preserve heading context in every chunk for better retrieval

Why sentence-level chunking matters:
  - Character-slice overlap frequently cuts mid-word or mid-sentence
  - A retrieved chunk that starts "…ently, the revenue grew" confuses the LLM
  - Sentence-boundary overlap keeps each chunk semantically self-contained
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Tuning constants ───────────────────────────────────────────────────────────
TARGET_TOKENS     = 512   # target chunk size (not hard limit)
MAX_TOKENS        = 768   # hard upper bound — prevents over-size context entries
MIN_CHUNK_TOKENS  = 30    # discard chunks shorter than this (noise / page numbers)
OVERLAP_SENTENCES = 2     # sentences to carry over for continuity
AVG_CHARS_PER_TOKEN = 4   # English prose estimate; safe for technical docs

TARGET_CHARS = TARGET_TOKENS * AVG_CHARS_PER_TOKEN   # 2048 chars
MAX_CHARS    = MAX_TOKENS * AVG_CHARS_PER_TOKEN       # 3072 chars
MIN_CHARS    = MIN_CHUNK_TOKENS * AVG_CHARS_PER_TOKEN # 120 chars

# Detect headings: markdown (#), ALLCAPS lines, or numbered sections (1. / 1.1 /)
HEADING_RE = re.compile(
    r"^(?:"
    r"#{1,6}\s+.+"                            # Markdown ## Heading
    r"|[A-Z][A-Z\d\s,\-]{4,}:?"              # ALL CAPS LINE
    r"|\d+(?:\.\d+)*[.)]\s+[A-Z].{3,}"       # 1. Introduction / 1.1 Background
    r")$",
    re.MULTILINE,
)

# Protect common abbreviations from being split as sentence endings
_ABBR_PATTERN = re.compile(
    r"\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|al|e\.g|i\.e|no|vol|pp|fig|sec|dept|approx|est)\.",
    re.IGNORECASE,
)
_ABBR_PLACEHOLDER = "\x00ABBR\x00"


@dataclass
class TextChunk:
    content: str
    chunk_type: str       # text_chunk | ocr_text | page_summary | table_summary | image_caption
    section_title: str | None
    chunk_index: int
    page_start: int | None = None
    page_end: int | None = None
    token_count: int = 0


# ── Public API ────────────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    section_title: str | None = None,
    chunk_type: str = "text_chunk",
    page_start: int | None = None,
    page_end: int | None = None,
    start_index: int = 0,
) -> list[TextChunk]:
    """
    Chunk text using sentence-boundary aware splitting.

    Algorithm:
      1. Split text into paragraphs (double-newline separated)
      2. Detect heading paragraphs — flush current chunk and update section context
      3. Within each non-heading paragraph, split into sentences
      4. Accumulate sentences into a chunk up to TARGET_CHARS
      5. When budget is reached, flush and carry over the last OVERLAP_SENTENCES
         so the new chunk starts with coherent context
      6. Discard micro-chunks (< MIN_CHARS)
    """
    if not text or not text.strip():
        return []

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[TextChunk] = []
    accumulated_sentences: list[str] = []
    current_chars = 0
    chunk_index = start_index
    current_section = section_title

    for para in paragraphs:
        # ── Heading detection ─────────────────────────────────────────────────
        if HEADING_RE.match(para):
            if accumulated_sentences:
                _flush(
                    chunks, accumulated_sentences, chunk_type,
                    current_section, chunk_index, page_start, page_end,
                )
                chunk_index += 1
                # Carry over last overlap sentences
                accumulated_sentences = accumulated_sentences[-OVERLAP_SENTENCES:]
                current_chars = sum(len(s) for s in accumulated_sentences)
            current_section = para
            continue

        # ── Split paragraph into sentences ───────────────────────────────────
        sentences = _split_sentences(para)

        for sent in sentences:
            sent_len = len(sent)

            # Single sentence longer than MAX_CHARS — hard split it
            if sent_len > MAX_CHARS:
                sub_sentences = _hard_split(sent, TARGET_CHARS)
                sentences_to_add = sub_sentences
            else:
                sentences_to_add = [sent]

            for s in sentences_to_add:
                s_len = len(s)
                if current_chars + s_len > TARGET_CHARS and accumulated_sentences:
                    _flush(
                        chunks, accumulated_sentences, chunk_type,
                        current_section, chunk_index, page_start, page_end,
                    )
                    chunk_index += 1
                    # Keep last OVERLAP_SENTENCES for continuity
                    accumulated_sentences = accumulated_sentences[-OVERLAP_SENTENCES:]
                    current_chars = sum(len(x) for x in accumulated_sentences)

                accumulated_sentences.append(s)
                current_chars += s_len

    # Final flush
    if accumulated_sentences:
        _flush(
            chunks, accumulated_sentences, chunk_type,
            current_section, chunk_index, page_start, page_end,
        )

    logger.debug(
        "Chunked into %d chunks (type=%s, page=%s)",
        len(chunks), chunk_type, page_start,
    )
    return chunks


# ── Internal helpers ──────────────────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    """
    Split a paragraph into sentences using a two-pass regex approach.

    Pass 1: Protect common abbreviations (Dr., Mr., etc.) so they don't
            trigger false sentence boundaries.
    Pass 2: Split on sentence-ending punctuation followed by whitespace
            and a word start character (uppercase letter, digit, quote).
    """
    # Protect abbreviations
    protected = _ABBR_PATTERN.sub(
        lambda m: m.group(0)[:-1] + _ABBR_PLACEHOLDER, text
    )

    # Split on sentence boundaries
    raw_sentences = re.split(
        r'(?<=[.!?])\s+(?=[A-Z0-9"\'(\[])',
        protected,
    )

    # Restore abbreviation dots and clean up
    cleaned: list[str] = []
    for s in raw_sentences:
        s = s.replace(_ABBR_PLACEHOLDER, ".").strip()
        if s:
            cleaned.append(s)

    return cleaned if cleaned else [text.strip()]


def _hard_split(text: str, target_chars: int) -> list[str]:
    """
    Last-resort splitter for sentences longer than MAX_CHARS.
    Splits on word boundary nearest to target_chars.
    """
    parts = []
    while len(text) > target_chars:
        split_at = text.rfind(" ", 0, target_chars)
        if split_at == -1:
            split_at = target_chars
        parts.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        parts.append(text)
    return parts


def _flush(
    chunks: list[TextChunk],
    sentences: list[str],
    chunk_type: str,
    section_title: str | None,
    chunk_index: int,
    page_start: int | None,
    page_end: int | None,
) -> None:
    content = " ".join(sentences).strip()
    if len(content) < MIN_CHARS:
        logger.debug("Skipping micro-chunk (%d chars): %r…", len(content), content[:40])
        return
    chunks.append(
        TextChunk(
            content=content,
            chunk_type=chunk_type,
            section_title=section_title,
            chunk_index=chunk_index,
            page_start=page_start,
            page_end=page_end,
            token_count=len(content) // AVG_CHARS_PER_TOKEN,
        )
    )
