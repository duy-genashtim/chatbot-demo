"""Integration tests for POST /api/internal/chat and GET /api/internal/chat/history.

Strategy:
  - Use httpx.AsyncClient with ASGITransport (no real server needed).
  - Override get_current_user / get_current_user_with_state via
    app.dependency_overrides so no real Entra token is required.
  - Patch get_retriever / get_session_store on app.services.chat_controller
    and app.main with fake implementations.
  - Verify: no auth → 401; with auth → 200 SSE stream with correct event order.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import User, get_current_user, get_current_user_with_state
from app.main import app


# ------------------------------------------------------------------ #
# Fake chat infrastructure (same as test_chat_controller)
# ------------------------------------------------------------------ #

class _FakeChunk:
    def __init__(self):
        self.text = "some context"
        self.metadata = {"source": "hr.pdf", "section": "leave"}
        self.score = 0.8

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
    r.search = AsyncMock(return_value=[_FakeChunk(), _FakeChunk()])
    return r


# ------------------------------------------------------------------ #
# Auth override helpers
# ------------------------------------------------------------------ #

_FAKE_USER = User(email="alice@corp.com", name="Alice", is_admin=False)
_FAKE_ADMIN = User(email="admin@corp.com", name="Admin", is_admin=True)


async def _override_user():
    return _FAKE_USER


async def _override_user_with_state(request: Request):
    """Override for get_current_user_with_state — must type-annotate request: Request
    so FastAPI injects it properly (not treated as a query param)."""
    request.state.user = _FAKE_USER
    return _FAKE_USER


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
async def test_internal_chat_no_auth_returns_401():
    """Request without auth override should get 401 (azure_scheme rejects it)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/internal/chat",
            json={"message": "hello"},
        )
    # fastapi-azure-auth raises 401 for missing token
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_internal_chat_with_auth_returns_200_sse():
    """With auth override and fake deps, POST /api/internal/chat returns SSE stream."""
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_user_with_state] = _override_user_with_state
    retriever = _fake_retriever()
    store = _FakeStore()

    try:
        with (
            patch("app.services.chat_controller.get_retriever", return_value=retriever),
            patch("app.services.chat_controller.get_session_store", return_value=store),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/internal/chat",
                    json={"message": "What is the leave policy?"},
                )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_with_state, None)

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_internal_chat_event_order():
    """SSE events: sources → delta+ → done in that order."""
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_user_with_state] = _override_user_with_state
    retriever = _fake_retriever()
    store = _FakeStore()

    try:
        with (
            patch("app.services.chat_controller.get_retriever", return_value=retriever),
            patch("app.services.chat_controller.get_session_store", return_value=store),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/internal/chat",
                    json={"message": "query"},
                )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_with_state, None)

    events = _parse_sse(resp.content)
    names = [e["event"] for e in events]
    assert names[0] == "sources"
    assert "delta" in names
    assert names[-1] == "done"


@pytest.mark.asyncio
async def test_internal_chat_done_event_has_session_id():
    """done event must include session_id."""
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_user_with_state] = _override_user_with_state
    retriever = _fake_retriever()
    store = _FakeStore()

    try:
        with (
            patch("app.services.chat_controller.get_retriever", return_value=retriever),
            patch("app.services.chat_controller.get_session_store", return_value=store),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/internal/chat",
                    json={"message": "q", "session_id": "test-sid-999"},
                )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_with_state, None)

    events = _parse_sse(resp.content)
    done = next(e for e in events if e["event"] == "done")
    assert done["data"]["session_id"] == "test-sid-999"


@pytest.mark.asyncio
async def test_internal_chat_auto_generates_session_id():
    """When session_id is absent, done event still contains a non-empty session_id."""
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_user_with_state] = _override_user_with_state
    retriever = _fake_retriever()
    store = _FakeStore()

    try:
        with (
            patch("app.services.chat_controller.get_retriever", return_value=retriever),
            patch("app.services.chat_controller.get_session_store", return_value=store),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/internal/chat",
                    json={"message": "q"},
                )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_with_state, None)

    events = _parse_sse(resp.content)
    done = next(e for e in events if e["event"] == "done")
    assert done["data"]["session_id"]  # non-empty UUID string


@pytest.mark.asyncio
async def test_internal_history_no_auth_returns_401():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/internal/chat/history",
            params={"session_id": "abc"},
        )
    assert resp.status_code == 401
