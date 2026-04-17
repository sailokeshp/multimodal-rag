"""
Image captioning via Groq Vision (llama-3.2-11b-vision-preview).

Generates a rich text description of an image at ingest time.
The caption is stored as a DocumentChunk so it is:
  - Searchable via text vector search (BGE)
  - Passed to the generation LLM as grounded context (closes the RAG loop)

Without captions, image-only assets produce zero text context for the LLM,
breaking the Augmented Generation step of RAG.
"""
from __future__ import annotations

import base64
import logging

logger = logging.getLogger(__name__)

_CAPTION_PROMPT = (
    "Describe this image in detail for a semantic search index. "
    "Include: people (gender, clothing colors, style, activity), "
    "objects, setting/background, and any notable visual elements. "
    "Be specific and factual. Keep it under 150 words."
)


def generate_caption(image_bytes: bytes, groq_api_key: str) -> str | None:
    """
    Call Groq Vision to caption an image.
    Returns the caption string, or None if unavailable/disabled.
    """
    if not groq_api_key:
        return None
    try:
        from groq import Groq

        b64 = base64.b64encode(image_bytes).decode()
        # Detect rough MIME type from magic bytes
        mime = "image/jpeg"
        if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        elif image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
            mime = "image/webp"

        client = Groq(api_key=groq_api_key)
        response = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                        {"type": "text", "text": _CAPTION_PROMPT},
                    ],
                }
            ],
            max_tokens=200,
            temperature=0.2,
        )
        caption = response.choices[0].message.content.strip()
        logger.info("Caption generated (%d chars)", len(caption))
        return caption

    except Exception as exc:
        logger.warning("Caption generation failed (non-fatal): %s", exc)
        return None
