"""
Page summary generator.

Calls the generation adapter to produce a short retrieval-oriented summary.
Falls back to first-N-chars truncation when the model is unavailable.

Note: prompt is defined inline here (not imported from app.prompts) so that
this module is usable both inside the API process and in the standalone worker
process without requiring the `app` package on sys.path.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

FALLBACK_SUMMARY_CHARS = 800

_PAGE_SUMMARY_PROMPT = """\
Summarize this page for retrieval.
Focus on topics, entities, obligations, deadlines, policy names, and any \
visible chart or figure mentions.
Keep it short (2-4 sentences) and searchable.
Do not add headings or bullet points.

Page content:
{content}

Summary:"""


def summarize_page(page_text: str, page_number: int) -> str:
    """
    Generate a retrieval-oriented summary for a document page.

    Returns empty string for empty pages.
    Falls back to truncated text when generation is unavailable.
    """
    if not page_text.strip():
        return ""

    try:
        from workers.ingestion_worker.embeddings.gemma_gen import GemmaGenerationAdapter

        adapter = GemmaGenerationAdapter()
        prompt = _PAGE_SUMMARY_PROMPT.format(content=page_text[:3000])
        summary = adapter.generate(prompt)

        # If generation returned an error placeholder, fall back to truncation.
        if summary.startswith("["):
            raise ValueError(summary)

        logger.debug("Page %d summary generated (%d chars)", page_number, len(summary))
        return summary.strip()

    except Exception as exc:
        logger.warning(
            "Page %d summary unavailable (%s) — using truncation fallback", page_number, exc
        )
        return page_text[:FALLBACK_SUMMARY_CHARS].strip()
