"""
Answer service — generates grounded answers from retrieved evidence.

Rules:
- Answer ONLY from retrieved context.
- Refuse to fabricate when evidence is insufficient.
- Always include source citations.
- Run generation in a thread executor (model inference is CPU-bound).
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gen")

_GROUNDED_ANSWER_PROMPT = """\
You are a retrieval-grounded assistant. Your task is to answer the user's \
question using ONLY the context below. Do not add information from outside \
the provided sources.

Rules:
- If the answer is clearly supported by the context, answer concisely.
- If the answer is partially supported, say so and cite only what you found.
- If the context does not contain enough information, say: \
"The uploaded documents do not contain enough information to answer this question."
- Always list the sources you used at the end under "Sources:".
- Do NOT invent file names, page numbers, or facts.

Context:
{context}

Question: {query}

Answer:"""


class AnswerService:
    async def generate(self, query: str, results: list[Any]) -> str:
        """Generate a grounded answer from retrieved search results."""
        context_blocks, citations = self._build_context(results)
        if not context_blocks:
            return "No relevant content was retrieved to answer this question."
        return await self._run_generation(query, context_blocks, citations)

    async def generate_from_context(self, query: str, context: list[str]) -> str:
        """Generate from caller-provided context strings (no result objects)."""
        return await self._run_generation(query, context, citations=None)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_context(
        self, results: list[Any]
    ) -> tuple[list[str], list[str]]:
        """
        Build context blocks and citation strings from mixed results.
        Deduplicates content that appears in multiple hits.
        """
        blocks: list[str] = []
        citations: list[str] = []
        seen_snippets: set[str] = set()

        for r in results:
            if hasattr(r, "snippet"):
                dedup_key = r.snippet[:120]
                if dedup_key in seen_snippets:
                    continue
                seen_snippets.add(dedup_key)

                if r.pageStart and r.pageEnd:
                    source_label = f"{r.fileName}, pages {r.pageStart}–{r.pageEnd}"
                else:
                    source_label = r.fileName

                blocks.append(f"[Source: {source_label}]\n{r.snippet}")
                if source_label not in citations:
                    citations.append(source_label)

            elif hasattr(r, "imageId"):
                source_label = f"{r.fileName} (image)"
                blocks.append(f"[Image source: {source_label}]")
                if source_label not in citations:
                    citations.append(source_label)

        return blocks, citations

    async def _run_generation(
        self,
        query: str,
        context_blocks: list[str],
        citations: list[str] | None,
    ) -> str:
        if not settings.enable_grounded_answer:
            return ""

        context_text = "\n\n".join(context_blocks)
        prompt = _GROUNDED_ANSWER_PROMPT.format(
            context=context_text, query=query
        )

        logger.info(
            "Generating answer: query=%r context_blocks=%d",
            query[:80],
            len(context_blocks),
        )

        loop = asyncio.get_event_loop()
        answer = await loop.run_in_executor(_executor, self._call_model, prompt)

        # Append citations if the model didn't include them naturally.
        if citations and "Sources:" not in answer:
            citation_block = "\n".join(f"- {c}" for c in citations)
            answer = f"{answer}\n\nSources:\n{citation_block}"

        return answer

    def _call_model(self, prompt: str) -> str:
        try:
            from workers.ingestion_worker.embeddings.gemma_gen import (
                GemmaGenerationAdapter,
            )
            return GemmaGenerationAdapter().generate(prompt)
        except Exception as exc:
            logger.error("Generation call failed: %s", exc)
            return (
                "Answer generation is currently unavailable. "
                "Retrieved results are shown above."
            )
