"""
DAM (Digital Asset Management) API routes.

GET /files          — list all uploaded files with metadata + thumbnail URL
GET /files/{id}/detail — full asset detail with SigLIP2 embedding preview
DELETE /files/{id}  — delete a file and all its indexed data
"""
from __future__ import annotations

import logging
import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models import DocumentChunk, File, Image
from app.db.session import get_db
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/files", tags=["assets"])
settings = get_settings()


# ── Pydantic response models ──────────────────────────────────────────────────

class FileAssetOut(BaseModel):
    fileId: str
    fileName: str
    fileType: str
    mimeType: str | None
    status: str
    sizeBytes: int | None
    uploadedAt: str
    processedAt: str | None
    pageCount: int | None
    errorMessage: str | None
    chunkCount: int
    imageCount: int
    thumbnailUrl: str | None


class EmbeddingPreview(BaseModel):
    model: str
    dim: int
    sample: list[float]       # first 8 values
    norm: float               # should be ~1.0 after L2 normalisation


class ImageDetail(BaseModel):
    imageId: str
    pageNumber: int | None
    width: int | None
    height: int | None
    ocrText: str | None
    caption: str | None
    thumbnailUrl: str | None
    embedding: EmbeddingPreview | None


class ChunkPreview(BaseModel):
    chunkId: str
    chunkType: str
    pageStart: int | None
    sectionTitle: str | None
    contentPreview: str       # first 200 chars


class FileDetailOut(FileAssetOut):
    textEmbeddingModel: str
    textEmbeddingDim: int
    imageEmbeddingModel: str
    imageEmbeddingDim: int
    images: list[ImageDetail]
    chunks: list[ChunkPreview]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _thumbnail_url(s3_key: str | None) -> str | None:
    if not s3_key:
        return None
    storage = StorageService()
    try:
        return storage.generate_presigned_get_url(s3_key, expires_in=3600)
    except Exception:
        return None


def _embedding_preview(vec: Any, model: str, dim: int) -> EmbeddingPreview | None:
    if vec is None:
        return None
    try:
        vals = list(vec)[:8]
        norm = math.sqrt(sum(v * v for v in vals))
        return EmbeddingPreview(
            model=model,
            dim=dim,
            sample=[round(v, 6) for v in vals],
            norm=round(norm, 4),
        )
    except Exception:
        return None


def _format_file(
    file: File,
    chunk_count: int,
    image_count: int,
    thumbnail_url: str | None,
) -> FileAssetOut:
    return FileAssetOut(
        fileId=str(file.id),
        fileName=file.file_name,
        fileType=file.file_type,
        mimeType=file.mime_type,
        status=file.status,
        sizeBytes=file.size_bytes,
        uploadedAt=file.uploaded_at.isoformat(),
        processedAt=file.processed_at.isoformat() if file.processed_at else None,
        pageCount=file.page_count,
        errorMessage=file.error_message,
        chunkCount=chunk_count,
        imageCount=image_count,
        thumbnailUrl=thumbnail_url,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[FileAssetOut])
async def list_files(db: AsyncSession = Depends(get_db)) -> list[FileAssetOut]:
    """Return all uploaded files with aggregate counts and thumbnail URLs."""

    # Count chunks per file
    chunk_counts_q = await db.execute(
        select(DocumentChunk.file_id, func.count().label("n"))
        .group_by(DocumentChunk.file_id)
    )
    chunk_counts = {str(row.file_id): row.n for row in chunk_counts_q}

    # Count images per file + get first thumbnail key
    image_q = await db.execute(
        select(Image.file_id, func.count().label("n"), func.min(Image.thumbnail_s3_key).label("thumb"))
        .group_by(Image.file_id)
    )
    image_data = {
        str(row.file_id): {"count": row.n, "thumb": row.thumb}
        for row in image_q
    }

    files_q = await db.execute(
        select(File).order_by(File.uploaded_at.desc())
    )
    files = files_q.scalars().all()

    result = []
    for f in files:
        fid = str(f.id)
        img_info = image_data.get(fid, {"count": 0, "thumb": None})
        thumb = _thumbnail_url(img_info["thumb"])
        result.append(_format_file(f, chunk_counts.get(fid, 0), img_info["count"], thumb))

    return result


@router.get("/{file_id}/detail", response_model=FileDetailOut)
async def get_file_detail(
    file_id: str,
    db: AsyncSession = Depends(get_db),
) -> FileDetailOut:
    """Full asset detail including SigLIP2 embedding preview."""

    file = await db.get(
        File,
        file_id,
        options=[
            selectinload(File.images),
            selectinload(File.chunks),
        ],
    )
    if not file:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="File not found")

    # Build image details with embedding preview
    image_details = []
    for img in sorted(file.images, key=lambda i: (i.page_number or 0)):
        thumb = _thumbnail_url(img.thumbnail_s3_key or img.s3_key)
        emb = _embedding_preview(
            img.embedding,
            model=settings.image_embed_model_name,
            dim=settings.image_embed_dim,
        )
        image_details.append(ImageDetail(
            imageId=str(img.id),
            pageNumber=img.page_number,
            width=img.width,
            height=img.height,
            ocrText=img.ocr_text,
            caption=img.caption_text,
            thumbnailUrl=thumb,
            embedding=emb,
        ))

    # Chunk previews (first 5)
    chunk_previews = []
    for chunk in sorted(file.chunks, key=lambda c: (c.chunk_index or 0))[:5]:
        chunk_previews.append(ChunkPreview(
            chunkId=str(chunk.id),
            chunkType=chunk.chunk_type,
            pageStart=chunk.page_start,
            sectionTitle=chunk.section_title,
            contentPreview=chunk.content[:200],
        ))

    # Thumbnail from first image
    first_thumb = image_details[0].thumbnailUrl if image_details else None
    chunk_count = len(file.chunks)

    base = _format_file(file, chunk_count, len(file.images), first_thumb)

    return FileDetailOut(
        **base.model_dump(),
        textEmbeddingModel=settings.text_embed_model_name,
        textEmbeddingDim=settings.text_embed_dim,
        imageEmbeddingModel=settings.image_embed_model_name,
        imageEmbeddingDim=settings.image_embed_dim,
        images=image_details,
        chunks=chunk_previews,
    )


@router.delete("/{file_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a file and all its indexed chunks/images (cascades in DB)."""
    file = await db.get(File, file_id)
    if not file:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="File not found")
    await db.delete(file)
    await db.flush()
    logger.info("Deleted file %s (%s)", file_id, file.file_name)
