"""E2E external (anonymous) chat flow tests.

Verifies:
  - POST /api/external/chat → 200 SSE with correct event order
  - Cookie set on first call (anonymous session ID)
  - Cookie reused on second call → same session_id in done event
  - sources event present (ANONYMOUS_SHOW_SOURCES default True)
  - Ring buffer updated after request

No auth override needed — external chat is anonymous.
Uses fake retriever + session store to avoid real Gemini/Chroma calls.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.metrics_buffer import get_metrics_buffer


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset the external rate limiter before each test to avoid cross-test 429s."""
    from app.services.rate_limiter import external_limiter
    external_limiter.reset()
    yield
    external_limiter.reset()


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
# Fake deps
# ------------------------------------------------------------------ #

class _FakeChunk:
    def __init__(self, src="policy.pdf", sec="section1"):
        self.text = f"context from {src}"
        self.metadata = {"source": src, "section": sec}
        self.score = 0.85

    @property
    def source(self): return self.metadata["source"]

    @property
    def section(self): return self.metadata["section"]


class _FakeSession:
    async def stream(self, user_text, retrieved_ctx, user_key):
        yield "answer "
        yield "here"


class _FakeStore:
    def get_or_create(self, session_key, mode):
        return _FakeSession()


def _fake_retriever():
    r = MagicMock()
    r.search = AsyncMock(return_value=[_FakeChunk(), _FakeChunk()])
    return r


def _patches():
    return (
        patch("app.services.chat_controller.get_retriever", return_value=_fake_retriever()),
        patch("app.services.chat_controller.get_session_store", return_value=_FakeStore()),
        # SettingsService.get for ANONYMOUS_SHOW_SOURCES
        patch(
            "app.core.settings_service.SettingsService.get",
            side_effect=lambda key, default=None, cast=None: (
                True if key == "ANONYMOUS_SHOW_SOURCES" else default
            ),
        ),
    )


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_external_chat_returns_200_sse():
    """Anonymous POST /api/external/chat → 200 text/event-stream."""
    with _patches()[0], _patches()[1], _patches()[2]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post("/api/external/chat", json={"message": "hi"})

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_external_chat_event_order():
    """SSE event order: sources → delta+ → done."""
    with _patches()[0], _patches()[1], _patches()[2]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post("/api/external/chat", json={"message": "what is policy?"})

    events = _parse_sse(resp.content)
    names = [e["event"] for e in events]
    assert names[0] == "sources", f"expected sources first, got: {names}"
    assert "delta" in names
    assert names[-1] == "done"


@pytest.mark.asyncio
async def test_external_chat_sets_sid_cookie():
    """First request with no cookie → Set-Cookie: sid header present."""
    with _patches()[0], _patches()[1], _patches()[2]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post("/api/external/chat", json={"message": "hello"})

    # httpx surfaces Set-Cookie via resp.cookies or headers
    assert "sid" in resp.cookies or any(
        "sid" in v for v in resp.headers.get_list("set-cookie")
    )


@pytest.mark.asyncio
async def test_external_chat_cookie_reused_gives_same_session():
    """When client sends back the sid cookie, done event returns same session_id."""
    with _patches()[0], _patches()[1], _patches()[2]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp1 = await c.post("/api/external/chat", json={"message": "first"})
            sid_cookie = resp1.cookies.get("sid")
            assert sid_cookie, "expected sid cookie on first call"

            resp2 = await c.post(
                "/api/external/chat",
                json={"message": "second"},
                cookies={"sid": sid_cookie},
            )

    events1 = _parse_sse(resp1.content)
    events2 = _parse_sse(resp2.content)
    done1 = next(e for e in events1 if e["event"] == "done")
    done2 = next(e for e in events2 if e["event"] == "done")
    # Both requests use the same session_id (derived from the same cookie)
    assert done1["data"]["session_id"] == done2["data"]["session_id"]


@pytest.mark.asyncio
async def test_external_chat_delta_text():
    """Delta events together form the full assistant reply."""
    with _patches()[0], _patches()[1], _patches()[2]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post("/api/external/chat", json={"message": "q"})

    events = _parse_sse(resp.content)
    text = "".join(e["data"]["text"] for e in events if e["event"] == "delta")
    assert text == "answer here"


@pytest.mark.asyncio
async def test_external_chat_ring_buffer_updated():
    """TimingMiddleware pushes summary for external chat requests."""
    buf = get_metrics_buffer()
    buf.clear()

    with _patches()[0], _patches()[1], _patches()[2]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            await c.post("/api/external/chat", json={"message": "q"})

    snaps = buf.snapshot()
    assert len(snaps) >= 1
    paths = [s["path"] for s in snaps]
    assert any("/api/external/chat" in p for p in paths)
