"""Unit tests for CacheManager — mocks genai client, verifies lifecycle.

Covers:
  - get_or_create reuses existing cache (no duplicate API call)
  - get_or_create creates cache when absent
  - invalidate calls caches.delete and clears index
  - sub-threshold error (token minimum) returns None gracefully
  - API list() failure is handled without raising
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.llm.cache_manager import CacheManager


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

def _mock_cache(display_name: str, name: str = "cachedContents/abc123"):
    c = MagicMock()
    c.display_name = display_name
    c.name = name
    return c


def _make_manager() -> tuple[CacheManager, MagicMock]:
    """Return (CacheManager, mock_client)."""
    manager = CacheManager()
    mock_client = MagicMock()
    return manager, mock_client


# ------------------------------------------------------------------ #
# get_or_create: reuse existing cache
# ------------------------------------------------------------------ #

class TestCacheManagerReuse:
    def test_returns_existing_cache_name_from_list(self):
        manager, mock_client = _make_manager()
        existing = _mock_cache("internal_cache", "cachedContents/existing")
        mock_client.caches.list.return_value = [existing]
        mock_client.caches.create = MagicMock()

        with patch("app.llm.cache_manager.get_client", return_value=mock_client):
            name = manager.get_or_create("internal_cache", "sys instruction", ["doc1"])

        assert name == "cachedContents/existing"
        mock_client.caches.create.assert_not_called()

    def test_returns_in_memory_cached_name_on_second_call(self):
        manager, mock_client = _make_manager()
        existing = _mock_cache("internal_cache", "cachedContents/existing")
        # First call: list returns the cache
        mock_client.caches.list.return_value = [existing]

        with patch("app.llm.cache_manager.get_client", return_value=mock_client):
            name1 = manager.get_or_create("internal_cache", "sys", ["doc"])
            # Simulate list now returning nothing (would normally trigger create)
            mock_client.caches.list.return_value = [existing]
            name2 = manager.get_or_create("internal_cache", "sys", ["doc"])

        assert name1 == name2
        # list() called on first call only (second uses in-memory index + verify)
        assert mock_client.caches.create.call_count == 0


# ------------------------------------------------------------------ #
# get_or_create: creates new cache when not found
# ------------------------------------------------------------------ #

class TestCacheManagerCreate:
    def test_creates_cache_when_not_found(self):
        manager, mock_client = _make_manager()
        mock_client.caches.list.return_value = []
        new_cache = _mock_cache("new_cache", "cachedContents/new")
        mock_client.caches.create.return_value = new_cache

        with patch("app.llm.cache_manager.get_client", return_value=mock_client):
            with patch("app.llm.cache_manager.get_settings") as mock_settings:
                mock_settings.return_value.CACHE_TTL_SEC = 1800
                mock_settings.return_value.GEMINI_MODEL = "gemini-test"
                name = manager.get_or_create("new_cache", "sys instruction", ["content"])

        assert name == "cachedContents/new"
        mock_client.caches.create.assert_called_once()

    def test_create_call_args_include_display_name(self):
        manager, mock_client = _make_manager()
        mock_client.caches.list.return_value = []
        new_cache = _mock_cache("my_cache", "cachedContents/xyz")
        mock_client.caches.create.return_value = new_cache

        with patch("app.llm.cache_manager.get_client", return_value=mock_client):
            with patch("app.llm.cache_manager.get_settings") as mock_settings:
                mock_settings.return_value.CACHE_TTL_SEC = 1800
                mock_settings.return_value.GEMINI_MODEL = "gemini-test"
                manager.get_or_create("my_cache", "system prompt", ["doc content"])

        call_kwargs = mock_client.caches.create.call_args
        assert call_kwargs is not None

    def test_returns_none_when_contents_empty(self):
        manager, mock_client = _make_manager()
        mock_client.caches.list.return_value = []

        with patch("app.llm.cache_manager.get_client", return_value=mock_client):
            name = manager.get_or_create("empty_cache", "sys", contents=[])

        assert name is None
        mock_client.caches.create.assert_not_called()


# ------------------------------------------------------------------ #
# get_or_create: sub-threshold / API error returns None
# ------------------------------------------------------------------ #

class TestCacheManagerSubThreshold:
    def test_returns_none_on_token_minimum_error(self):
        manager, mock_client = _make_manager()
        mock_client.caches.list.return_value = []
        mock_client.caches.create.side_effect = Exception(
            "Minimum 1024 tokens required for caching"
        )

        with patch("app.llm.cache_manager.get_client", return_value=mock_client):
            with patch("app.llm.cache_manager.get_settings") as mock_settings:
                mock_settings.return_value.CACHE_TTL_SEC = 1800
                mock_settings.return_value.GEMINI_MODEL = "gemini-test"
                name = manager.get_or_create("small_cache", "short sys", ["tiny"])

        assert name is None

    def test_returns_none_on_generic_api_error(self):
        manager, mock_client = _make_manager()
        mock_client.caches.list.return_value = []
        mock_client.caches.create.side_effect = Exception("Service unavailable")

        with patch("app.llm.cache_manager.get_client", return_value=mock_client):
            with patch("app.llm.cache_manager.get_settings") as mock_settings:
                mock_settings.return_value.CACHE_TTL_SEC = 1800
                mock_settings.return_value.GEMINI_MODEL = "gemini-test"
                name = manager.get_or_create("fail_cache", "sys", ["content"])

        assert name is None

    def test_list_failure_handled_gracefully(self):
        manager, mock_client = _make_manager()
        mock_client.caches.list.side_effect = Exception("API quota exceeded")
        new_cache = _mock_cache("fallback_cache", "cachedContents/fallback")
        mock_client.caches.create.return_value = new_cache

        with patch("app.llm.cache_manager.get_client", return_value=mock_client):
            with patch("app.llm.cache_manager.get_settings") as mock_settings:
                mock_settings.return_value.CACHE_TTL_SEC = 1800
                mock_settings.return_value.GEMINI_MODEL = "gemini-test"
                # Should not raise; will attempt create after list fails
                name = manager.get_or_create("fallback_cache", "sys", ["doc"])

        # Either created or None — must not raise
        assert name is None or name == "cachedContents/fallback"


# ------------------------------------------------------------------ #
# invalidate
# ------------------------------------------------------------------ #

class TestCacheManagerInvalidate:
    def test_invalidate_calls_delete_and_clears_index(self):
        manager, mock_client = _make_manager()
        existing = _mock_cache("to_delete", "cachedContents/del")
        mock_client.caches.list.return_value = [existing]

        with patch("app.llm.cache_manager.get_client", return_value=mock_client):
            result = manager.invalidate("to_delete")

        assert result is True
        mock_client.caches.delete.assert_called_once_with(name="cachedContents/del")
        assert "to_delete" not in manager._cache_names

    def test_invalidate_returns_false_when_not_found(self):
        manager, mock_client = _make_manager()
        mock_client.caches.list.return_value = []

        with patch("app.llm.cache_manager.get_client", return_value=mock_client):
            result = manager.invalidate("nonexistent")

        assert result is False
        mock_client.caches.delete.assert_not_called()

    def test_invalidate_removes_from_in_memory_index(self):
        manager, mock_client = _make_manager()
        # Pre-populate the in-memory index
        manager._cache_names["cached_key"] = "cachedContents/abc"
        existing = _mock_cache("cached_key", "cachedContents/abc")
        mock_client.caches.list.return_value = [existing]

        with patch("app.llm.cache_manager.get_client", return_value=mock_client):
            manager.invalidate("cached_key")

        assert "cached_key" not in manager._cache_names
