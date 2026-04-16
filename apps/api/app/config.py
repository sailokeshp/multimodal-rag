import os
from functools import lru_cache


class Settings:
    app_env: str = os.getenv("APP_ENV", "local")
    api_port: int = int(os.getenv("API_PORT", "8000"))

    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "multimodal_rag")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "postgres")

    s3_bucket: str = os.getenv("S3_BUCKET", "multimodal-rag-dev")
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")

    use_textract: bool = os.getenv("USE_TEXTRACT", "false").lower() == "true"
    use_local_ocr: bool = os.getenv("USE_LOCAL_OCR", "true").lower() == "true"

    # ── Text embedding ────────────────────────────────────────────────────────
    # Configurable model name.  Default is a fast, CPU-friendly model (384d).
    # Change to "BAAI/bge-base-en-v1.5" (768d) or "BAAI/bge-large-en-v1.5"
    # (1024d) for higher quality, but you must recreate the DB if you change.
    text_embed_model_name: str = os.getenv(
        "TEXT_EMBED_MODEL_NAME", "BAAI/bge-small-en-v1.5"
    )
    # Dimension must match the chosen model — set explicitly when overriding.
    text_embed_dim: int = int(os.getenv("TEXT_EMBED_DIM", "384"))
    enable_text_embeddings: bool = os.getenv(
        "ENABLE_TEXT_EMBEDDINGS", "true"
    ).lower() == "true"

    # ── Image embedding ───────────────────────────────────────────────────────
    # SigLIP2 so400m produces 1152-dimensional embeddings.
    image_embed_model_name: str = os.getenv(
        "IMAGE_EMBED_MODEL_NAME", "google/siglip2-so400m-patch16-384"
    )
    image_embed_dim: int = int(os.getenv("IMAGE_EMBED_DIM", "1152"))
    # Disabled by default because the optional SigLIP2 dependencies are not
    # installed in the default worker image and the model is memory-heavy.
    enable_image_embeddings: bool = os.getenv(
        "ENABLE_IMAGE_EMBEDDINGS", "false"
    ).lower() == "true"

    # ── Generation ────────────────────────────────────────────────────────────
    # Backend: "groq" (default, free), "google_ai" (free), or "local" (needs RAM).
    gen_model_backend: str = os.getenv("GEN_MODEL_BACKEND", "google_ai")
    gen_model_name: str = os.getenv("GEN_MODEL_NAME", "gemma2-9b-it")
    # Groq backend (default — gemma2-9b-it, free, no credit card):
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    # Google AI backend (alternative free option):
    google_ai_api_key: str = os.getenv("GOOGLE_AI_API_KEY", "")
    google_ai_model: str = os.getenv("GOOGLE_AI_MODEL", "gemini-2.0-flash")
    enable_grounded_answer: bool = os.getenv("ENABLE_GROUNDED_ANSWER", "true").lower() == "true"

    # ── Retrieval tuning ──────────────────────────────────────────────────────
    top_k_text: int = int(os.getenv("TOP_K_TEXT", "8"))
    top_k_image: int = int(os.getenv("TOP_K_IMAGE", "8"))
    top_k_final: int = int(os.getenv("TOP_K_FINAL", "10"))
    # Minimum cosine similarity score to include a result (0.0 = no threshold).
    retrieval_score_threshold: float = float(os.getenv("RETRIEVAL_SCORE_THRESHOLD", "0.3"))

    # ── Upload limits ─────────────────────────────────────────────────────────
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "50"))
    max_pdf_pages: int = int(os.getenv("MAX_PDF_PAGES", "300"))

    # ── Queue / storage ───────────────────────────────────────────────────────
    sqs_queue_url: str = os.getenv("SQS_QUEUE_URL", "")
    local_storage_path: str = os.getenv("LOCAL_STORAGE_PATH", "/tmp/rag_uploads")

    # ── Security ──────────────────────────────────────────────────────────────
    # Set a non-empty value to require X-API-Key header on all requests.
    api_key: str = os.getenv("API_KEY", "")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
