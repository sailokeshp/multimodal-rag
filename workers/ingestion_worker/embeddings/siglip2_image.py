"""
SigLIP2 image embedding adapter.

Uses the image encoder of google/siglip2-so400m-patch16-384 to embed
raw image bytes into a 1152-d vector space shared with the text encoder.
This enables cross-modal similarity search (text query → image results).

Output dimension: 1152
Requires: transformers, torch, Pillow
"""
from __future__ import annotations

import io
import logging

from workers.ingestion_worker.embeddings.siglip2_shared import (
    EMBED_DIM,
    _normalize,
    get_model,
)

logger = logging.getLogger(__name__)


class SigLIP2ImageAdapter:
    def embed_image(self, image_bytes: bytes) -> list[float]:
        """
        Embed a single image from raw bytes.
        Returns an L2-normalised 1152-d vector.
        Falls back to zero vector if the model is unavailable.
        """
        try:
            import torch
            from PIL import Image

            processor, model = get_model()
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

            inputs = processor(images=img, return_tensors="pt")
            device = next(model.parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}

            with torch.no_grad():
                features = model.get_image_features(**inputs)

            vec = features[0].cpu().float().tolist()
            return _normalize(vec)

        except Exception as exc:
            logger.error("SigLIP2 image embed failed: %s", exc, exc_info=True)
            return [0.0] * EMBED_DIM

    def embed_batch(self, images: list[bytes]) -> list[list[float]]:
        """Batch encode images — processes one at a time for memory safety."""
        return [self.embed_image(img) for img in images]
