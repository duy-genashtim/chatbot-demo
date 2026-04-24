"""Shared pytest fixtures for phase-08 integration and route tests.

Fixtures provided:
  fake_gemini_client   — patches get_client() with a deterministic streaming stub
  tmp_chroma_path      — function-scoped tmp_path, patches settings.CHROMA_PATH
  auth_override_admin  — dependency_override returning a fake admin User
  auth_override_user   — dependency_override returning a fake non-admin User
  anon_client          — httpx AsyncClient (no auth override)
  auth_client          — httpx AsyncClient with admin auth override active

All fixtures are function-scoped unless noted (isolates state between tests).
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import User, get_current_user, get_current_user_with_state
from app.main import app


# ------------------------------------------------------------------ #
# Fake Gemini infrastructure
# ------------------------------------------------------------------ #

class _FakeUsageMeta:
    """Stub for google.genai usage_metadata on final stream chunk."""
    prompt_token_count = 50
    cached_content_token_count = 0
    candidates_token_count = 20


class _FakeChunk:
    """Single streaming chunk from a fake Gemini response."""

    def __init__(self, text: str = "", is_last: bool = False) -> None:
        self.usage_metadata = _FakeUsageMeta() if is_last else None
        self._text = text

        # Build minimal candidates structure
        part = MagicMock()
        part.text = text
        content = MagicMock()
        content.parts = [part]
        candidate = MagicMock()
        candidate.content = content
        self.candidates = [candidate]


def _make_fake_stream(tokens: list[str] | None = None):
    """Return a synchronous iterable of fake chunks (matches SDK interface)."""
    if tokens is None:
        tokens = ["hello ", "world"]
    chunks = [_FakeChunk(t) for t in tokens]
    if chunks:
        # Mark last chunk with usage_metadata
        chunks[-1].usage_metadata = _FakeUsageMeta()
    return iter(chunks)


@pytest.fixture()
def fake_gemini_client():
    """Patch app.llm.gemini_client.get_client to return a streaming stub.

    The stub's models.generate_content_stream returns an iterator of
    _FakeChunk objects with deterministic text and usage_metadata on the
    last chunk.  No real API call is made.
    """
    mock_client = MagicMock()
    mock_client.models.generate_content_stream.side_effect = (
        lambda **kwargs: _make_fake_stream()
    )

    with patch("app.llm.gemini_client.get_client", return_value=mock_client):
        yield mock_client


# ------------------------------------------------------------------ #
# Fake retriever / session store helpers (reused across route tests)
# ------------------------------------------------------------------ #

class _FakeRetrievedChunk:
    def __init__(self, source: str = "doc.pdf", section: str = "intro") -> None:
        self.text = f"context from {source}"
        self.metadata = {"source": source, "section": section}
        self.score = 0.9

    @property
    def source(self) -> str:
        return self.metadata["source"]

    @property
    def section(self) -> str:
        return self.metadata["section"]


def make_fake_retriever(chunks: list | None = None):
    """Return a mock HybridRetriever whose search() yields canned chunks."""
    if chunks is None:
        chunks = [
            _FakeRetrievedChunk("a.pdf", "s1"),
            _FakeRetrievedChunk("b.pdf", "s2"),
            _FakeRetrievedChunk("c.pdf", "s3"),
        ]
    r = MagicMock()
    r.search = AsyncMock(return_value=chunks)
    return r


class _FakeChatSession:
    """Async generator session yielding two fixed tokens."""

    async def stream(self, user_text, retrieved_ctx, user_key):
        yield "hello "
        yield "world"


class _FakeSessionStore:
    def get_or_create(self, session_key, mode):
        return _FakeChatSession()


# ------------------------------------------------------------------ #
# Auth override fixtures
# ------------------------------------------------------------------ #

_FAKE_ADMIN = User(email="admin@corp.com", name="Admin User", is_admin=True)
_FAKE_USER  = User(email="user@corp.com",  name="Regular User", is_admin=False)


@pytest.fixture()
def auth_override_admin():
    """Apply dependency_overrides so all auth deps return a fake admin."""
    async def _override_user():
        return _FAKE_ADMIN

    async def _override_with_state(request: Request):
        request.state.user = _FAKE_ADMIN
        return _FAKE_ADMIN

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_user_with_state] = _override_with_state
    yield _FAKE_ADMIN
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_with_state, None)


@pytest.fixture()
def auth_override_user():
    """Apply dependency_overrides so all auth deps return a fake non-admin."""
    async def _override_user():
        return _FAKE_USER

    async def _override_with_state(request: Request):
        request.state.user = _FAKE_USER
        return _FAKE_USER

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_user_with_state] = _override_with_state
    yield _FAKE_USER
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_with_state, None)


# ------------------------------------------------------------------ #
# HTTP client fixtures
# ------------------------------------------------------------------ #

@pytest.fixture()
async def anon_client() -> AsyncIterator[AsyncClient]:
    """httpx AsyncClient with no auth override (anonymous requests)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture()
async def auth_client(auth_override_admin) -> AsyncIterator[AsyncClient]:
    """httpx AsyncClient pre-configured with admin auth override."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
