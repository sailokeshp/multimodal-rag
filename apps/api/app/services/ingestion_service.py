import json
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def enqueue_ingestion(file_id: str) -> None:
    """
    Send a file-id to the ingestion queue.
    Uses SQS in production and a direct in-process call in local mode.
    """
    if settings.app_env == "local" or not settings.sqs_queue_url:
        logger.info("Local mode: triggering ingestion inline for file_id=%s", file_id)
        await _run_local_ingestion(file_id)
        return

    import boto3
    sqs = boto3.client("sqs", region_name=settings.aws_region)
    sqs.send_message(
        QueueUrl=settings.sqs_queue_url,
        MessageBody=json.dumps({"file_id": file_id}),
    )
    logger.info("Enqueued ingestion for file_id=%s", file_id)


async def _run_local_ingestion(file_id: str) -> None:
    """
    Run ingestion directly in the API process (local dev only).
    Imports the worker pipeline lazily to avoid heavy deps in production API.
    """
    try:
        import importlib
        pipeline = importlib.import_module("workers.ingestion_worker.pipeline.ingest_file")
        await pipeline.ingest_file(file_id)
    except ModuleNotFoundError:
        logger.warning(
            "Ingestion worker not importable from API process. "
            "Start the worker separately: python -m workers.ingestion_worker.main"
        )
    except Exception as exc:
        logger.error("Local ingestion failed for file_id=%s: %s", file_id, exc, exc_info=True)
