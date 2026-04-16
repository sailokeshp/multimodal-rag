"""Unit tests for the retrieval merge/rerank logic (no DB required)."""
import pytest

from app.schemas.search import DocumentChunkResult, ImageResult


def _make_chunk(file_id: str, snippet: str, score: float) -> DocumentChunkResult:
    return DocumentChunkResult(
        fileId=file_id, fileName="doc.pdf", snippet=snippet, score=score
    )


def _make_image(file_id: str, image_id: str, score: float) -> ImageResult:
    return ImageResult(
        fileId=file_id, fileName="img.png", imageId=image_id, score=score
    )


class TestMergeAndRerank:
    def _get_merger(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.services.retrieval_service import RetrievalService
        db = MagicMock()
        db.add = MagicMock()
        svc = RetrievalService(db)
        return svc

    def test_empty_inputs_return_empty(self):
        svc = self._get_merger()
        result = svc._merge_and_rerank([], [], [], 10, "hybrid")
        assert result == []

    def test_text_hits_appear_in_output(self):
        svc = self._get_merger()
        chunks = [_make_chunk("f1", "alpha content", 0.9)]
        result = svc._merge_and_rerank(chunks, [], [], 10, "hybrid")
        assert len(result) == 1
        assert result[0].snippet == "alpha content"

    def test_image_hits_appear_in_output(self):
        svc = self._get_merger()
        images = [_make_image("f2", "img-001", 0.8)]
        result = svc._merge_and_rerank([], images, [], 10, "image")
        assert len(result) == 1
        assert hasattr(result[0], "imageId")

    def test_top_k_is_respected(self):
        svc = self._get_merger()
        chunks = [_make_chunk("f1", f"content {i}", 0.5 + i * 0.01) for i in range(20)]
        result = svc._merge_and_rerank(chunks, [], [], 5, "hybrid")
        assert len(result) <= 5

    def test_higher_score_ranked_first(self):
        svc = self._get_merger()
        low = _make_chunk("f1", "low score content", 0.3)
        high = _make_chunk("f2", "high score content", 0.9)
        result = svc._merge_and_rerank([low, high], [], [], 10, "hybrid")
        assert result[0].snippet == "high score content"

    def test_duplicate_snippets_merged(self):
        """Same chunk appearing in text and lexical results should deduplicate."""
        svc = self._get_merger()
        snippet = "exactly the same text snippet here"
        text_hit = _make_chunk("f1", snippet, 0.8)
        lex_hit = _make_chunk("f1", snippet, 0.6)
        result = svc._merge_and_rerank([text_hit], [], [lex_hit], 10, "hybrid")
        assert len(result) == 1

    def test_image_query_type_boosts_images(self):
        """For query_type=image, image results should outscore equal-quality text."""
        svc = self._get_merger()
        chunk = _make_chunk("f1", "some text", 1.0)
        image = _make_image("f2", "img-002", 1.0)
        result = svc._merge_and_rerank([chunk], [image], [], 10, "image")
        # With image weights (text=0.15, image=0.60), image should rank first
        assert hasattr(result[0], "imageId")

    def test_query_classification_text_query(self):
        svc = self._get_merger()
        assert svc._classify_query("find termination policy document") == "hybrid"

    def test_query_classification_image_query(self):
        svc = self._get_merger()
        assert svc._classify_query("show me the org chart diagram") == "image"

    def test_query_classification_summary_query(self):
        svc = self._get_merger()
        assert svc._classify_query("summarize all the uploaded documents") == "summary"

    def test_query_classification_compare_query(self):
        svc = self._get_merger()
        assert svc._classify_query("compare the two policies") == "compare"
