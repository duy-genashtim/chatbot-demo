"""Singleton Gemini API client for chatbotv2.

Lazy-initialised once at startup via init_client(). All modules call
get_client() — never instantiate genai.Client directly.
"""

from __future__ import annotations

import logging

from google import genai

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def init_client() -> genai.Client:
    """Create (or return) the process-level Gemini client.

    Called once from lifespan startup. Subsequent calls are no-ops.
    """
    global _client
    if _client is None:
        api_key = get_settings().GEMINI_API_KEY
        if not api_key:
            logger.warning("GEMINI_API_KEY not set — LLM calls will fail at runtime")
        _client = genai.Client(api_key=api_key)
        logger.info("GeminiClient initialised")
    return _client


def get_client() -> genai.Client:
    """Return the process-level Gemini client. Raises if not yet initialised."""
    if _client is None:
        # Fallback: lazy init (e.g. during tests or direct import)
        return init_client()
    return _client
