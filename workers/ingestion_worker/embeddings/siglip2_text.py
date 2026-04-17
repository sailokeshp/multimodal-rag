"""
SigLIP2 text encoder adapter.

Uses the TEXT encoder of the same google/siglip2-so400m-patch16-384
checkpoint to embed natural-language queries into the 1152-d cross-modal
space.  These query vectors are compared against image embeddings stored
in the DB, enabling image retrieval from text queries.

Output dimension: 1152 (same space as SigLIP2ImageAdapter)
"""
from __future__ import annotations

import logging

from workers.ingestion_worker.embeddings.siglip2_shared import (
    EMBED_DIM,
    _normalize,
    get_model,
)

logger = logging.getLogger(__name__)


class SigLIP2TextAdapter:
    def embed_text(self, text: str) -> list[float]:
        """
        Embed a text string using the SigLIP2 text encoder.
        Returns an L2-normalised 1152-d vector.
        Falls back to zero vector if the model is unavailable.
        """
        try:
            import torch

            processor, model = get_model()

            # SigLIP2 has a fixed max token length — truncate gracefully.
            inputs = processor(
                text=[text],
                return_tensors="pt",
                padding="max_length",
                truncation=True,
            )
            device = next(model.parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}

            with torch.no_grad():
                out = model.get_text_features(**inputs)

            if isinstance(out, torch.Tensor):
                feat = out
            elif hasattr(out, 'text_embeds') and out.text_embeds is not None:
                feat = out.text_embeds
            elif hasattr(out, 'pooler_output') and out.pooler_output is not None:
                feat = out.pooler_output
            else:
                feat = out[0]

            vec = feat.squeeze().cpu().float().tolist()
            if vec and isinstance(vec[0], (list, tuple)):
                vec = vec[0]
            return _normalize(vec)

        except Exception as exc:
            logger.error("SigLIP2 text embed failed: %s", exc, exc_info=True)
            return [0.0] * EMBED_DIM

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch encode — processes one at a time for simplicity."""
        return [self.embed_text(t) for t in texts]
