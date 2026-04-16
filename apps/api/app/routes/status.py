import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import File
from app.db.session import get_db
from app.schemas.upload import FileStatusOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/files", tags=["files"])
settings = get_settings()


@router.get("/{file_id}/status", response_model=FileStatusOut)
async def get_file_status(
    file_id: str,
    db: AsyncSession = Depends(get_db),
) -> FileStatusOut:
    file_row = await db.get(File, file_id)
    if not file_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    return FileStatusOut(
        fileId=str(file_row.id),
        status=file_row.status,
        pageCount=file_row.page_count,
        errorMessage=file_row.error_message,
    )


@router.get("/thumbnail/{path:path}", include_in_schema=False)
async def serve_thumbnail(path: str):
    """
    Serve a locally stored thumbnail image.
    Used by the frontend to display image results without S3 presigned URLs.
    """
    # Security: resolve and ensure the path stays within local_storage_path.
    local_root = os.path.realpath(settings.local_storage_path)
    requested = os.path.realpath(os.path.join(local_root, path))

    if not requested.startswith(local_root + os.sep) and requested != local_root:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path")

    if not os.path.isfile(requested):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not found")

    return FileResponse(requested, media_type="image/jpeg")
