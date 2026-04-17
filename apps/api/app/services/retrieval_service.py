"""
Retrieval service — hybrid semantic + lexical search.

Query flow:
  1. Classify query type (heuristic)
  2. Embed query (text + image-space) in thread executor (CPU-bound)
  3. Parallel: text vector search + image vector search + PG full-text
  4. Merge and rerank with query-type-aware weights
  5. Apply score threshold
  6. Return top-k results + query type label
"""
from __future__ import annotations

import asyncio
import logging
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

# Scoring weights for the default "hybrid" mode.
W_TEXT = 0.45
W_IMAGE = 0.30
W_LEXICAL = 0.15

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
        text_hits = await self._vector_search_text(text_embedding, top_k_text, filters)
        image_hits = await self._vector_search_image(image_embedding, top_k_image, filters)
        lexical_hits = await self._lexical_search(query, top_k_text, filters)

        merged = self._merge_and_rerank(
            text_hits, image_hits, lexical_hits, top_k_final, query_type
        )

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
            "Search done: type=%s hits=(text=%d img=%d lex=%d) final=%d latency=%dms",
            query_type,
            len(text_hits),
            len(image_hits),
            len(lexical_hits),
            len(merged),
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
                if score_f < image_threshold:
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

    def _merge_and_rerank(
        self,
        text_hits: list,
        image_hits: list,
        lexical_hits: list,
        top_k_final: int,
        query_type: str,
    ) -> list:
        # Adjust weights by query type.
        w_text = W_TEXT
        w_image = W_IMAGE
        if query_type == "image":
            w_text, w_image = 0.15, 0.60
        elif query_type in ("summary", "compare"):
            w_text, w_image = 0.60, 0.10

        scored: dict[str, dict] = {}

        def _key(item: Any) -> str:
            if hasattr(item, "imageId"):
                return f"img:{item.imageId}"
            # For text chunks, key on fileId + snippet prefix for dedup.
            return f"txt:{item.fileId}:{getattr(item, 'snippet', '')[:50]}"

        def _upsert(item: Any, weight: float) -> None:
            k = _key(item)
            if k not in scored:
                scored[k] = {"item": item, "final_score": 0.0}
            scored[k]["final_score"] += weight * item.score

        for hit in text_hits:
            _upsert(hit, w_text)
        for hit in image_hits:
            _upsert(hit, w_image)
        for hit in lexical_hits:
            _upsert(hit, W_LEXICAL)

        ranked = sorted(scored.values(), key=lambda x: x["final_score"], reverse=True)

        results = []
        for entry in ranked[:top_k_final]:
            item = entry["item"]
            item.score = round(entry["final_score"], 4)
            results.append(item)
        return results
