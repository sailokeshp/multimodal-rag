"""Unit tests for the structure-aware text chunker."""
import pytest

from workers.ingestion_worker.chunking.text_chunker import chunk_text


def test_empty_text_returns_nothing():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_short_text_produces_single_chunk():
    chunks = chunk_text("This is a short paragraph.")
    assert len(chunks) == 1
    assert chunks[0].content == "This is a short paragraph."
    assert chunks[0].chunk_index == 0


def test_long_text_splits_into_multiple_chunks():
    # ~3000 chars — should produce 2+ chunks at 600-token target
    text = "\n\n".join(["word " * 80] * 8)
    chunks = chunk_text(text)
    assert len(chunks) > 1


def test_chunk_type_is_preserved():
    chunks = chunk_text("some text here", chunk_type="ocr_text")
    assert all(c.chunk_type == "ocr_text" for c in chunks)


def test_default_chunk_type_is_text_chunk():
    chunks = chunk_text("a paragraph of text")
    assert chunks[0].chunk_type == "text_chunk"


def test_page_numbers_are_propagated():
    chunks = chunk_text("page text", page_start=5, page_end=5)
    assert all(c.page_start == 5 for c in chunks)
    assert all(c.page_end == 5 for c in chunks)


def test_start_index_offsets_chunk_indices():
    chunks = chunk_text("some text", start_index=10)
    assert chunks[0].chunk_index == 10


def test_section_title_is_preserved():
    chunks = chunk_text("body text", section_title="Introduction")
    assert chunks[0].section_title == "Introduction"


def test_token_count_is_estimated():
    chunks = chunk_text("four words here text")
    # Token count is a rough estimate (len/4); must be > 0
    assert all(c.token_count > 0 for c in chunks)


def test_overlap_present_in_long_text():
    """Last chars of chunk N should appear at the start of chunk N+1."""
    # Build text long enough to force multiple chunks
    text = "\n\n".join(["word " * 100] * 6)
    chunks = chunk_text(text)
    if len(chunks) > 1:
        # Overlap means chunk[1] content should share some suffix of chunk[0]
        tail = chunks[0].content[-50:]
        assert tail in chunks[1].content, "Expected overlap between consecutive chunks"
