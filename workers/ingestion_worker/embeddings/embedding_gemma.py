"""
Text embedding adapter using sentence-transformers.

Default model: BAAI/bge-small-en-v1.5 (384d, ~33 MB, fast on CPU)

Override via env:
  TEXT_EMBED_MODEL_NAME=BAAI/bge-base-en-v1.5    # 768d, better quality
  TEXT_EMBED_MODEL_NAME=BAAI/bge-large-en-v1.5   # 1024d, best quality
  TEXT_EMBED_DIM=<matching dim>

Note: if you change the model you must also change TEXT_EMBED_DIM and
recreate the Postgres tables (the vector column dimension is fixed).

The BGE family was chosen because:
- It's fully CPU-compatible
- Quality rivals much larger models on retrieval benchmarks
- sentence-transformers handles pooling and normalisation automatically
- It aligns with the Gemma-family retrieval philosophy (dense embedding)
"""
from __future__ import annotations

import logging
import os
import threading
from typing import ClassVar

logger = logging.getLogger(__name__)

_MODEL_NAME = os.getenv("TEXT_EMBED_MODEL_NAME", "BAAI/bge-small-en-v1.5")
EMBED_DIM = int(os.getenv("TEXT_EMBED_DIM", "384"))

_lock = threading.Lock()


class EmbeddingGemmaAdapter:
    """
    Thread-safe, singleton-backed text embedding adapter.
    Class-level _model ensures one SentenceTransformer per process.
    """

    _model: ClassVar = None
    _load_error: ClassVar[str | None] = None

    # BGE models are trained to embed queries with a short prefix for retrieval.
    _QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def _load_model(self) -> None:
        if EmbeddingGemmaAdapter._model is not None:
            return
        if EmbeddingGemmaAdapter._load_error is not None:
            raise RuntimeError(
                f"Text embedding model previously failed: {EmbeddingGemmaAdapter._load_error}"
            )

        with _lock:
            if EmbeddingGemmaAdapter._model is not None:
                return

            logger.info("Loading text embedding model: %s…", _MODEL_NAME)
            try:
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(_MODEL_NAME)
                actual_dim = model.get_sentence_embedding_dimension()
                if actual_dim != EMBED_DIM:
                    raise ValueError(
                        f"Model {_MODEL_NAME!r} produces {actual_dim}-dim embeddings "
                        f"but TEXT_EMBED_DIM={EMBED_DIM}. "
                        "Set TEXT_EMBED_DIM to match, then recreate the DB."
                    )

                EmbeddingGemmaAdapter._model = model
                logger.info(
                    "Text embedding model loaded: %s (dim=%d)", _MODEL_NAME, actual_dim
                )
            except Exception as exc:
                EmbeddingGemmaAdapter._load_error = str(exc)
                logger.error("Text embedding model load failed: %s", exc, exc_info=True)
                raise

    def embed_text(self, text: str, is_query: bool = False) -> list[float]:
        """
        Embed a single text string.

        Args:
            text: The text to embed.
            is_query: If True, apply the BGE query prefix for better
                      retrieval performance (use for search queries,
                      not for document chunks).
        """
        self._load_model()
        if EmbeddingGemmaAdapter._model is None:
            return [0.0] * EMBED_DIM

        input_text = (self._QUERY_PREFIX + text) if is_query else text
        # normalize_embeddings=True → L2 unit vectors, cosine sim = dot product
        vec = (
            EmbeddingGemmaAdapter._model
            .encode(input_text, normalize_embeddings=True)
            .tolist()
        )
        return vec

    def embed_batch(
        self, texts: list[str], is_query: bool = False
    ) -> list[list[float]]:
        """Batch encode for efficiency (avoids per-text overhead)."""
        self._load_model()
        if EmbeddingGemmaAdapter._model is None:
            return [[0.0] * EMBED_DIM for _ in texts]

        inputs = (
            [self._QUERY_PREFIX + t for t in texts] if is_query else texts
        )
        vecs = (
            EmbeddingGemmaAdapter._model
            .encode(inputs, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
            .tolist()
        )
        return vecs
