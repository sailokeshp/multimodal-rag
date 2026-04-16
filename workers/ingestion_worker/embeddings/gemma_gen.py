"""
Gemma generation adapter.

Three backends, selected via GEN_MODEL_BACKEND env var:

  "anthropic"  (recommended — best answer quality)
      Uses Claude via Anthropic API.
      Requires: pip install anthropic
      Requires: ANTHROPIC_API_KEY env var
      Model: configurable via GEN_MODEL_NAME (default: claude-haiku-4-5-20251001)

  "groq"
      Runs gemma2-9b-it on Groq's free API (14,400 req/day, no credit card).
      Requires: pip install groq
      Requires: GROQ_API_KEY env var
      Get a free key at: https://console.groq.com

  "google_ai"
      Uses the Google Gemini API (free tier, 1500 req/day).
      Requires: pip install google-genai
      Requires: GOOGLE_AI_API_KEY env var

  "local"
      Loads a Hugging Face model locally (requires ~4+ GB RAM).
      NOT suitable for EC2 t2.micro (1 GB RAM).
      Requires: pip install transformers torch accelerate

If no backend is available, a descriptive fallback message is returned
so the rest of the pipeline continues to work.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import ClassVar

logger = logging.getLogger(__name__)

_BACKEND = os.getenv("GEN_MODEL_BACKEND", "google_ai")
_GEN_MODEL_NAME = os.getenv("GEN_MODEL_NAME", "gemma2-9b-it")
_ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
_GOOGLE_AI_KEY = os.getenv("GOOGLE_AI_API_KEY", "")
_GOOGLE_AI_MODEL = os.getenv("GOOGLE_AI_MODEL", "gemini-2.0-flash")
MAX_NEW_TOKENS = int(os.getenv("GEN_MAX_TOKENS", "512"))

_lock = threading.Lock()


# ─── Anthropic (Claude) backend ──────────────────────────────────────────────

class _AnthropicBackend:
    _client: ClassVar = None
    _error: ClassVar[str | None] = None

    def _load(self) -> None:
        if _AnthropicBackend._client is not None:
            return
        if _AnthropicBackend._error:
            raise RuntimeError(_AnthropicBackend._error)

        with _lock:
            if _AnthropicBackend._client is not None:
                return
            try:
                import anthropic

                if not _ANTHROPIC_KEY:
                    raise ValueError(
                        "ANTHROPIC_API_KEY is not set. "
                        "Get a key at https://console.anthropic.com"
                    )
                _AnthropicBackend._client = anthropic.Anthropic(api_key=_ANTHROPIC_KEY)
                logger.info("Anthropic backend ready (model=%s)", _GEN_MODEL_NAME)
            except Exception as exc:
                _AnthropicBackend._error = str(exc)
                logger.error("Anthropic backend failed to init: %s", exc)
                raise

    def generate(self, prompt: str) -> str:
        self._load()
        msg = _AnthropicBackend._client.messages.create(
            model=_GEN_MODEL_NAME,
            max_tokens=MAX_NEW_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()


# ─── Groq backend (gemma2-9b-it, free tier) ──────────────────────────────────

class _GroqBackend:
    _client: ClassVar = None
    _error: ClassVar[str | None] = None

    def _load(self) -> None:
        if _GroqBackend._client is not None:
            return
        if _GroqBackend._error:
            raise RuntimeError(_GroqBackend._error)

        with _lock:
            if _GroqBackend._client is not None:
                return
            try:
                from groq import Groq  # pip install groq

                if not _GROQ_API_KEY:
                    raise ValueError(
                        "GROQ_API_KEY is not set. "
                        "Get a free key (no credit card) at https://console.groq.com"
                    )
                _GroqBackend._client = Groq(api_key=_GROQ_API_KEY)
                logger.info("Groq backend ready (model=%s)", _GEN_MODEL_NAME)
            except Exception as exc:
                _GroqBackend._error = str(exc)
                logger.error("Groq backend failed to init: %s", exc)
                raise

    def generate(self, prompt: str) -> str:
        self._load()
        resp = _GroqBackend._client.chat.completions.create(
            model=_GEN_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_NEW_TOKENS,
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()


# ─── Google AI (Gemini) backend ───────────────────────────────────────────────

class _GoogleAIBackend:
    _client: ClassVar = None
    _error: ClassVar[str | None] = None

    def _load(self) -> None:
        if _GoogleAIBackend._client is not None:
            return
        if _GoogleAIBackend._error:
            raise RuntimeError(_GoogleAIBackend._error)

        with _lock:
            if _GoogleAIBackend._client is not None:
                return
            try:
                from google import genai
                from google.genai import types as genai_types

                if not _GOOGLE_AI_KEY:
                    raise ValueError(
                        "GOOGLE_AI_API_KEY is not set. "
                        "Get a free key at https://aistudio.google.com/app/apikey"
                    )
                client = genai.Client(api_key=_GOOGLE_AI_KEY)
                _GoogleAIBackend._client = client
                logger.info("Google AI (genai) backend ready (model=%s)", _GOOGLE_AI_MODEL)
            except Exception as exc:
                _GoogleAIBackend._error = str(exc)
                logger.error("Google AI backend failed to init: %s", exc)
                raise

    def generate(self, prompt: str) -> str:
        self._load()
        from google.genai import types as genai_types

        resp = _GoogleAIBackend._client.models.generate_content(
            model=_GOOGLE_AI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.1,  # low temp for factual grounded answers
                max_output_tokens=MAX_NEW_TOKENS,
            ),
        )
        return resp.text.strip()


# ─── HuggingFace local backend ────────────────────────────────────────────────

class _LocalHFBackend:
    _pipeline: ClassVar = None
    _error: ClassVar[str | None] = None

    def _load(self) -> None:
        if _LocalHFBackend._pipeline is not None:
            return
        if _LocalHFBackend._error:
            raise RuntimeError(_LocalHFBackend._error)

        with _lock:
            if _LocalHFBackend._pipeline is not None:
                return
            try:
                import torch
                from transformers import pipeline, AutoTokenizer

                device = 0 if torch.cuda.is_available() else -1
                dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32

                logger.info(
                    "Loading local generation model: %s on %s…",
                    _GEN_MODEL_NAME,
                    "GPU" if device == 0 else "CPU",
                )
                tok = AutoTokenizer.from_pretrained(_GEN_MODEL_NAME)
                pipe = pipeline(
                    "text-generation",
                    model=_GEN_MODEL_NAME,
                    tokenizer=tok,
                    torch_dtype=dtype,
                    device=device,
                )
                _LocalHFBackend._pipeline = pipe
                logger.info("Local generation model loaded: %s", _GEN_MODEL_NAME)
            except Exception as exc:
                _LocalHFBackend._error = str(exc)
                logger.error("Local generation model failed to load: %s", exc, exc_info=True)
                raise

    def generate(self, prompt: str) -> str:
        self._load()
        output = _LocalHFBackend._pipeline(
            prompt,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            temperature=None,
            top_p=None,
            pad_token_id=_LocalHFBackend._pipeline.tokenizer.eos_token_id,
        )
        full_text: str = output[0]["generated_text"]
        # Strip the prompt prefix from the output.
        if full_text.startswith(prompt):
            return full_text[len(prompt):].strip()
        return full_text.strip()


# ─── Public adapter ───────────────────────────────────────────────────────────

class GemmaGenerationAdapter:
    """
    Backend-agnostic generation adapter.
    Use GEN_MODEL_BACKEND=google_ai (default) or local.
    """

    def __init__(self) -> None:
        if _BACKEND == "local":
            self._backend = _LocalHFBackend()
        elif _BACKEND == "google_ai":
            self._backend = _GoogleAIBackend()
        else:  # "groq" remains supported as an explicit opt-in backend
            self._backend = _GroqBackend()

    def generate(self, prompt: str) -> str:
        try:
            return self._backend.generate(prompt)
        except Exception as exc:
            logger.error("Generation failed (%s backend): %s", _BACKEND, exc)
            return (
                f"[Answer generation unavailable — {_BACKEND} backend error: {exc}. "
                "Retrieved results are shown above.]"
            )
