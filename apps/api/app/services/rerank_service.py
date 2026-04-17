"""
Cross-encoder reranking service.

Why reranking matters:
  Bi-encoder vector search (BGE/SigLIP2) retrieves by approximate similarity.
  It's fast but imprecise — the top-20 candidates often include irrelevant passages
  that happen to be near the query in embedding space.

  A cross-encoder reads (query, passage) together, attending to the full interaction.
  It assigns a relevance score much closer to what an LLM would judge as "useful".
  Reranking the top-N bi-encoder candidates with a cross-encoder typically improves
  NDCG@10 by 10-25% on document retrieval benchmarks.

Architecture:
  1. Retrieval (fast, approximate):  bi-encoder → top-K*3 candidates
  2. Reranking (slow, precise):      cross-encoder → top-K final results

Model: cross-encoder/ms-marco-MiniLM-L-6-v2
  - 6-layer MiniLM, ~66 MB, runs on CPU in ~50-200 ms for 10-20 passages
  - Trained on MS MARCO (100K passage relevance annotations)
  - State-of-the-art for passage reranking without a GPU
"""
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cross_encoder = None
_load_error: str | None = None


def _get_cross_encoder():
    global _cross_encoder, _load_error

    if _cross_encoder is not None:
        return _cross_encoder
    if _load_error:
        raise RuntimeError(f"Cross-encoder previously failed to load: {_load_error}")

    with _lock:
        if _cross_encoder is not None:
            return _cross_encoder

        try:
            from app.config import get_settings
            settings = get_settings()
            model_name = settings.rerank_model

            logger.info("Loading cross-encoder: %s…", model_name)
            from sentence_transformers import CrossEncoder
            _cross_encoder = CrossEncoder(model_name)
            logger.info("Cross-encoder loaded: %s", model_name)
            return _cross_encoder

        except Exception as exc:
            _load_error = str(exc)
            logger.error("Cross-encoder load failed: %s", exc, exc_info=True)
            raise


def _passage_text(result: Any) -> str:
    """Extract the best text representation from a search result for reranking."""
    if hasattr(result, "snippet") and result.snippet:
        # DocumentChunkResult — use section title + snippet for richer context
        prefix = getattr(result, "section_title", None)
        if prefix:
            return f"{prefix}. {result.snippet}"
        return result.snippet
    if hasattr(result, "caption") and result.caption:
        # ImageResult — use caption (AI-generated visual description)
        return result.caption
    # Fallback: file name only
    return result.fileName or ""


class RerankService:
    def rerank(
        self,
        query: str,
        results: list[Any],
        top_k: int,
    ) -> list[Any]:
        """
        Score (query, passage) pairs with a cross-encoder and return top_k.

        Scores are normalized to [0, 1] via sigmoid so they remain interpretable
        alongside the upstream bi-encoder scores.

        If the cross-encoder is unavailable, returns the original results unchanged.
        """
        if not results:
            return results

        try:
            model = _get_cross_encoder()
        except Exception:
            # Graceful degradation — fall back to bi-encoder ranking
            logger.warning(
                "Cross-encoder unavailable — returning bi-encoder ranking unchanged"
            )
            return results[:top_k]

        passages = [_passage_text(r) for r in results]
        pairs = [(query, p) for p in passages]

        try:
            import math
            raw_scores = model.predict(pairs, show_progress_bar=False)

            # Sigmoid normalisation: maps logit-scale scores to [0, 1]
            def _sigmoid(x: float) -> float:
                return 1.0 / (1.0 + math.exp(-float(x)))

            scored = sorted(
                zip(raw_scores, results),
                key=lambda t: float(t[0]),
                reverse=True,
            )

            reranked: list[Any] = []
            for raw_score, item in scored[:top_k]:
                item.score = round(_sigmoid(raw_score), 4)
                reranked.append(item)

            logger.info(
                "Reranked %d → %d candidates (top score=%.4f)",
                len(results), len(reranked),
                reranked[0].score if reranked else 0,
            )
            return reranked

        except Exception as exc:
            logger.error("Reranking failed: %s", exc, exc_info=True)
            return results[:top_k]
