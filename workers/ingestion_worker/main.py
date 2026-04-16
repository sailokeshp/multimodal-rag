"""
Ingestion worker entry point.

Local mode: polls SQS (or runs inline if SQS is not configured).
Start with: python -m workers.ingestion_worker.main
"""
import asyncio
import json
import logging
import os
import signal
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from app.config import get_settings
from workers.ingestion_worker.pipeline.ingest_file import ingest_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()

POLL_INTERVAL_SECONDS = 5
MAX_MESSAGES = 5

_running = True


def _handle_shutdown(signum, frame):
    global _running
    logger.info("Shutdown signal received — draining and stopping.")
    _running = False


signal.signal(signal.SIGTERM, _handle_shutdown)
signal.signal(signal.SIGINT, _handle_shutdown)


async def poll_sqs() -> None:
    import boto3
    sqs = boto3.client("sqs", region_name=settings.aws_region)
    logger.info("Worker polling SQS: %s", settings.sqs_queue_url)

    while _running:
        try:
            response = sqs.receive_message(
                QueueUrl=settings.sqs_queue_url,
                MaxNumberOfMessages=MAX_MESSAGES,
                WaitTimeSeconds=10,
            )
            messages = response.get("Messages", [])

            for msg in messages:
                body = json.loads(msg["Body"])
                file_id = body.get("file_id")
                if file_id:
                    logger.info("Processing file_id=%s", file_id)
                    await ingest_file(file_id)

                sqs.delete_message(
                    QueueUrl=settings.sqs_queue_url,
                    ReceiptHandle=msg["ReceiptHandle"],
                )

        except Exception as exc:
            logger.error("SQS poll error: %s", exc, exc_info=True)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def main() -> None:
    if settings.sqs_queue_url:
        await poll_sqs()
    else:
        logger.info(
            "No SQS_QUEUE_URL configured. "
            "Worker is idle — ingestion runs inline via the API in local mode."
        )
        while _running:
            await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
