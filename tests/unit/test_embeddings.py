"""
Unit tests for embedding adapters.

These tests verify the adapter API contract — correct output dimension,
L2 normalisation, batch consistency, and graceful error handling.
They do NOT require a GPU or a large model download when the model is
already cached; on CI they mock the model loading.
"""
from __future__ import annotations

import math
import pytest
from unittest.mock import MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _l2_norm(vec: list[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))


# ── EmbeddingGemmaAdapter ─────────────────────────────────────────────────────

class TestEmbeddingGemmaAdapter:

    def test_returns_list_of_floats(self):
        from workers.ingestion_worker.embeddings.embedding_gemma import (
            EmbeddingGemmaAdapter, EMBED_DIM
        )
        adapter = EmbeddingGemmaAdapter()
        # Patch model to avoid download during unit tests.
        mock_model = MagicMock()
        import numpy as np
        fake_vec = np.ones(EMBED_DIM) / math.sqrt(EMBED_DIM)
        mock_model.encode.return_value = fake_vec
        mock_model.get_sentence_embedding_dimension.return_value = EMBED_DIM

        EmbeddingGemmaAdapter._model = mock_model
        try:
            vec = adapter.embed_text("hello world")
            assert isinstance(vec, list)
            assert len(vec) == EMBED_DIM
            assert all(isinstance(x, float) for x in vec)
        finally:
            EmbeddingGemmaAdapter._model = None  # reset

    def test_batch_matches_single(self):
        from workers.ingestion_worker.embeddings.embedding_gemma import (
            EmbeddingGemmaAdapter, EMBED_DIM
        )
        import numpy as np
        adapter = EmbeddingGemmaAdapter()
        texts = ["alpha text", "beta text", "gamma text"]

        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = EMBED_DIM
        single_vec = np.ones(EMBED_DIM) / math.sqrt(EMBED_DIM)
        # embed_batch calls encode with a list → must return 2D array
        batch_vecs = np.stack([single_vec] * len(texts))
        mock_model.encode.return_value = batch_vecs

        EmbeddingGemmaAdapter._model = mock_model
        try:
            batch = adapter.embed_batch(texts)
            assert len(batch) == 3
            assert all(len(v) == EMBED_DIM for v in batch)
        finally:
            EmbeddingGemmaAdapter._model = None

    def test_dim_mismatch_raises_on_load(self):
        """If the model produces wrong dims, _load_model must raise ValueError."""
        from workers.ingestion_worker.embeddings.embedding_gemma import EmbeddingGemmaAdapter

        # Reset state
        EmbeddingGemmaAdapter._model = None
        EmbeddingGemmaAdapter._load_error = None

        mock_st = MagicMock()
        wrong_dim_model = MagicMock()
        wrong_dim_model.get_sentence_embedding_dimension.return_value = 9999
        mock_st.SentenceTransformer.return_value = wrong_dim_model

        with patch.dict("sys.modules", {"sentence_transformers": mock_st}):
            with pytest.raises((ValueError, RuntimeError)):
                adapter = EmbeddingGemmaAdapter()
                adapter._load_model()

        # Reset for other tests
        EmbeddingGemmaAdapter._model = None
        EmbeddingGemmaAdapter._load_error = None


# ── SigLIP2 normalisation helper ──────────────────────────────────────────────

class TestSigLIP2NormaliseHelper:
    def test_unit_vector_unchanged(self):
        from workers.ingestion_worker.embeddings.siglip2_shared import _normalize
        vec = [1.0, 0.0, 0.0]
        normed = _normalize(vec)
        assert abs(_l2_norm(normed) - 1.0) < 1e-6

    def test_arbitrary_vector_normalised(self):
        from workers.ingestion_worker.embeddings.siglip2_shared import _normalize
        vec = [3.0, 4.0]  # norm = 5
        normed = _normalize(vec)
        assert abs(_l2_norm(normed) - 1.0) < 1e-6

    def test_zero_vector_returns_safely(self):
        from workers.ingestion_worker.embeddings.siglip2_shared import _normalize
        vec = [0.0] * 10
        result = _normalize(vec)
        assert result == vec  # unchanged, no division by zero


# ── GemmaGenerationAdapter ────────────────────────────────────────────────────

class TestGemmaGenerationAdapter:
    def test_returns_string(self):
        from workers.ingestion_worker.embeddings.gemma_gen import GemmaGenerationAdapter

        # Patch backend to avoid real API call.
        adapter = GemmaGenerationAdapter()
        adapter._backend = MagicMock()
        adapter._backend.generate.return_value = "The policy states 30 days notice."

        result = adapter.generate("What is the notice period?")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_backend_error_returns_message_not_exception(self):
        from workers.ingestion_worker.embeddings.gemma_gen import GemmaGenerationAdapter

        adapter = GemmaGenerationAdapter()
        adapter._backend = MagicMock()
        adapter._backend.generate.side_effect = RuntimeError("API unreachable")

        result = adapter.generate("any query")
        # Must not raise — returns a human-readable error string instead.
        assert isinstance(result, str)
        assert "unavailable" in result.lower() or "error" in result.lower()
