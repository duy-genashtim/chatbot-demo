"""Integration tests for POST /api/external/chat — anonymous SSE endpoint.

Verifies:
  - Anonymous request → 200 SSE stream
  - 'sid' cookie set on first call when no cookie present
  - 'sid' cookie re-used on second call (same session_id in done event)
  - Rate limit returns 429 after N+1 requests within window
  - sources event present by default; suppressed when ANONYMOUS_SHOW_SOURCES=False

All tests patch SettingsService.get to avoid DB hits (no lifespan in test client).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# ------------------------------------------------------------------ #
# Shared SettingsService patch: returns True for ANONYMOUS_SHOW_SOURCES
# so tests don't need the DB to be set up.
# ------------------------------------------------------------------ #
def _settings_show_sources_true(key, default=None, cast=str):
    if key == "ANONYMOUS_SHOW_SOURCES":
        return True
    return default


# ------------------------------------------------------------------ #
# Fake chat infrastructure
# ------------------------------------------------------------------ #

class _FakeChunk:
    def __init__(self):
        self.text = "policy context"
        self.metadata = {"source": "policy.pdf", "section": "sec1"}
        self.score = 0.7

    @property
    def source(self):
        return self.metadata["source"]

    @property
    def section(self):
        return self.metadata["section"]


class _FakeSession:
    async def stream(self, user_text, retrieved_ctx, user_key):
        yield "hello "
        yield "world"


class _FakeStore:
    def get_or_create(self, session_key, mode):
        return _FakeSession()


def _fake_retriever():
    r = MagicMock()
    r.search = AsyncMock(return_value=[_FakeChunk()])
    return r


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _parse_sse(content: bytes) -> list[dict]:
    events = []
    event_name = None
    for line in content.decode().splitlines():
        if line.startswith("event: "):
            event_name = line[7:]
        elif line.startswith("data: ") and event_name:
            events.append({"event": event_name, "data": json.loads(line[6:])})
            event_name = None
    return events


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_external_chat_anonymous_returns_200():
    """No auth needed — external endpoint should return 200 SSE."""
    retriever = _fake_retriever()
    store = _FakeStore()

    with (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),
        patch("app.services.chat_controller.get_session_store", return_value=store),
        patch("app.core.settings_service.SettingsService.get", side_effect=_settings_show_sources_true),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/external/chat",
                json={"message": "What are the external policies?"},
            )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_external_chat_sets_sid_cookie_on_first_call():
    """When no 'sid' cookie is present, the response must set one."""
    retriever = _fake_retriever()
    store = _FakeStore()

    with (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),
        patch("app.services.chat_controller.get_session_store", return_value=store),
        patch("app.core.settings_service.SettingsService.get", side_effect=_settings_show_sources_true),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/external/chat",
                json={"message": "hello"},
            )

    assert "sid" in resp.cookies, "Expected 'sid' cookie to be set on first call"


@pytest.mark.asyncio
async def test_external_chat_reuses_sid_cookie():
    """Second call with existing 'sid' cookie should reuse the same session_id."""
    retriever = _fake_retriever()
    store = _FakeStore()

    with (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),
        patch("app.services.chat_controller.get_session_store", return_value=store),
        patch("app.core.settings_service.SettingsService.get", side_effect=_settings_show_sources_true),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            follow_redirects=True,
        ) as client:
            # First call — no cookie
            resp1 = await client.post(
                "/api/external/chat",
                json={"message": "first"},
            )
            sid_value = resp1.cookies.get("sid")
            assert sid_value, "First response must set sid cookie"

            # Second call — cookie auto-sent by httpx client jar
            resp2 = await client.post(
                "/api/external/chat",
                json={"message": "second"},
            )

    events1 = _parse_sse(resp1.content)
    events2 = _parse_sse(resp2.content)
    done1 = next(e for e in events1 if e["event"] == "done")
    done2 = next(e for e in events2 if e["event"] == "done")

    # Same session_id on both calls (cookie was re-used)
    assert done1["data"]["session_id"] == done2["data"]["session_id"]


@pytest.mark.asyncio
async def test_external_chat_event_order():
    """SSE events: sources → delta+ → done."""
    retriever = _fake_retriever()
    store = _FakeStore()

    with (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),
        patch("app.services.chat_controller.get_session_store", return_value=store),
        patch("app.core.settings_service.SettingsService.get", side_effect=_settings_show_sources_true),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/external/chat",
                json={"message": "q"},
            )

    events = _parse_sse(resp.content)
    names = [e["event"] for e in events]
    assert names[0] == "sources"
    assert "delta" in names
    assert names[-1] == "done"


@pytest.mark.asyncio
async def test_external_chat_sources_suppressed_when_setting_false():
    """When ANONYMOUS_SHOW_SOURCES resolves to False, no sources event."""
    retriever = _fake_retriever()
    store = _FakeStore()

    # Patch SettingsService.get to return False for ANONYMOUS_SHOW_SOURCES
    def _fake_settings_get(key, default=None, cast=str):
        if key == "ANONYMOUS_SHOW_SOURCES":
            return False
        return default

    with (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),
        patch("app.services.chat_controller.get_session_store", return_value=store),
        patch(
            "app.core.settings_service.SettingsService.get",
            side_effect=_fake_settings_get,
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/external/chat",
                json={"message": "q"},
            )

    events = _parse_sse(resp.content)
    names = [e["event"] for e in events]
    assert "sources" not in names
    assert "delta" in names
    assert "done" in names


@pytest.mark.asyncio
async def test_external_chat_rate_limit_triggers_429():
    """After RATE_LIMIT_EXTERNAL_PER_MIN+1 requests, slowapi returns 429."""
    from app.core.config import get_settings
    from app.services.rate_limiter import external_limiter

    settings = get_settings()
    limit = settings.RATE_LIMIT_EXTERNAL_PER_MIN
    retriever = _fake_retriever()
    store = _FakeStore()

    # Use a fixed IP so the rate limiter sees the same key every time.
    # httpx's test client uses 'testclient' as host; X-Forwarded-For overrides that.
    headers = {"X-Forwarded-For": "10.0.0.1"}

    # Reset the limiter storage between test runs to avoid pollution
    external_limiter.reset()

    status_codes = []
    with (
        patch("app.services.chat_controller.get_retriever", return_value=retriever),
        patch("app.services.chat_controller.get_session_store", return_value=store),
        patch("app.core.settings_service.SettingsService.get", side_effect=_settings_show_sources_true),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(limit + 2):
                resp = await client.post(
                    "/api/external/chat",
                    json={"message": "flood"},
                    headers=headers,
                )
                status_codes.append(resp.status_code)

    # At least one 429 must have been returned
    assert 429 in status_codes, f"Expected 429 in {status_codes}"
