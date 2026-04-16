"""
Run ingestion for a specific file_id directly (bypasses the queue).

Usage:
    python scripts/local_index_run.py <file_id>
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/local_index_run.py <file_id>")
        sys.exit(1)

    file_id = sys.argv[1]
    print(f"Running ingestion for file_id={file_id}")

    from workers.ingestion_worker.pipeline.ingest_file import ingest_file
    await ingest_file(file_id)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
