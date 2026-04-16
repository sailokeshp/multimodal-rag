"""
Seed demo data for local development.
Creates a sample PDF and image upload record to test search.

Usage:
    python scripts/seed_demo_data.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from app.config import get_settings
from workers.ingestion_worker.pipeline.ingest_file import ingest_file

settings = get_settings()


async def main():
    demo_dir = os.path.join(settings.local_storage_path, "demo")
    os.makedirs(demo_dir, exist_ok=True)

    print("Seed script ready.")
    print("To test ingestion, call ingest_file('<uuid>') with a real file_id from the DB.")
    print("Or use POST /upload/local to upload a file via the API.")


if __name__ == "__main__":
    asyncio.run(main())
