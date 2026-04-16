import hashlib
import logging
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import File
from app.db.session import get_db
from app.schemas.upload import (
    FileStatusOut,
    UploadCompleteIn,
    UploadCompleteOut,
    UploadRequestIn,
    UploadRequestOut,
)
from app.services.storage_service import StorageService
from app.services.ingestion_service import enqueue_ingestion

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["upload"])
settings = get_settings()

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
    "image/webp",
}


@router.post("/request", response_model=UploadRequestOut)
async def request_upload(
    body: UploadRequestIn,
    db: AsyncSession = Depends(get_db),
) -> UploadRequestOut:
    if body.contentType not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {body.contentType}",
        )

    file_id = uuid.uuid4()
    ext = os.path.splitext(body.fileName)[1]
    s3_key = f"raw/{file_id}/{body.fileName}"

    storage = StorageService()
    upload_url = storage.generate_presigned_put_url(s3_key, body.contentType)

    file_row = File(
        id=file_id,
        file_name=body.fileName,
        file_type=ext.lstrip(".").lower(),
        mime_type=body.contentType,
        s3_key=s3_key,
        status="PENDING_UPLOAD",
        uploaded_at=datetime.utcnow(),
    )
    db.add(file_row)
    await db.flush()

    logger.info("Upload requested: file_id=%s key=%s", file_id, s3_key)
    return UploadRequestOut(fileId=str(file_id), uploadUrl=upload_url, s3Key=s3_key)


@router.post("/complete", response_model=UploadCompleteOut)
async def complete_upload(
    body: UploadCompleteIn,
    db: AsyncSession = Depends(get_db),
) -> UploadCompleteOut:
    file_row = await db.get(File, body.fileId)
    if not file_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    file_row.status = "UPLOADED"
    await db.flush()

    await enqueue_ingestion(str(file_row.id))
    logger.info("Upload complete, ingestion enqueued: file_id=%s", file_row.id)
    return UploadCompleteOut(status="UPLOADED")


@router.post("/local", response_model=UploadRequestOut, summary="Direct upload for local dev")
async def local_upload(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
) -> UploadRequestOut:
    """
    Accepts a multipart file upload directly (no presigned URL needed).
    For local development only — skips S3 and saves to LOCAL_STORAGE_PATH.
    """
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {file.content_type}",
        )

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_mb} MB limit",
        )

    checksum = hashlib.sha256(content).hexdigest()
    file_id = uuid.uuid4()
    ext = os.path.splitext(file.filename or "file")[1]
    s3_key = f"raw/{file_id}/{file.filename}"

    local_path = os.path.join(settings.local_storage_path, str(file_id))
    os.makedirs(local_path, exist_ok=True)
    dest = os.path.join(local_path, file.filename or "upload")
    with open(dest, "wb") as f:
        f.write(content)

    file_row = File(
        id=file_id,
        file_name=file.filename,
        file_type=ext.lstrip(".").lower(),
        mime_type=file.content_type,
        s3_key=s3_key,
        checksum=checksum,
        size_bytes=len(content),
        status="UPLOADED",
        uploaded_at=datetime.utcnow(),
    )
    db.add(file_row)
    await db.flush()

    await enqueue_ingestion(str(file_id))
    logger.info("Local upload complete, ingestion enqueued: file_id=%s", file_id)
    return UploadRequestOut(fileId=str(file_id), uploadUrl="", s3Key=s3_key)
