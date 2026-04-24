"""Unit tests for SessionStore — LRU eviction, TTL expiry, idempotency.

Uses monkeypatching to isolate from DB and Gemini SDK.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

# Patch heavy imports before loading the module under test
import sys

# Stub google.genai.types so chat_session / session_store import cleanly
gtypes_stub = MagicMock()
gtypes_stub.Content = MagicMock(side_effect=lambda role, parts: MagicMock(role=role, parts=parts))
gtypes_stub.Part = MagicMock(side_effect=lambda text: MagicMock(text=text))
sys.modules.setdefault("google", MagicMock())
sys.modules.setdefault("google.genai", MagicMock())
sys.modules.setdefault("google.genai.types", gtypes_stub)

from app.llm.session_store import SessionStore  # noqa: E402
from app.llm.chat_session import ChatSession      # noqa: E402


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_store(max_sessions: int = 3, ttl_sec: int = 300) -> SessionStore:
    return SessionStore(max_sessions=max_sessions, ttl_sec=ttl_sec)


def _fake_session(key: str, mode: str = "internal") -> ChatSession:
    s = ChatSession(session_key=key, mode=mode)
    return s


# Patch out DB calls inside get_or_create -> _rehydrate
def _no_rehydrate(self, session):
    """No-op rehydrate: DB not available in unit tests."""
    pass


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

class TestSessionStoreIdempotency:
    """get_or_create returns the same object on repeated calls."""

    def test_same_instance_returned(self):
        store = _make_store()
        with patch.object(SessionStore, "_rehydrate", _no_rehydrate):
            s1 = store.get_or_create("user@example.com|internal", "internal")
            s2 = store.get_or_create("user@example.com|internal", "internal")
        assert s1 is s2

    def test_different_keys_different_instances(self):
        store = _make_store()
        with patch.object(SessionStore, "_rehydrate", _no_rehydrate):
            s1 = store.get_or_create("alice|internal", "internal")
            s2 = store.get_or_create("bob|internal", "internal")
        assert s1 is not s2

    def test_session_key_stored_correctly(self):
        store = _make_store()
        with patch.object(SessionStore, "_rehydrate", _no_rehydrate):
            s = store.get_or_create("alice|internal", "internal")
        assert s.session_key == "alice|internal"
        assert s.mode == "internal"


class TestSessionStoreLRUEviction:
    """Least-recently-used session is evicted when capacity exceeded."""

    def test_lru_eviction_on_overflow(self):
        store = _make_store(max_sessions=2)
        with patch.object(SessionStore, "_rehydrate", _no_rehydrate):
            s1 = store.get_or_create("a", "internal")
            s2 = store.get_or_create("b", "internal")
            # Access 'a' to make it recently-used; 'b' becomes LRU
            store.get_or_create("a", "internal")
            # Insert third session — 'b' should be evicted
            store.get_or_create("c", "internal")

        assert store.size() == 2
        assert "a" in store._store
        assert "c" in store._store
        assert "b" not in store._store

    def test_store_size_does_not_exceed_max(self):
        store = _make_store(max_sessions=3)
        with patch.object(SessionStore, "_rehydrate", _no_rehydrate):
            for i in range(10):
                store.get_or_create(f"user{i}", "external")
        assert store.size() <= 3

    def test_lru_eviction_oldest_when_no_access(self):
        store = _make_store(max_sessions=2)
        with patch.object(SessionStore, "_rehydrate", _no_rehydrate):
            store.get_or_create("first", "internal")
            store.get_or_create("second", "internal")
            store.get_or_create("third", "internal")

        assert store.size() == 2
        assert "first" not in store._store


class TestSessionStoreTTLExpiry:
    """Sessions idle beyond TTL are evicted."""

    def test_stale_session_evicted_on_access(self):
        store = _make_store(max_sessions=5, ttl_sec=1)
        with patch.object(SessionStore, "_rehydrate", _no_rehydrate):
            store.get_or_create("old_user", "internal")
            # Manually backdate last_access to simulate TTL exceeded
            store._store["old_user"].last_access = time.monotonic() - 10
            # Next get_or_create for same key should create a fresh session
            s_new = store.get_or_create("old_user", "internal")
        # Fresh session: history empty (rehydrate no-op), last_access recent
        assert (time.monotonic() - s_new.last_access) < 2

    def test_evict_stale_removes_expired_entries(self):
        store = _make_store(max_sessions=5, ttl_sec=1)
        with patch.object(SessionStore, "_rehydrate", _no_rehydrate):
            store.get_or_create("live_user", "internal")
            store.get_or_create("dead_user", "internal")
            store._store["dead_user"].last_access = time.monotonic() - 100

        removed = store.evict_stale()
        assert removed == 1
        assert "dead_user" not in store._store
        assert "live_user" in store._store

    def test_evict_stale_returns_zero_when_nothing_stale(self):
        store = _make_store(max_sessions=5, ttl_sec=300)
        with patch.object(SessionStore, "_rehydrate", _no_rehydrate):
            store.get_or_create("active", "internal")
        assert store.evict_stale() == 0

    def test_evict_stale_clears_all_expired(self):
        store = _make_store(max_sessions=5, ttl_sec=1)
        with patch.object(SessionStore, "_rehydrate", _no_rehydrate):
            for i in range(4):
                store.get_or_create(f"u{i}", "internal")
                store._store[f"u{i}"].last_access = time.monotonic() - 200

        removed = store.evict_stale()
        assert removed == 4
        assert store.size() == 0
