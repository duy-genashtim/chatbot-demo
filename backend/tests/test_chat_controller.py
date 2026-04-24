"""Tests for app.services.chat_controller — stream event ordering and sources suppression.

All external dependencies (retriever, session_store, ChatSession) are faked
via monkeypatching app.main module globals — no real Gemini or Chroma calls.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat_controller import hash_external_user_key, stream_chat


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _parse_events(raw: list[str]) -> list[dict]:
    """Parse a list of SSE-formatted strings into [{event, data}] dicts."""
    events = []
    for chunk in raw:
        lines = [l for l in chunk.strip().splitlines() if l]
        event_name = None
        data = None
        for line in lines:
            if line.startswith("event: "):
                event_name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event_name:
            events.append({"event": event_name, "data": data})
    return events


async def _collect(gen) -> list[str]:
    """Collect all items from an async generator into a list."""
    items = []
    async for item in gen:
        items.append(item)
    return items


# ------------------------------------------------------------------ #
# Fake implementations
# ------------------------------------------------------------------ #

class FakeChunk:
    def __init__(self, source: str = "doc.pdf", section: str = "intro"):
        self.text = f"context from {source}"
        self.metadata = {"source": source, "section": section, "domain": "test"}
        self.score = 0.9

    @property
    def source(self):
        return self.metadata["source"]

    @property
    def section(self):
        return self.metadata["section"]


class FakeChatSession:
    """Yields two text deltas then stops."""

    async def stream(self, user_text, retrieved_ctx, user_key):
        yield "hello "
        yield "world"


class FakeSessionStore:
    def __init__(self, session):
        self._session = session

    def get_or_create(self, session_key, mode):
        return self._session


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

def _make_fake_retriever(chunks=None):
    """Return a mock retriever whose search() returns fake chunks."""
    if chunks is None:
        chunks = [FakeChunk("a.pdf", "s1"), FakeChunk("b.pdf", "s2"), FakeChunk("c.pdf", "s3")]
    retriever = MagicMock()
    retriever.search = AsyncMock(return_value=chunks)
    return retriever


def _make_patches(retriever=None, session=None):
    """Return patch context managers for main.get_retriever and main.get_session_store."""
    if retriever is None:
        retriever = _make_fake_retriever()
    if session is None:
        session = FakeChatSession()
    store = FakeSessionStore(session)
    return (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),  # wait — uses lazy import
        patch("app.main.get_retriever", return_value=retriever),
        patch("app.main.get_session_store", return_value=store),
    )


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_event_order_sources_delta_done():
    """sources event must arrive before any delta event."""
    retriever = _make_fake_retriever()
    session = FakeChatSession()
    store = FakeSessionStore(session)

    with (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),
        patch("app.services.chat_controller.get_session_store", return_value=store),
    ):
        raw = await _collect(
            stream_chat("internal", "sid-1", "user@ex.com", "user@ex.com", "hello")
        )

    events = _parse_events(raw)
    names = [e["event"] for e in events]

    assert names[0] == "sources", f"First event should be sources, got {names}"
    # All delta events come after sources
    first_delta = names.index("delta")
    assert first_delta > 0
    assert names[-1] == "done"


@pytest.mark.asyncio
async def test_sources_event_contains_chunk_metadata():
    retriever = _make_fake_retriever([FakeChunk("report.pdf", "chapter2")])
    session = FakeChatSession()
    store = FakeSessionStore(session)

    with (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),
        patch("app.services.chat_controller.get_session_store", return_value=store),
    ):
        raw = await _collect(
            stream_chat("internal", "sid-2", "k", "k", "question")
        )

    events = _parse_events(raw)
    sources_event = next(e for e in events if e["event"] == "sources")
    assert sources_event["data"][0]["source"] == "report.pdf"
    assert sources_event["data"][0]["section"] == "chapter2"


@pytest.mark.asyncio
async def test_delta_events_contain_text():
    retriever = _make_fake_retriever()
    session = FakeChatSession()
    store = FakeSessionStore(session)

    with (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),
        patch("app.services.chat_controller.get_session_store", return_value=store),
    ):
        raw = await _collect(
            stream_chat("internal", "sid-3", "k", "k", "q")
        )

    events = _parse_events(raw)
    delta_texts = [e["data"]["text"] for e in events if e["event"] == "delta"]
    assert "hello " in delta_texts
    assert "world" in delta_texts


@pytest.mark.asyncio
async def test_done_event_contains_session_id_and_latency():
    retriever = _make_fake_retriever()
    session = FakeChatSession()
    store = FakeSessionStore(session)

    with (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),
        patch("app.services.chat_controller.get_session_store", return_value=store),
    ):
        raw = await _collect(
            stream_chat("internal", "my-session-id", "k", "k", "q")
        )

    events = _parse_events(raw)
    done = next(e for e in events if e["event"] == "done")
    assert done["data"]["session_id"] == "my-session-id"
    assert "latency_ms" in done["data"]
    assert isinstance(done["data"]["latency_ms"], int)


@pytest.mark.asyncio
async def test_sources_suppressed_when_show_sources_false():
    """When show_sources=False no sources event is emitted (external anon config)."""
    retriever = _make_fake_retriever()
    session = FakeChatSession()
    store = FakeSessionStore(session)

    with (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),
        patch("app.services.chat_controller.get_session_store", return_value=store),
    ):
        raw = await _collect(
            stream_chat(
                "external", "sid-ext", "external:sid-ext",
                "ext:abc", "hi", show_sources=False
            )
        )

    events = _parse_events(raw)
    event_names = [e["event"] for e in events]
    assert "sources" not in event_names
    assert "delta" in event_names
    assert "done" in event_names


@pytest.mark.asyncio
async def test_sources_present_when_show_sources_true():
    retriever = _make_fake_retriever()
    session = FakeChatSession()
    store = FakeSessionStore(session)

    with (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),
        patch("app.services.chat_controller.get_session_store", return_value=store),
    ):
        raw = await _collect(
            stream_chat(
                "external", "sid-ext2", "external:sid-ext2",
                "ext:abc", "hi", show_sources=True
            )
        )

    events = _parse_events(raw)
    assert any(e["event"] == "sources" for e in events)


@pytest.mark.asyncio
async def test_error_event_on_retriever_failure():
    """If retriever raises, an error SSE event is yielded instead of crashing."""
    retriever = MagicMock()
    retriever.search = AsyncMock(side_effect=RuntimeError("chroma down"))

    with patch("app.services.chat_controller.get_retriever", return_value=retriever):
        raw = await _collect(
            stream_chat("internal", "sid-err", "k", "k", "q")
        )

    events = _parse_events(raw)
    assert any(e["event"] == "error" for e in events)
    # No done event after an error
    assert not any(e["event"] == "done" for e in events)


@pytest.mark.asyncio
async def test_external_domain_used_for_external_mode():
    """Retriever.search must be called with 'external_policy' for external mode."""
    retriever = _make_fake_retriever()
    session = FakeChatSession()
    store = FakeSessionStore(session)

    with (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),
        patch("app.services.chat_controller.get_session_store", return_value=store),
    ):
        await _collect(stream_chat("external", "s", "k", "k", "q"))

    retriever.search.assert_awaited_once()
    call_args = retriever.search.call_args
    assert call_args[0][1] == "external_policy" or call_args[1].get("domain") == "external_policy"


@pytest.mark.asyncio
async def test_internal_domain_used_for_internal_mode():
    """Retriever.search must be called with 'internal_hr' for internal mode."""
    retriever = _make_fake_retriever()
    session = FakeChatSession()
    store = FakeSessionStore(session)

    with (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),
        patch("app.services.chat_controller.get_session_store", return_value=store),
    ):
        await _collect(stream_chat("internal", "s", "k", "k", "q"))

    call_args = retriever.search.call_args
    assert call_args[0][1] == "internal_hr" or call_args[1].get("domain") == "internal_hr"


# ------------------------------------------------------------------ #
# hash_external_user_key
# ------------------------------------------------------------------ #

class TestHashExternalUserKey:
    def test_returns_ext_prefix(self):
        key = hash_external_user_key("session-abc", "1.2.3.4")
        assert key.startswith("ext:")

    def test_deterministic(self):
        k1 = hash_external_user_key("s", "ip")
        k2 = hash_external_user_key("s", "ip")
        assert k1 == k2

    def test_different_ip_gives_different_key(self):
        k1 = hash_external_user_key("session", "1.1.1.1")
        k2 = hash_external_user_key("session", "2.2.2.2")
        assert k1 != k2

    def test_different_session_gives_different_key(self):
        k1 = hash_external_user_key("aaa", "1.1.1.1")
        k2 = hash_external_user_key("bbb", "1.1.1.1")
        assert k1 != k2

    def test_hex_suffix_length(self):
        # "ext:" + 16 hex chars = 20 chars total
        key = hash_external_user_key("s", "ip")
        assert len(key) == 4 + 16
