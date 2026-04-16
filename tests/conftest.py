"""
Shared pytest fixtures for the multimodal RAG test suite.

The tests/unit tests run fully offline — no DB or network required.
The tests/integration tests require Postgres (use docker-compose or a local DB).
"""
import os
import sys

# Make both the API app and the worker importable without installing them.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "apps", "api"))

# Set safe environment defaults so imports don't fail without a real .env.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "multimodal_rag_test")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "postgres")
os.environ.setdefault("LOCAL_STORAGE_PATH", "/tmp/rag_test_uploads")
os.environ.setdefault("TEXT_EMBED_DIM", "384")
os.environ.setdefault("IMAGE_EMBED_DIM", "1152")
os.environ.setdefault("ENABLE_TEXT_EMBEDDINGS", "true")
os.environ.setdefault("ENABLE_IMAGE_EMBEDDINGS", "false")
os.environ.setdefault("GEN_MODEL_BACKEND", "google_ai")
os.environ.setdefault("ENABLE_GROUNDED_ANSWER", "false")
os.environ.setdefault("RETRIEVAL_SCORE_THRESHOLD", "0.0")  # no threshold in tests
