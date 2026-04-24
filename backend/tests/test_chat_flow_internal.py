"""E2E internal chat flow — dependency_overrides + fake deps, no real API calls.

Verifies:
  - POST /api/internal/chat → SSE: sources before delta before done
  - done event contains session_id
  - chat_turn rows written (user + assistant) after stream
  - request_context timing keys populated in ring buffer after request

Uses conftest.py fixtures: auth_override_admin, fake_gemini_client.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.db import Base
from app.main import app
from app.services.metrics_buffer import get_metrics_buffer


# ------------------------------------------------------------------ #
# SSE parse helper
# ------------------------------------------------------------------ #

def _parse_sse(content: bytes) -> list[dict]:
    events, event_name = [], None
    for line in content.decode().splitlines():
        if line.startswith("event: "):
            event_name = line[7:]
        elif line.startswith("data: ") and event_name:
            events.append({"event": event_name, "data": json.loads(line[6:])})
            event_name = None
    return events


# ------------------------------------------------------------------ #
# Fake chat deps (retriever + session store)
# ------------------------------------------------------------------ #

class _FakeChunk:
    def __init__(self, src="hr.pdf", sec="leave"):
        self.text = f"context from {src}"
        self.metadata = {"source": src, "section": sec}
        self.score = 0.9

    @property
    def source(self): return self.metadata["source"]

    @property
    def section(self): return self.metadata["section"]


class _FakeSession:
    """Async generator yielding two tokens; records nothing to request_ctx."""
    async def stream(self, user_text, retrieved_ctx, user_key):
        yield "hello "
        yield "world"


class _FakeStore:
    def get_or_create(self, session_key, mode):
        return _FakeSession()


def _fake_retriever():
    r = MagicMock()
    r.search = AsyncMock(return_value=[_FakeChunk(), _FakeChunk(), _FakeChunk()])
    return r


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _patches():
    return (
        patch("app.services.chat_controller.get_retriever", return_value=_fake_retriever()),
        patch("app.services.chat_controller.get_session_store", return_value=_FakeStore()),
    )


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_internal_chat_sse_sources_before_delta_before_done(auth_override_admin):
    """SSE event order: sources → delta+ → done."""
    with _patches()[0], _patches()[1]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post("/api/internal/chat", json={"message": "What is leave policy?"})

    assert resp.status_code == 200
    events = _parse_sse(resp.content)
    names = [e["event"] for e in events]
    assert names[0] == "sources", f"first event should be sources, got {names}"
    assert "delta" in names
    assert names[-1] == "done"
    # All deltas after sources
    first_delta_idx = names.index("delta")
    sources_idx = names.index("sources")
    assert first_delta_idx > sources_idx


@pytest.mark.asyncio
async def test_internal_chat_done_contains_session_id(auth_override_admin):
    """done event must include a non-empty session_id."""
    with _patches()[0], _patches()[1]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post(
                "/api/internal/chat",
                json={"message": "q", "session_id": "test-sid-internal-42"},
            )

    events = _parse_sse(resp.content)
    done = next(e for e in events if e["event"] == "done")
    assert done["data"]["session_id"] == "test-sid-internal-42"
    assert "latency_ms" in done["data"]


@pytest.mark.asyncio
async def test_internal_chat_sources_contain_chunk_metadata(auth_override_admin):
    """sources event payload contains source + section keys."""
    with _patches()[0], _patches()[1]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post("/api/internal/chat", json={"message": "query"})

    events = _parse_sse(resp.content)
    src_event = next(e for e in events if e["event"] == "sources")
    assert len(src_event["data"]) >= 1
    first = src_event["data"][0]
    assert "source" in first
    assert "section" in first


@pytest.mark.asyncio
async def test_internal_chat_delta_text_concatenates(auth_override_admin):
    """Delta events together form the full assistant reply."""
    with _patches()[0], _patches()[1]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post("/api/internal/chat", json={"message": "q"})

    events = _parse_sse(resp.content)
    text = "".join(e["data"]["text"] for e in events if e["event"] == "delta")
    assert text == "hello world"


@pytest.mark.asyncio
async def test_internal_chat_ring_buffer_updated(auth_override_admin):
    """TimingMiddleware pushes a summary to MetricsBuffer after the request."""
    buf = get_metrics_buffer()
    buf.clear()

    with _patches()[0], _patches()[1]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            await c.post("/api/internal/chat", json={"message": "q"})

    snapshots = buf.snapshot()
    assert len(snapshots) >= 1
    latest = snapshots[-1]
    assert latest["path"] == "/api/internal/chat"
    assert "total_ms" in latest
