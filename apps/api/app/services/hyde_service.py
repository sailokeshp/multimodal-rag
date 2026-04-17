"""
HyDE — Hypothetical Document Embedding  (NirDiamant/rag_techniques #8)

Problem this solves:
  A user asks: "What were the Q3 revenue figures?"
  The query embedding sits in the "question" region of the vector space.
  The relevant passage "Revenue for Q3 was $45M, up 23% YoY…" sits in the
  "answer / document" region.  These two regions are NOT the same, so the
  query embedding may be far from the passage embedding even though they are
  semantically related.

HyDE bridge:
  1. Ask the LLM to *generate* a plausible short answer document for the query.
  2. Embed that *hypothetical* document → it lives in the "document" region.
  3. Use this embedding (or an average with the original query embedding) for retrieval.
  4. The hypothetical document is never shown to the user — it is only used as
     an embedding anchor.

Reference:
  Gao et al., 2022 — "Precise Zero-Shot Dense Retrieval without Relevance Labels"
  https://arxiv.org/abs/2212.10496
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_HYDE_PROMPT = """\
Write a concise document passage (50-100 words) that directly answers the question below.
Write as if you are an expert author whose passage would be retrieved to answer the question.
Do NOT start with "The answer is" or refer to the question — just write the passage.

Question: {query}

Passage:"""


class HyDEService:
    def generate_hypothetical_document(self, query: str) -> str | None:
        """
        Generate a short hypothetical document passage that would answer the query.
        Returns None if generation fails (graceful fallback to standard retrieval).
        """
        try:
            from workers.ingestion_worker.embeddings.gemma_gen import (
                GemmaGenerationAdapter,
            )
            prompt = _HYDE_PROMPT.format(query=query)
            result = GemmaGenerationAdapter().generate(prompt)
            if result and len(result.strip()) > 20:
                logger.debug("HyDE generated %d chars for query: %r", len(result), query[:60])
                return result.strip()
            return None
        except Exception as exc:
            logger.warning("HyDE generation failed (using original query): %s", exc)
            return None

    def blend_embeddings(
        self,
        query_embedding: list[float],
        hyde_embedding: list[float],
        hyde_weight: float = 0.5,
    ) -> list[float]:
        """
        Blend the original query embedding and the HyDE embedding.

        A 50/50 blend balances two signals:
          - Original query embedding: captures the user's intent precisely
          - HyDE embedding: captures the "document space" of the answer

        This is typically better than using either alone.
        """
        import math
        blended = [
            (1.0 - hyde_weight) * q + hyde_weight * h
            for q, h in zip(query_embedding, hyde_embedding)
        ]
        # Re-normalise so cosine similarity remains valid
        norm = math.sqrt(sum(x * x for x in blended))
        if norm < 1e-9:
            return query_embedding
        return [x / norm for x in blended]
