import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.session import engine
from app.db.models import Base
from app.routes import upload, search, answer, status, assets
from app.utils.security import verify_api_key

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create pgvector extension, tables, and performance indexes on startup.
    # All statements are idempotent (IF NOT EXISTS) — safe to run every time.
    async with engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.run_sync(Base.metadata.create_all)

        # ── HNSW vector indexes ───────────────────────────────────────────────
        # HNSW (Hierarchical Navigable Small World) gives O(log n) ANN search
        # vs O(n) for the default sequential scan. At 10k+ chunks the difference
        # is 10-100x query speedup with <5% recall loss.
        #
        # m=16: connections per node (standard value, good recall/speed balance)
        # ef_construction=64: build quality; higher = better recall, slower build
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_doc_chunks_hnsw
            ON document_chunks
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_images_hnsw
            ON images
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """))

        # ── Standard BTree indexes for common filter columns ─────────────────
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_files_status ON files (status)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_chunks_file_type "
            "ON document_chunks (chunk_type)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_chunks_file_id "
            "ON document_chunks (file_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_images_file_id "
            "ON images (file_id)"
        ))

    logger.info(
        "Database tables and indexes ensured. App starting (env=%s).",
        settings.app_env,
    )

    os.makedirs(settings.local_storage_path, exist_ok=True)

    yield

    await engine.dispose()
    logger.info("App shutdown complete.")


# Optional CORS origins — wildcard is fine for local dev.
# Set CORS_ORIGINS=https://myapp.com in production.
_cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")

app = FastAPI(
    title="Multimodal RAG API",
    description="Semantic search over images and documents using hybrid retrieval.",
    version="0.1.0",
    lifespan=lifespan,
    # Apply API-key check globally so Swagger UI still loads without auth.
    dependencies=[Depends(verify_api_key)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(assets.router)
app.include_router(status.router)
app.include_router(search.router)
app.include_router(answer.router)


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    """Health check — no auth required."""
    return {"status": "ok", "env": settings.app_env}
