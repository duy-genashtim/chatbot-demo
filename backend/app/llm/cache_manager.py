"""Gemini explicit context cache lifecycle manager.

Provides get_or_create / invalidate for per-mode caches.
Gracefully skips caching when content is below the 1024-token minimum —
callers receive None and must fall back to inline system_instruction.
"""

from __future__ import annotations

import logging
from typing import Any

from google.genai import types

from app.core.config import get_settings
from app.llm.gemini_client import get_client

logger = logging.getLogger(__name__)

# Gemini explicit cache minimum (tokens). Below this threshold the API rejects
# the cache creation request; we skip gracefully and return None.
_CACHE_MIN_TOKENS = 1024


class CacheManager:
    """Manage Gemini CachedContent objects keyed by display_name.

    One instance is shared for the entire process (created in main.py lifespan).
    """

    def __init__(self) -> None:
        # display_name -> cache.name (resource name, e.g. "cachedContents/xxx")
        self._cache_names: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_or_create(
        self,
        display_name: str,
        system_instruction: str,
        contents: list[Any],
    ) -> str | None:
        """Return existing cache name or create a new one.

        Returns None if:
          - content is below the 1024-token minimum (caching not supported)
          - an API error occurs during creation

        Callers must handle None by passing system_instruction inline instead.
        """
        # 1. Check in-memory index first
        if display_name in self._cache_names:
            # Verify it still exists on the API side
            existing = self._find_existing(display_name)
            if existing:
                logger.debug("Cache hit: %s -> %s", display_name, existing.name)
                return existing.name
            # Cache expired or deleted — remove from index, recreate below
            del self._cache_names[display_name]

        # 2. Try to find on the API (in case of restart)
        existing = self._find_existing(display_name)
        if existing:
            self._cache_names[display_name] = existing.name
            logger.info("Reusing existing cache %s", existing.name)
            return existing.name

        # 3. Create new cache
        return self._create(display_name, system_instruction, contents)

    def invalidate(self, display_name: str) -> bool:
        """Delete a cache by display_name. Returns True if deleted."""
        existing = self._find_existing(display_name)
        if not existing:
            self._cache_names.pop(display_name, None)
            return False
        try:
            get_client().caches.delete(name=existing.name)
            self._cache_names.pop(display_name, None)
            logger.info("Cache invalidated: %s", display_name)
            return True
        except Exception as exc:
            logger.error("Failed to delete cache %s: %s", display_name, exc)
            return False

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _find_existing(self, display_name: str):
        """Iterate caches.list() to find one with matching display_name."""
        try:
            for cache in get_client().caches.list():
                if cache.display_name == display_name:
                    return cache
        except Exception as exc:
            logger.warning("caches.list() failed: %s", exc)
        return None

    def _create(
        self,
        display_name: str,
        system_instruction: str,
        contents: list[Any],
    ) -> str | None:
        settings = get_settings()
        ttl = f"{settings.CACHE_TTL_SEC}s"
        model = settings.GEMINI_MODEL

        # Guard: if contents is empty we cannot cache
        if not contents:
            logger.info(
                "Skipping cache creation for '%s': no contents (below threshold)",
                display_name,
            )
            return None

        try:
            cache = get_client().caches.create(
                model=model,
                config=types.CreateCachedContentConfig(
                    display_name=display_name,
                    system_instruction=system_instruction,
                    contents=contents,
                    ttl=ttl,
                ),
            )
            self._cache_names[display_name] = cache.name
            logger.info("Created cache %s (%s)", display_name, cache.name)
            return cache.name
        except Exception as exc:
            err_str = str(exc).lower()
            # Detect sub-threshold error — skip silently
            if "minimum" in err_str or "token" in err_str or "1024" in err_str:
                logger.info(
                    "Cache creation skipped for '%s': content below %d-token minimum",
                    display_name,
                    _CACHE_MIN_TOKENS,
                )
            else:
                logger.error("Cache creation failed for '%s': %s", display_name, exc)
            return None
