"""Tests for GET/DELETE /api/admin/metrics ring-buffer endpoint.

Verifies:
  - Admin can read the metrics snapshot (200)
  - Admin can clear the buffer (200)
  - Non-admin gets 403 on both routes
  - Buffer actually reflects pushed summaries
"""

from __future__ import annotations

import pytest
from unittest.mock import patch
from httpx import ASGITransport, AsyncClient
from fastapi import Request

from app.auth.dependencies import User, get_current_user, get_current_user_with_state
from app.main import app
from app.services.metrics_buffer import get_metrics_buffer


# ------------------------------------------------------------------ #
# Auth override helpers (local — these tests need both admin + user)
# ------------------------------------------------------------------ #

_ADMIN = User(email="admin@corp.com", name="Admin", is_admin=True)
_USER  = User(email="user@corp.com",  name="User",  is_admin=False)


def _apply_override(user_obj: User):
    async def _get():
        return user_obj

    async def _get_with_state(request: Request):
        request.state.user = user_obj
        return user_obj

    app.dependency_overrides[get_current_user] = _get
    app.dependency_overrides[get_current_user_with_state] = _get_with_state


def _clear_override():
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_with_state, None)


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_metrics_admin_returns_200():
    """Admin GET /api/admin/metrics → 200 with summaries list."""
    _apply_override(_ADMIN)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/admin/metrics")
    finally:
        _clear_override()

    assert resp.status_code == 200
    body = resp.json()
    assert "summaries" in body
    assert "total" in body
    assert isinstance(body["summaries"], list)


@pytest.mark.asyncio
async def test_metrics_non_admin_returns_403():
    """Non-admin GET /api/admin/metrics → 403."""
    _apply_override(_USER)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/admin/metrics")
    finally:
        _clear_override()

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_metrics_clear_admin_returns_200():
    """Admin DELETE /api/admin/metrics → 200 with cleared=True."""
    _apply_override(_ADMIN)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.delete("/api/admin/metrics")
    finally:
        _clear_override()

    assert resp.status_code == 200
    assert resp.json()["cleared"] is True


@pytest.mark.asyncio
async def test_metrics_clear_non_admin_returns_403():
    """Non-admin DELETE /api/admin/metrics → 403."""
    _apply_override(_USER)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.delete("/api/admin/metrics")
    finally:
        _clear_override()

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_metrics_reflects_pushed_summaries():
    """Buffer content is reflected in GET response."""
    buf = get_metrics_buffer()
    buf.clear()
    buf.push({"req_id": "aabbccdd", "path": "/api/internal/chat", "total_ms": 300})
    buf.push({"req_id": "11223344", "path": "/api/external/chat", "total_ms": 150})

    _apply_override(_ADMIN)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/admin/metrics")
    finally:
        _clear_override()
        buf.clear()

    body = resp.json()
    assert body["total"] == 2
    paths = [s["path"] for s in body["summaries"]]
    assert "/api/internal/chat" in paths
    assert "/api/external/chat" in paths


@pytest.mark.asyncio
async def test_metrics_clear_empties_buffer():
    """After DELETE, buffer is cleared (GET may have 1 entry from its own middleware push)."""
    buf = get_metrics_buffer()
    # Pre-fill with 5 entries so we can distinguish "was cleared" from "1 middleware push"
    for i in range(5):
        buf.push({"req_id": f"pre{i}", "total_ms": i})

    _apply_override(_ADMIN)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.delete("/api/admin/metrics")
            # After clear, any further requests add at most 1 entry (the GET itself)
            resp = await c.get("/api/admin/metrics")
    finally:
        _clear_override()

    # At most 2 entries: the DELETE push + the GET push (both from TimingMiddleware)
    assert resp.json()["total"] <= 2
    # None of the pre-filled req_ids should survive
    ids = [s.get("req_id", "") for s in resp.json()["summaries"]]
    assert not any(rid.startswith("pre") for rid in ids)
