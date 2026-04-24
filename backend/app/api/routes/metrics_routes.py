"""Admin metrics endpoint — exposes the in-memory request ring buffer.

Routes (mounted under /api/admin via admin_routes.py):
  GET  /metrics  — returns last 100 request summaries (admin only)
  DELETE /metrics — clears the ring buffer (useful in tests / post-deploy smoke)

The require_admin dependency is applied at the parent router level in
main.py (admin_router registration), so individual handlers here only
need to accept `user` for identity logging — admin check already done.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import User, require_admin
from app.services.metrics_buffer import get_metrics_buffer

router = APIRouter(tags=["admin-metrics"])


@router.get("/metrics")
async def get_metrics(user: User = Depends(require_admin)) -> dict:
    """Return the last 100 request timing summaries.

    Response shape:
        {
          "summaries": [ { req_id, method, path, status, total_ms, ... }, ... ],
          "total": <int>
        }
    """
    buf = get_metrics_buffer()
    items = buf.snapshot()
    return {"summaries": items, "total": len(items)}


@router.delete("/metrics")
async def clear_metrics(user: User = Depends(require_admin)) -> dict:
    """Clear the ring buffer.  Useful for test isolation and post-deploy smoke."""
    get_metrics_buffer().clear()
    return {"cleared": True}
