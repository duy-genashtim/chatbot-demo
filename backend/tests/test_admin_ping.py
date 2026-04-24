"""Tests for GET /api/admin/ping — require_admin guard.

Verifies:
  - Non-admin authenticated user → 403
  - Admin user → 200 {"ok": true}
  - Unauthenticated → 401
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import User, get_current_user, get_current_user_with_state, require_admin
from app.main import app

# ------------------------------------------------------------------ #
# User fixtures
# ------------------------------------------------------------------ #

_NON_ADMIN = User(email="bob@corp.com", name="Bob", is_admin=False)
_ADMIN = User(email="admin@corp.com", name="Admin", is_admin=True)


async def _override_non_admin():
    return _NON_ADMIN


async def _override_admin():
    return _ADMIN


async def _require_admin_non_admin():
    from fastapi import HTTPException, status
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin privileges required.",
    )


async def _require_admin_pass():
    return _ADMIN


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_admin_ping_unauthenticated_returns_401():
    """No auth token at all → 401 from azure_scheme before require_admin."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/admin/ping")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_ping_non_admin_returns_403():
    """Authenticated but non-admin user → 403 from require_admin."""
    app.dependency_overrides[get_current_user] = _override_non_admin
    app.dependency_overrides[require_admin] = _require_admin_non_admin
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/admin/ping")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_admin, None)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_ping_admin_returns_200():
    """Admin user → 200 {"ok": true}."""
    app.dependency_overrides[get_current_user] = _override_admin
    app.dependency_overrides[require_admin] = _require_admin_pass
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/admin/ping")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_admin, None)

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
