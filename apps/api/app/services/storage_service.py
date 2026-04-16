import logging
import os

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class StorageService:
    """
    Abstraction over file storage.
    Uses AWS S3 in production and local filesystem in APP_ENV=local.
    """

    def generate_presigned_put_url(self, s3_key: str, content_type: str, expires_in: int = 3600) -> str:
        if settings.app_env == "local":
            return f"local://{settings.local_storage_path}/{s3_key}"

        import boto3
        s3 = boto3.client("s3", region_name=settings.aws_region)
        url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.s3_bucket,
                "Key": s3_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        return url

    def generate_presigned_get_url(self, s3_key: str, expires_in: int = 3600) -> str:
        if settings.app_env == "local":
            return f"local://{settings.local_storage_path}/{s3_key}"

        import boto3
        s3 = boto3.client("s3", region_name=settings.aws_region)
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": s3_key},
            ExpiresIn=expires_in,
        )
        return url

    def get_local_path(self, s3_key: str) -> str:
        return os.path.join(settings.local_storage_path, s3_key)

    def read_bytes(self, s3_key: str) -> bytes:
        if settings.app_env == "local":
            path = self.get_local_path(s3_key)
            with open(path, "rb") as f:
                return f.read()

        import boto3
        s3 = boto3.client("s3", region_name=settings.aws_region)
        resp = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        return resp["Body"].read()

    def write_bytes(self, s3_key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        if settings.app_env == "local":
            path = self.get_local_path(s3_key)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            return

        import boto3
        s3 = boto3.client("s3", region_name=settings.aws_region)
        s3.put_object(Bucket=settings.s3_bucket, Key=s3_key, Body=data, ContentType=content_type)
