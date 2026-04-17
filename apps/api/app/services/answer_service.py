"""
Answer service — generates grounded answers from retrieved evidence.

Production-grade rules:
- Answer ONLY from retrieved context.  Never fabricate.
- Enforce a hard context-window budget so generation never OOMs / truncates.
- Structure the answer: direct response → supporting details → sources.
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

# Approximate chars per token for context budget calculation.
_CHARS_PER_TOKEN = 4

_GROUNDED_ANSWER_PROMPT = """\
You are a document analyst. The user has uploaded documents and asked a question. \
Your job is to read the retrieved document excerpts below and synthesise a \
direct, cited answer. Never add information not present in the sources.

Rules:
1. **Direct answer first** — open with 1-2 sentences that directly answer the \
   question.
2. **Support with evidence** — quote or paraphrase specific passages, always \
   citing the document and page (e.g. "According to report.pdf, page 3, …").
3. **Synthesise across sources** — if multiple documents contain relevant \
   information, integrate them into a coherent answer rather than listing them \
   separately.
4. **Admit gaps honestly** — if the context does not contain enough information, \
   say exactly: "The uploaded documents do not contain enough information to \
   answer this question."
5. **Never invent** — do not fabricate facts, page numbers, or file names.
6. **Sources section** — end every answer with a "Sources:" section that lists \
   each document + page you cited.

Retrieved document excerpts:
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

        Context window management:
          - Hard budget: settings.max_context_tokens
          - Results are already ranked by relevance — process in order
          - Once budget is exhausted, stop adding (don't truncate mid-sentence)
          - Image captions count toward budget (they can be verbose)

        Deduplication:
          - Skip blocks whose first 120 chars match a seen block
          - Prevents the same passage from appearing twice in the prompt
        """
        blocks: list[str] = []
        citations: list[str] = []
        seen_snippets: set[str] = set()
        tokens_used = 0
        max_tokens = settings.max_context_tokens

        for r in results:
            if hasattr(r, "snippet"):
                dedup_key = r.snippet[:120]
                if dedup_key in seen_snippets:
                    continue
                seen_snippets.add(dedup_key)

                if r.pageStart and r.pageEnd:
                    source_label = f"{r.fileName}, pages {r.pageStart}–{r.pageEnd}"
                elif r.pageStart:
                    source_label = f"{r.fileName}, page {r.pageStart}"
                else:
                    source_label = r.fileName

                block = f"[Source: {source_label}]\n{r.snippet}"

            elif hasattr(r, "imageId"):
                source_label = f"{r.fileName} (image)"
                caption = getattr(r, "caption", None)
                if caption:
                    block = f"[Image source: {source_label}]\nVisual description: {caption}"
                else:
                    block = f"[Image source: {source_label}]"
            else:
                continue

            block_tokens = len(block) // _CHARS_PER_TOKEN
            if tokens_used + block_tokens > max_tokens:
                logger.debug(
                    "Context budget reached at %d/%d tokens — stopping",
                    tokens_used, max_tokens,
                )
                break

            blocks.append(block)
            tokens_used += block_tokens
            if source_label not in citations:
                citations.append(source_label)

        logger.debug(
            "Context built: %d blocks, ~%d tokens (budget=%d)",
            len(blocks), tokens_used, max_tokens,
        )
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
            "Generating answer: query=%r context_blocks=%d context_tokens~=%d",
            query[:80],
            len(context_blocks),
            len(context_text) // _CHARS_PER_TOKEN,
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
