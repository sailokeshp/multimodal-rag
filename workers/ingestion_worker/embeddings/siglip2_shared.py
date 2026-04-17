"""
Shared SigLIP2 model singleton.

Both siglip2_image.py and siglip2_text.py import from here so the
~1.7 GB checkpoint is loaded exactly once per process.

Model: google/siglip2-so400m-patch16-384
Output dimension: 1152
"""
from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("IMAGE_EMBED_MODEL_NAME", "google/siglip2-so400m-patch16-384")
EMBED_DIM = int(os.getenv("IMAGE_EMBED_DIM", "1152"))

_lock = threading.Lock()
_processor = None
_model = None
_load_error: str | None = None


def get_model():
    """Return (processor, model) tuple, loading on first call. Thread-safe."""
    global _processor, _model, _load_error

    if _model is not None:
        return _processor, _model

    if _load_error is not None:
        raise RuntimeError(f"SigLIP2 previously failed to load: {_load_error}")

    with _lock:
        if _model is not None:
            return _processor, _model

        logger.info("Loading SigLIP2 model: %s (this may take a moment)…", MODEL_NAME)
        try:
            import torch
            try:
                from transformers import AutoProcessor, AutoModel
            except ImportError:
                # Older transformers versions may not export AutoProcessor/AutoModel
                # from the top-level namespace; fall back to the concrete classes.
                from transformers import SiglipProcessor as AutoProcessor, SiglipModel as AutoModel

            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info("SigLIP2 device: %s", device)

            proc = AutoProcessor.from_pretrained(MODEL_NAME)
            mdl = AutoModel.from_pretrained(MODEL_NAME)
            mdl.eval()
            mdl.to(device)

            _processor = proc
            _model = mdl
            logger.info("SigLIP2 model loaded (dim=%d, device=%s)", EMBED_DIM, device)
            return _processor, _model

        except Exception as exc:
            _load_error = str(exc)
            logger.error("SigLIP2 model load failed: %s", exc, exc_info=True)
            raise


def _normalize(vec: list[float]) -> list[float]:
    """L2-normalise a vector so cosine similarity = dot product."""
    import math
    norm = math.sqrt(sum(x * x for x in vec))
    if norm < 1e-9:
        return vec
    return [x / norm for x in vec]
