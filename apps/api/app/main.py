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
    # Create pgvector extension and tables on startup (idempotent).
    async with engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured. App starting (env=%s).", settings.app_env)

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
