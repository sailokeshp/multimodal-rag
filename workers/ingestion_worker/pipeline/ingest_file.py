"""
Main ingestion pipeline — deterministic, resumable, per-file.

Steps:
  1.  Load file metadata from DB
  2.  Idempotency guard (checksum deduplicate, already-READY skip)
  3.  Load raw bytes from storage
  4.  Parse file by type (PDF / DOCX / image)
  5.  OCR pages/images where text is sparse
  6.  Chunk text into overlapping segments
  7.  Generate page summaries
  8.  Embed text chunks (EmbeddingGemma / BGE)
  9.  Embed images (SigLIP2)
  10. Persist everything to DB
  11. Mark file READY — or FAILED with error message
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Config / DB imports are deferred so this module can run as a worker
# without the full `app` package being present at import time.

def _get_settings():
    from app.config import get_settings as _gs
    return _gs()


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

async def ingest_file(file_id: str) -> None:
    """
    Entry point — called from SQS worker or inline from the API in local mode.
    Creates its own DB connection so it works both inside and outside the API.
    """
    settings = _get_settings()

    from app.db.models import File

    engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with SessionLocal() as db:
        try:
            await _run_pipeline(db, file_id)
        except Exception as exc:
            logger.error("Ingestion failed: file_id=%s err=%s", file_id, exc, exc_info=True)
            # Best-effort status update — ignore if it also fails.
            try:
                file_row = await db.get(File, file_id)
                if file_row:
                    file_row.status = "FAILED"
                    file_row.error_message = str(exc)[:1000]
                    await db.commit()
            except Exception as status_exc:
                logger.error("Failed to write FAILED status: %s", status_exc)
        finally:
            await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline orchestration
# ─────────────────────────────────────────────────────────────────────────────

async def _run_pipeline(db: AsyncSession, file_id: str) -> None:
    from app.db.models import DocumentChunk, File, Image
    from app.services.storage_service import StorageService
    from workers.ingestion_worker.embeddings.embedding_gemma import EmbeddingGemmaAdapter
    from workers.ingestion_worker.embeddings.siglip2_image import SigLIP2ImageAdapter

    settings = _get_settings()

    # 1. Load metadata
    file_row = await db.get(File, file_id)
    if not file_row:
        raise ValueError(f"File not found in DB: {file_id}")

    # 2. Idempotency — skip if already successfully processed
    if file_row.status == "READY":
        logger.info("file_id=%s already READY — skipping", file_id)
        return

    file_row.status = "PROCESSING"
    await db.flush()
    logger.info(
        "Ingestion started: file_id=%s name=%r type=%s",
        file_id, file_row.file_name, file_row.file_type,
    )

    # 3. Load raw bytes
    storage = StorageService()
    file_bytes = storage.read_bytes(file_row.s3_key)

    # Verify / record checksum (skip duplicate file content silently — same ID OK)
    checksum = hashlib.sha256(file_bytes).hexdigest()
    file_row.checksum = checksum
    file_row.size_bytes = len(file_bytes)
    await db.flush()

    text_adapter = EmbeddingGemmaAdapter() if settings.enable_text_embeddings else None
    image_adapter = SigLIP2ImageAdapter() if settings.enable_image_embeddings else None

    # 4–10. Dispatch by file type
    file_type = file_row.file_type.lower().lstrip(".")
    _FILE_TYPE_MAP = {
        "pdf": _ingest_pdf,
        "docx": _ingest_docx,
        "doc": _ingest_docx,
        "jpg": _ingest_image,
        "jpeg": _ingest_image,
        "png": _ingest_image,
        "webp": _ingest_image,
    }
    handler = _FILE_TYPE_MAP.get(file_type)
    if handler is None:
        raise ValueError(
            f"Unsupported file type: {file_type!r}. "
            f"Supported: {sorted(_FILE_TYPE_MAP)}"
        )

    await handler(db, file_row, file_bytes, storage, text_adapter, image_adapter)

    # 11. Mark READY
    file_row.status = "READY"
    file_row.processed_at = datetime.utcnow()
    await db.commit()
    logger.info("Ingestion complete: file_id=%s", file_id)


def _safe_embed_text(text_adapter, text: str) -> list[float] | None:
    if text_adapter is None:
        return None
    try:
        return text_adapter.embed_text(text)
    except Exception as exc:
        logger.warning("Text embedding skipped: %s", exc)
        return None


def _safe_embed_image(image_adapter, image_bytes: bytes) -> list[float] | None:
    if image_adapter is None:
        return None
    try:
        return image_adapter.embed_image(image_bytes)
    except Exception as exc:
        logger.warning("Image embedding skipped: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Per-type ingestors
# ─────────────────────────────────────────────────────────────────────────────

async def _ingest_pdf(
    db, file_row, file_bytes: bytes, storage, text_adapter, image_adapter
) -> None:
    from app.db.models import DocumentChunk, Image
    from workers.ingestion_worker.parsers.pdf_parser import parse_pdf
    from workers.ingestion_worker.ocr.tesseract_ocr import run_ocr
    from workers.ingestion_worker.chunking.text_chunker import chunk_text
    from workers.ingestion_worker.chunking.page_summary import summarize_page

    settings = _get_settings()
    result = parse_pdf(file_bytes, max_pages=settings.max_pdf_pages)
    file_row.page_count = result.page_count
    await db.flush()

    chunk_index = 0

    for page in result.pages:
        page_text = page.text

        # OCR scanned or image-heavy pages
        if page.needs_ocr and settings.use_local_ocr:
            try:
                import fitz
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                pix = doc[page.page_number - 1].get_pixmap(dpi=150)
                page_image_bytes = pix.tobytes("png")
                doc.close()
                ocr_text = run_ocr(page_image_bytes)
                if ocr_text:
                    page_text = ocr_text
                    for chunk in chunk_text(
                        ocr_text,
                        chunk_type="ocr_text",
                        page_start=page.page_number,
                        page_end=page.page_number,
                        start_index=chunk_index,
                    ):
                        chunk_index += 1
                        db.add(DocumentChunk(
                            id=uuid.uuid4(),
                            file_id=file_row.id,
                            chunk_type=chunk.chunk_type,
                            page_start=chunk.page_start,
                            page_end=chunk.page_end,
                            section_title=chunk.section_title,
                            chunk_index=chunk.chunk_index,
                            content=chunk.content,
                            token_count=chunk.token_count,
                            embedding=_safe_embed_text(text_adapter, chunk.content),
                        ))
            except Exception as exc:
                logger.warning("OCR failed for page %d: %s", page.page_number, exc)

        # Regular text chunks
        if page.text:
            for chunk in chunk_text(
                page.text,
                chunk_type="text_chunk",
                page_start=page.page_number,
                page_end=page.page_number,
                start_index=chunk_index,
            ):
                chunk_index += 1
                db.add(DocumentChunk(
                    id=uuid.uuid4(),
                    file_id=file_row.id,
                    chunk_type=chunk.chunk_type,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section_title=chunk.section_title,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    embedding=_safe_embed_text(text_adapter, chunk.content),
                ))

        # Page summary
        summary_text = summarize_page(page_text, page.page_number)
        if summary_text:
            db.add(DocumentChunk(
                id=uuid.uuid4(),
                file_id=file_row.id,
                chunk_type="page_summary",
                page_start=page.page_number,
                page_end=page.page_number,
                content=summary_text,
                embedding=_safe_embed_text(text_adapter, summary_text),
            ))

        # Inline images from this page
        for img_bytes in page.image_bytes:
            img_key = (
                f"extracted/{file_row.id}/page{page.page_number}"
                f"_{uuid.uuid4().hex[:8]}.jpg"
            )
            try:
                storage.write_bytes(img_key, img_bytes, "image/jpeg")
                db.add(Image(
                    id=uuid.uuid4(),
                    file_id=file_row.id,
                    page_number=page.page_number,
                    image_role="inline_extracted",
                    s3_key=img_key,
                    embedding=_safe_embed_image(image_adapter, img_bytes),
                ))
            except Exception as exc:
                logger.warning("Failed to store inline image: %s", exc)

        # Flush per page to avoid one giant transaction
        await db.flush()
        logger.debug("PDF page %d ingested (chunks=%d)", page.page_number, chunk_index)


async def _ingest_docx(
    db, file_row, file_bytes: bytes, storage, text_adapter, image_adapter
) -> None:
    from app.db.models import DocumentChunk, Image
    from workers.ingestion_worker.parsers.docx_parser import parse_docx
    from workers.ingestion_worker.chunking.text_chunker import chunk_text

    result = parse_docx(file_bytes)
    full_text = "\n\n".join(b.content for b in result.blocks)

    chunk_index = 0
    for chunk in chunk_text(full_text, chunk_type="text_chunk", start_index=chunk_index):
        chunk_index += 1
        db.add(DocumentChunk(
            id=uuid.uuid4(),
            file_id=file_row.id,
            chunk_type=chunk.chunk_type,
            section_title=chunk.section_title,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            token_count=chunk.token_count,
            embedding=_safe_embed_text(text_adapter, chunk.content),
        ))

    for idx, img_bytes in enumerate(result.inline_image_bytes):
        img_key = f"extracted/{file_row.id}/inline_{idx}.jpg"
        try:
            storage.write_bytes(img_key, img_bytes, "image/jpeg")
            db.add(Image(
                id=uuid.uuid4(),
                file_id=file_row.id,
                image_role="inline_extracted",
                s3_key=img_key,
                embedding=_safe_embed_image(image_adapter, img_bytes),
            ))
        except Exception as exc:
            logger.warning("Failed to store inline DOCX image %d: %s", idx, exc)

    await db.flush()
    logger.info(
        "DOCX ingested: file_id=%s chunks=%d images=%d",
        file_row.id, chunk_index, len(result.inline_image_bytes),
    )


async def _ingest_image(
    db, file_row, file_bytes: bytes, storage, text_adapter, image_adapter
) -> None:
    from app.db.models import Image
    from workers.ingestion_worker.parsers.image_parser import parse_image
    from workers.ingestion_worker.ocr.tesseract_ocr import run_ocr

    settings = _get_settings()
    parsed = parse_image(file_bytes)

    thumb_key = f"thumbnails/{file_row.id}/thumb.jpg"
    try:
        storage.write_bytes(thumb_key, parsed.thumbnail_bytes, "image/jpeg")
    except Exception as exc:
        logger.warning("Thumbnail write failed: %s", exc)
        thumb_key = None

    ocr_text: str | None = None
    if parsed.text_likely and settings.use_local_ocr:
        try:
            ocr_text = run_ocr(file_bytes) or None
        except Exception as exc:
            logger.warning("OCR failed for uploaded image: %s", exc)

    db.add(Image(
        id=uuid.uuid4(),
        file_id=file_row.id,
        image_role="uploaded",
        s3_key=file_row.s3_key,
        thumbnail_s3_key=thumb_key,
        width=parsed.width,
        height=parsed.height,
        ocr_text=ocr_text,
        embedding=_safe_embed_image(image_adapter, file_bytes),
    ))

    await db.flush()
    logger.info("Image ingested: file_id=%s size=%dx%d", file_row.id, parsed.width, parsed.height)
