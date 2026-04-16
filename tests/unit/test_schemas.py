"""Unit tests for Pydantic request/response schemas."""
from io import BytesIO

import pytest
from pydantic import ValidationError
from starlette.datastructures import Headers, UploadFile

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


def test_config_embedding_flags_defaults():
    from app.config import Settings
    s = Settings()
    assert s.enable_text_embeddings is True
    assert s.enable_image_embeddings is False


@pytest.mark.asyncio
async def test_direct_upload_uses_storage_backend(monkeypatch):
    from app.routes.upload import local_upload

    class FakeDB:
        def __init__(self):
            self.rows = []

        def add(self, row):
            self.rows.append(row)

        async def flush(self):
            return None

    writes = []
    enqueued = []

    def fake_write_bytes(self, s3_key, data, content_type="application/octet-stream"):
        writes.append((s3_key, data, content_type))

    async def fake_enqueue(file_id: str):
        enqueued.append(file_id)

    monkeypatch.setattr("app.routes.upload.StorageService.write_bytes", fake_write_bytes)
    monkeypatch.setattr("app.routes.upload.enqueue_ingestion", fake_enqueue)

    upload = UploadFile(
        file=BytesIO(b"hello world"),
        filename="sample.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    db = FakeDB()

    resp = await local_upload(upload, db=db)

    assert resp.fileId
    assert resp.s3Key.endswith("/sample.pdf")
    assert resp.s3Key.startswith(f"raw/{resp.fileId}/")
    assert writes == [(resp.s3Key, b"hello world", "application/pdf")]
    assert enqueued == [resp.fileId]
    assert db.rows[0].s3_key == resp.s3Key
