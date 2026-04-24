"""Admin router — assembles all admin sub-routers under /api/admin.

Sub-routers (each in their own module to stay under 200 lines):
  admin_documents_routes  → /documents/*
  admin_settings_routes   → /settings/*
  admin_admins_routes     → /admins/*
  admin_history_routes    → /history/*

The router-level require_admin dependency is applied in main.py when this
router is registered, so individual route handlers only need to inject
`user: User = Depends(require_admin)` for access to the caller's identity
(e.g. audit logging). They do NOT need to re-check is_admin.

Legacy smoke-test kept for backwards compatibility with test_admin_ping.py.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.admin_documents_routes import router as documents_router
from app.api.routes.admin_settings_routes import router as settings_router
from app.api.routes.admin_admins_routes import router as admins_router
from app.api.routes.admin_history_routes import router as history_router
from app.api.routes.metrics_routes import router as metrics_router

router = APIRouter(tags=["admin"])

# Legacy smoke-test endpoint (phase-05 stub — kept for test_admin_ping.py)
@router.get("/ping")
async def admin_ping() -> dict:
    """Smoke-test endpoint — confirms admin guard is active."""
    return {"ok": True}

# Mount all admin sub-routers (no additional prefix — paths start at /documents, etc.)
router.include_router(documents_router)
router.include_router(settings_router)
router.include_router(admins_router)
router.include_router(history_router)
router.include_router(metrics_router)
