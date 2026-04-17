"""
Retrieval service — hybrid semantic + lexical search.

Query flow:
  1. Classify query type (heuristic)
  2. Embed query (text + image-space) in thread executor (CPU-bound)
  3. Parallel: text vector search + image vector search + PG full-text
  4. RRF merge — rank-position fusion (replaces raw-score weighted average)
  5. Cross-encoder rerank (stage 2 precision)
  6. Document diversity filter — max N results per source file
  7. Return top-k results + query type label
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import DocumentChunk, File, Image, SearchLog
from app.schemas.search import DocumentChunkResult, ImageResult, SearchFilters
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)
settings = get_settings()

# RRF k-constant: dampens the rank-1 advantage.
# k=60 is the value from the original Cormack & Clarke paper and is widely used.
_RRF_K = 60

# Shared thread-pool for CPU-bound embedding calls.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embed")


class RetrievalService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def search(
        self,
        query: str,
        top_k_text: int,
        top_k_image: int,
        top_k_final: int,
        filters: SearchFilters,
    ) -> tuple[list[Any], str]:
        t0 = time.monotonic()
        loop = asyncio.get_event_loop()

        query_type = self._classify_query(query)

        # When reranking is enabled, over-fetch candidates so the cross-encoder
        # has a richer pool to re-score. The multiplier is configurable.
        fetch_multiplier = settings.rerank_fetch_multiplier if settings.enable_reranking else 1
        fetch_k_text  = top_k_text  * fetch_multiplier
        fetch_k_image = top_k_image * fetch_multiplier

        image_embedding_future = loop.create_future()
        image_embedding_future.set_result(None)
        if self._should_embed_image_query(query_type):
            image_embedding_future = loop.run_in_executor(
                _executor, self._embed_image_query, query
            )

        # Run CPU-bound embedding in thread pool so the event loop stays free.
        text_embedding, image_embedding = await asyncio.gather(
            loop.run_in_executor(_executor, self._embed_text, query),
            image_embedding_future,
        )

        # SQLAlchemy AsyncSession does not permit concurrent execute() calls on
        # the same session while provisioning/using a connection, so keep the
        # DB-bound retrieval passes sequential for stability.
        text_hits   = await self._vector_search_text(text_embedding, fetch_k_text, filters)
        image_hits  = await self._vector_search_image(image_embedding, fetch_k_image, filters)
        lexical_hits = await self._lexical_search(query, top_k_text, filters)

        # Stage 1: RRF merge — combines three retrieval channels by rank position,
        # not raw score.  Rank position is meaningful across heterogeneous channels
        # (cosine similarity, image cosine, BM25) where raw scores are NOT comparable.
        merged = self._merge_rrf(
            text_hits, image_hits, lexical_hits,
            top_k_final * fetch_multiplier,   # keep a wider pool for the reranker
            query_type,
        )

        # Stage 2: cross-encoder rerank → final top_k_final
        if settings.enable_reranking and merged:
            from app.services.rerank_service import RerankService
            reranker = RerankService()
            merged = await loop.run_in_executor(
                _executor,
                lambda: reranker.rerank(query, merged, top_k_final),
            )
        else:
            merged = merged[:top_k_final]

        # Stage 3: document diversity filter — cap results per source file
        if settings.diversity_max_per_file > 0:
            merged = self._apply_diversity_filter(merged, settings.diversity_max_per_file)

        latency_ms = int((time.monotonic() - t0) * 1000)
        self.db.add(
            SearchLog(
                query_text=query,
                query_type=query_type,
                result_count=len(merged),
                latency_ms=latency_ms,
            )
        )
        logger.info(
            "Search done: type=%s hits=(text=%d img=%d lex=%d) "
            "merged=%d final=%d reranked=%s latency=%dms",
            query_type,
            len(text_hits), len(image_hits), len(lexical_hits),
            len(text_hits) + len(image_hits) + len(lexical_hits),
            len(merged),
            settings.enable_reranking,
            latency_ms,
        )
        return merged, query_type

    # ── Query classification ──────────────────────────────────────────────────

    def _classify_query(self, query: str) -> str:
        """
        Keyword heuristic classifier.
        Gemma-based classifier can replace this in Phase 3.
        """
        q = query.lower()
        # Use word-level matching to avoid substring false positives
        # e.g. "men" must not match inside "documents", "red" inside "shredded".
        words = set(q.split())
        image_kw = {
            # Explicit visual intent
            "image", "photo", "picture", "chart", "diagram", "graph",
            "figure", "logo", "illustration", "screenshot", "visual",
            "thumbnail", "icon", "banner", "poster",
            # People / body
            "woman", "women", "man", "men", "person", "people",
            "girl", "boy", "model", "athlete", "face",
            # Clothing / fashion / appearance
            "wearing", "dressed", "outfit", "clothes", "clothing",
            "shirt", "shorts", "pants", "dress", "jacket", "coat",
            "shoes", "hat", "bag", "fashion", "sportswear",
            "uniform", "jersey", "swimwear", "suit",
            # Colors (only as standalone words)
            "color", "colour", "pattern", "stripe",
            # Scene / environment
            "scene", "outdoor", "indoor", "background", "landscape",
            "sky", "studio", "nature",
            # Products / visual action
            "product", "display",
        }
        summary_kw = {
            "summarize", "summary", "overview", "describe all",
            "list all", "what is in", "give me an overview",
        }
        compare_kw = {"compare", "difference", "vs", "versus", "contrast", "which is"}

        # word-level check for single-word keywords; substring for multi-word phrases
        single_word_image = {k for k in image_kw if " " not in k}
        multi_word_image = {k for k in image_kw if " " in k}
        if (words & single_word_image) or any(k in q for k in multi_word_image):
            return "image"
        if any(k in q for k in summary_kw):
            return "summary"
        if any(k in q for k in compare_kw):
            return "compare"
        return "hybrid"

    # ── Embedding helpers (synchronous — run in executor) ─────────────────────

    def _embed_text(self, query: str) -> list[float] | None:
        if not settings.enable_text_embeddings:
            return None
        try:
            from workers.ingestion_worker.embeddings.embedding_gemma import (
                EmbeddingGemmaAdapter,
            )
            return EmbeddingGemmaAdapter().embed_text(query, is_query=True)
        except Exception as exc:
            logger.warning("Text embedding unavailable: %s", exc)
            return None

    def _embed_image_query(self, query: str) -> list[float] | None:
        if not settings.enable_image_embeddings:
            return None
        try:
            from workers.ingestion_worker.embeddings.siglip2_text import (
                SigLIP2TextAdapter,
            )
            return SigLIP2TextAdapter().embed_text(query)
        except Exception as exc:
            logger.warning("Image-query embedding unavailable: %s", exc)
            return None

    def _should_embed_image_query(self, query_type: str) -> bool:
        if not settings.enable_image_embeddings:
            return False
        if settings.image_query_embed_policy == "always":
            return True
        return query_type == "image"

    # ── Vector searches ───────────────────────────────────────────────────────

    async def _vector_search_text(
        self,
        embedding: list[float] | None,
        top_k: int,
        filters: SearchFilters,
    ) -> list[DocumentChunkResult]:
        if embedding is None:
            return []
        try:
            q = (
                select(
                    DocumentChunk,
                    File.file_name,
                    (
                        1 - DocumentChunk.embedding.cosine_distance(embedding)
                    ).label("score"),
                )
                .join(File, File.id == DocumentChunk.file_id)
                .where(DocumentChunk.embedding.isnot(None))
                # Exclude image_caption chunks — they are already surfaced as
                # ImageResult via SigLIP2 vector search.  Including them in
                # text search creates duplicate results and false positives
                # when caption words happen to match unrelated queries.
                .where(DocumentChunk.chunk_type != "image_caption")
                .order_by(DocumentChunk.embedding.cosine_distance(embedding))
                .limit(top_k)
            )
            if filters.fileTypes:
                q = q.where(File.file_type.in_(filters.fileTypes))

            rows = (await self.db.execute(q)).all()
            results = []
            for chunk, file_name, score in rows:
                score_f = float(score)
                if score_f < settings.retrieval_score_threshold:
                    continue
                results.append(
                    DocumentChunkResult(
                        fileId=str(chunk.file_id),
                        fileName=file_name,
                        pageStart=chunk.page_start,
                        pageEnd=chunk.page_end,
                        snippet=chunk.content[:600],
                        score=round(score_f, 4),
                    )
                )
            return results
        except Exception as exc:
            logger.error("Text vector search failed: %s", exc, exc_info=True)
            return []

    async def _vector_search_image(
        self,
        embedding: list[float] | None,
        top_k: int,
        filters: SearchFilters,
    ) -> list[ImageResult]:
        if embedding is None:
            return []
        try:
            q = (
                select(
                    Image,
                    File.file_name,
                    (1 - Image.embedding.cosine_distance(embedding)).label("score"),
                )
                .join(File, File.id == Image.file_id)
                .where(Image.embedding.isnot(None))
                .order_by(Image.embedding.cosine_distance(embedding))
                .limit(top_k)
            )
            if filters.fileTypes:
                q = q.where(File.file_type.in_(filters.fileTypes))

            rows = (await self.db.execute(q)).all()
            results = []
            # SigLIP2 cross-modal scores are typically lower than same-modal
            # text scores, so apply a more lenient threshold for image results.
            image_threshold = min(settings.retrieval_score_threshold, 0.20)
            storage = StorageService()
            for image, file_name, score in rows:
                score_f = float(score)
                # NaN/Inf arise when the stored embedding is a zero vector
                # (pgvector: cosine_distance(zero, v) = undefined).
                # NaN comparisons always return False in Python so they would
                # bypass the threshold check — guard against that explicitly.
                if not math.isfinite(score_f) or score_f < image_threshold:
                    continue
                thumb_url = None
                if image.thumbnail_s3_key:
                    try:
                        thumb_url = storage.generate_presigned_get_url(
                            image.thumbnail_s3_key, expires_in=3600
                        )
                    except Exception as exc:
                        logger.warning("Failed to generate presigned URL for %s: %s", image.thumbnail_s3_key, exc)
                results.append(
                    ImageResult(
                        fileId=str(image.file_id),
                        fileName=file_name,
                        imageId=str(image.id),
                        thumbnailUrl=thumb_url,
                        caption=image.caption_text,
                        score=round(score_f, 4),
                    )
                )
            return results
        except Exception as exc:
            logger.error("Image vector search failed: %s", exc, exc_info=True)
            return []

    async def _lexical_search(
        self,
        query: str,
        top_k: int,
        filters: SearchFilters,
    ) -> list[DocumentChunkResult]:
        try:
            q = (
                select(
                    DocumentChunk,
                    File.file_name,
                    text(
                        "ts_rank_cd("
                        "  to_tsvector('english', document_chunks.content),"
                        "  plainto_tsquery('english', :q)"
                        ") AS score"
                    ),
                )
                .join(File, File.id == DocumentChunk.file_id)
                .where(
                    text(
                        "to_tsvector('english', document_chunks.content) "
                        "@@ plainto_tsquery('english', :q)"
                    )
                )
                .where(DocumentChunk.chunk_type != "image_caption")
                .order_by(text("score DESC"))
                .limit(top_k)
                .params(q=query)
            )
            if filters.fileTypes:
                q = q.where(File.file_type.in_(filters.fileTypes))

            rows = (await self.db.execute(q)).all()
            return [
                DocumentChunkResult(
                    fileId=str(chunk.file_id),
                    fileName=file_name,
                    pageStart=chunk.page_start,
                    pageEnd=chunk.page_end,
                    snippet=chunk.content[:600],
                    score=round(float(score), 4),
                )
                for chunk, file_name, score in rows
            ]
        except Exception as exc:
            logger.error("Lexical search failed: %s", exc, exc_info=True)
            return []

    # ── Merge and rerank ──────────────────────────────────────────────────────

    def _merge_rrf(
        self,
        text_hits: list,
        image_hits: list,
        lexical_hits: list,
        top_k: int,
        query_type: str,
    ) -> list:
        """
        Reciprocal Rank Fusion (RRF) across three retrieval channels.

        Formula:  score(d) = Σ_channel  w_channel / (k + rank_in_channel)

        Why RRF beats weighted raw-score averaging:
        - Cosine similarity, image cosine, and BM25 scores live on different scales.
          Averaging them is mathematically unsound — a 0.9 text score averaged
          with a 0.3 image score buries the strong text signal.
        - Rank *position* is meaningful and comparable across all channels:
          rank-1 in any channel means "best match in that channel."
        - k=60 dampens the rank-1 advantage — proven optimal in the original
          Cormack & Clarke (2009) paper and confirmed across many IR benchmarks.

        Reference: Cormack, G.V., Clarke, C.L.A., Buettcher, S. (2009).
        "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods."
        """
        # Channel weights vary by query intent
        if query_type == "image":
            w_text, w_image, w_lex = 0.15, 0.60, 0.25
        elif query_type in ("summary", "compare"):
            w_text, w_image, w_lex = 0.60, 0.10, 0.30
        else:  # hybrid (default)
            w_text, w_image, w_lex = 0.45, 0.30, 0.25

        rrf_scores: dict[str, dict] = {}

        def _key(item: Any) -> str:
            if hasattr(item, "imageId"):
                return f"img:{item.imageId}"
            return f"txt:{item.fileId}:{getattr(item, 'snippet', '')[:50]}"

        def _apply_channel(hits: list, weight: float) -> None:
            for rank, hit in enumerate(hits, start=1):
                k = _key(hit)
                if k not in rrf_scores:
                    rrf_scores[k] = {"item": hit, "score": 0.0}
                rrf_scores[k]["score"] += weight / (_RRF_K + rank)

        _apply_channel(text_hits, w_text)
        _apply_channel(image_hits, w_image)
        _apply_channel(lexical_hits, w_lex)

        ranked = sorted(rrf_scores.values(), key=lambda x: x["score"], reverse=True)

        # Normalise to [0, 1] so score display remains intuitive downstream
        if ranked:
            max_score = ranked[0]["score"]
            if max_score > 0:
                for entry in ranked:
                    entry["score"] /= max_score

        results = []
        for entry in ranked[:top_k]:
            item = entry["item"]
            item.score = round(entry["score"], 4)
            results.append(item)
        return results

    def _apply_diversity_filter(self, results: list, max_per_file: int) -> list:
        """
        Limit results to max_per_file entries per source document.

        Without this, a large document with many similar chunks can fill every
        slot in the top-K results — meaning the user never sees relevant content
        from other uploaded documents.  Critical for multi-document RAG.

        Applied after reranking so the cross-encoder's quality signal determines
        *which* chunks from each file are kept, not which files are kept.
        """
        seen: dict[str, int] = {}
        filtered = []
        for item in results:
            file_id = item.fileId
            count = seen.get(file_id, 0)
            if count < max_per_file:
                filtered.append(item)
                seen[file_id] = count + 1
        if len(filtered) < len(results):
            logger.debug(
                "Diversity filter: %d → %d results (max %d per file)",
                len(results), len(filtered), max_per_file,
            )
        return filtered
