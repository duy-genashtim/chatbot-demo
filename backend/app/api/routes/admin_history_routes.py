"""Admin chat-history routes — browse / export CSV / purge.

Mounted under /api/admin (router-level require_admin applied in main.py).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import User, require_admin
from app.core.db import get_db
from app.services import audit_service
from app.services.chat_history_service import ChatHistoryService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-history"])


def _turn_to_dict(t) -> dict:
    return {
        "id": t.id,
        "session_id": t.session_id,
        "user_key": t.user_key,
        "mode": t.mode,
        "role": t.role,
        "content": t.content,
        "tokens_in": t.tokens_in,
        "tokens_cached": t.tokens_cached,
        "tokens_out": t.tokens_out,
        "latency_ms": t.latency_ms,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


# ------------------------------------------------------------------ #
# GET /history
# ------------------------------------------------------------------ #

@router.get("/history")
def list_history(
    mode: Optional[str] = Query(None),
    user_key: Optional[str] = Query(None),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    session_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """Return paginated ChatTurn rows with optional filters."""
    svc = ChatHistoryService(db)
    turns = svc.list_turns(
        mode=mode,
        user_key=user_key,
        since=since,
        until=until,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return [_turn_to_dict(t) for t in turns]


# ------------------------------------------------------------------ #
# GET /history/sessions — aggregated per-session summary
# ------------------------------------------------------------------ #

@router.get("/history/sessions")
def list_history_sessions(
    mode: Optional[str] = Query(None),
    user_key: Optional[str] = Query(None),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    session_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """Return paginated session summaries (one row per session_id)."""
    svc = ChatHistoryService(db)
    sessions = svc.list_sessions(
        mode=mode,
        user_key=user_key,
        since=since,
        until=until,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    total = svc.count_sessions(
        mode=mode,
        user_key=user_key,
        since=since,
        until=until,
        session_id=session_id,
    )
    # ISO-format datetimes for JSON safety
    for s in sessions:
        s["first_at"] = s["first_at"].isoformat() if s["first_at"] else None
        s["last_at"] = s["last_at"].isoformat() if s["last_at"] else None
    return {"total": total, "items": sessions}


# ------------------------------------------------------------------ #
# GET /history/sessions/{session_id} — all turns for one session
# ------------------------------------------------------------------ #

@router.get("/history/sessions/{session_id}")
def get_session_detail(
    session_id: str = Path(..., min_length=1),
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """Return full ordered turn list for a single session."""
    svc = ChatHistoryService(db)
    turns = svc.get_session_turns(session_id)
    if not turns:
        raise HTTPException(status_code=404, detail="không tìm thấy phiên")
    return {
        "session_id": session_id,
        "turns": [_turn_to_dict(t) for t in turns],
    }


# ------------------------------------------------------------------ #
# DELETE /history/sessions/{session_id}
# ------------------------------------------------------------------ #

@router.delete("/history/sessions/{session_id}")
def delete_session(
    session_id: str = Path(..., min_length=1),
    x_confirm_delete: Optional[str] = Header(None, alias="X-Confirm-Delete"),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Delete all turns for a single session. Requires X-Confirm-Delete: yes."""
    if (x_confirm_delete or "").lower() != "yes":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thao tác nguy hiểm — gửi header 'X-Confirm-Delete: yes' để xác nhận.",
        )
    svc = ChatHistoryService(db)
    deleted = svc.purge_session(session_id)
    audit_service.log(
        db,
        actor_email=user.email,
        action="history.purge_session",
        meta={"session_id": session_id, "deleted": deleted},
    )
    return {"deleted": deleted, "session_id": session_id}


# ------------------------------------------------------------------ #
# GET /history/stats — aggregate stats across filter
# ------------------------------------------------------------------ #

@router.get("/history/stats")
def history_stats(
    mode: Optional[str] = Query(None),
    user_key: Optional[str] = Query(None),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """Return aggregate stats (sessions, turns, tokens, avg latency)."""
    svc = ChatHistoryService(db)
    return svc.stats_summary(
        mode=mode,
        user_key=user_key,
        since=since,
        until=until,
        session_id=session_id,
    )


# ------------------------------------------------------------------ #
# GET /history/export.csv
# ------------------------------------------------------------------ #

@router.get("/history/export.csv")
def export_history_csv(
    mode: Optional[str] = Query(None),
    user_key: Optional[str] = Query(None),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """Stream matching ChatTurn rows as a CSV download (no pagination)."""
    svc = ChatHistoryService(db)
    csv_bytes = svc.export_csv(
        mode=mode,
        user_key=user_key,
        since=since,
        until=until,
        session_id=session_id,
    )

    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=chat_history.csv"},
    )


# ------------------------------------------------------------------ #
# DELETE /history
# ------------------------------------------------------------------ #

@router.delete("/history")
def purge_history(
    mode: Optional[str] = Query(None),
    user_key: Optional[str] = Query(None),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    session_id: Optional[str] = Query(None),
    x_confirm_delete: Optional[str] = Header(None, alias="X-Confirm-Delete"),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Purge chat turns matching filters.

    Requires header  X-Confirm-Delete: yes  to prevent accidental deletion.
    Returns {deleted: n}.
    """
    if (x_confirm_delete or "").lower() != "yes":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Thao tác nguy hiểm — gửi header 'X-Confirm-Delete: yes' để xác nhận."
            ),
        )

    svc = ChatHistoryService(db)
    deleted = svc.purge_by_filters(
        mode=mode,
        user_key=user_key,
        since=since,
        until=until,
        session_id=session_id,
    )

    audit_service.log(
        db,
        actor_email=user.email,
        action="history.purge",
        meta={
            "mode": mode,
            "user_key": user_key,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "session_id": session_id,
            "deleted": deleted,
        },
    )
    return {"deleted": deleted}
