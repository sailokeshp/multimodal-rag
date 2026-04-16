from pydantic import BaseModel


class UploadRequestIn(BaseModel):
    fileName: str
    contentType: str


class UploadRequestOut(BaseModel):
    fileId: str
    uploadUrl: str
    s3Key: str


class UploadCompleteIn(BaseModel):
    fileId: str


class UploadCompleteOut(BaseModel):
    status: str


class FileStatusOut(BaseModel):
    fileId: str
    status: str
    pageCount: int | None = None
    errorMessage: str | None = None
