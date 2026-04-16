"""Unit tests for Pydantic request/response schemas."""
import pytest
from pydantic import ValidationError

from app.schemas.upload import UploadRequestIn, FileStatusOut
from app.schemas.search import SearchRequest, SearchFilters, DocumentChunkResult, ImageResult


# ── Upload schemas ────────────────────────────────────────────────────────────

def test_upload_request_valid():
    req = UploadRequestIn(fileName="report.pdf", contentType="application/pdf")
    assert req.fileName == "report.pdf"
    assert req.contentType == "application/pdf"


def test_upload_request_missing_field():
    with pytest.raises(ValidationError):
        UploadRequestIn(fileName="only.pdf")


def test_file_status_out_defaults():
    status = FileStatusOut(fileId="abc", status="READY")
    assert status.pageCount is None
    assert status.errorMessage is None


# ── Search schemas ────────────────────────────────────────────────────────────

def test_search_request_defaults():
    req = SearchRequest(query="invoices from Q3")
    assert req.topK == 10
    assert req.includeAnswer is False
    assert req.filters.fileTypes == []


def test_search_request_with_all_fields():
    req = SearchRequest(
        query="show me diagrams",
        topK=5,
        filters={"fileTypes": ["pdf", "png"]},
        includeAnswer=True,
    )
    assert req.topK == 5
    assert req.filters.fileTypes == ["pdf", "png"]
    assert req.includeAnswer is True


def test_document_chunk_result_defaults():
    r = DocumentChunkResult(
        fileId="uuid1",
        fileName="doc.pdf",
        snippet="some content",
        score=0.85,
    )
    assert r.resultType == "document_chunk"
    assert r.pageStart is None


def test_image_result_defaults():
    r = ImageResult(
        fileId="uuid2",
        fileName="photo.png",
        imageId="img-uuid",
        score=0.77,
    )
    assert r.resultType == "image"
    assert r.thumbnailUrl is None


# ── Config ────────────────────────────────────────────────────────────────────

def test_config_database_url_format():
    from app.config import Settings
    s = Settings()
    assert "postgresql+asyncpg://" in s.database_url
    assert s.postgres_db in s.database_url


def test_config_max_upload_bytes():
    from app.config import Settings
    s = Settings()
    assert s.max_upload_bytes == s.max_upload_mb * 1024 * 1024
