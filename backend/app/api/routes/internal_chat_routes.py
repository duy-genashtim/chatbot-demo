"""Internal chat routes — requires valid Entra ID bearer token.

Endpoints:
  POST /chat          — stream SSE chat response (HR domain)
  GET  /chat/history  — return last N turns for session reconnect

Rate limit: RATE_LIMIT_INTERNAL_PER_MIN req/min keyed by authenticated email.
The get_current_user_with_state dependency runs BEFORE the handler, storing
the User on request.state so the internal_limiter key_func can read it.

Slowapi usage note:
  @limiter.limit("N/minute") must be applied BEFORE @router.post() so that
  FastAPI sees the original function signature (not the wrapped one).
  The Request parameter is mandatory when using slowapi decorators.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth.dependencies import User, get_current_user_with_state
from app.core.config import get_settings
from app.core.db import get_db
from app.services.chat_controller import stream_chat
from app.services.rate_limiter import internal_limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["internal-chat"])

# SSE response headers — tell nginx/proxies not to buffer the stream
_SSE_HEADERS = {
    "X-Accel-Buffering": "no",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
}

# Rate limit string — evaluated once at import time from settings
_INTERNAL_RATE_LIMIT = f"{get_settings().RATE_LIMIT_INTERNAL_PER_MIN}/minute"


# ------------------------------------------------------------------ #
# Request / response schemas
# ------------------------------------------------------------------ #


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


# ------------------------------------------------------------------ #
# POST /chat — SSE stream
# ------------------------------------------------------------------ #


@router.post("/chat", response_class=StreamingResponse)
@internal_limiter.limit(_INTERNAL_RATE_LIMIT)
async def internal_chat(
    request: Request,
    body: ChatRequest,
    user: User = Depends(get_current_user_with_state),
):
    """Stream a chat response for an authenticated internal user.

    - session_key = user.email  (LRU store key)
    - user_key    = user.email  (DB persistence key)
    - domain      = internal_hr
    - sources event always emitted
    """
    session_id = body.session_id or str(uuid.uuid4())
    session_key = user.email  # one LRU session per email
    user_key = user.email

    logger.info(
        "internal_chat user=%s session=%s msg_len=%d",
        user.email, session_id, len(body.message),
    )

    return StreamingResponse(
        stream_chat(
            mode="internal",
            session_id=session_id,
            session_key=session_key,
            user_key=user_key,
            message=body.message,
            show_sources=True,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ------------------------------------------------------------------ #
# GET /chat/history — reconnect support
# ------------------------------------------------------------------ #


@router.get("/chat/history")
async def internal_chat_history(
    request: Request,
    session_id: str = Query(..., description="Session ID to fetch history for"),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user_with_state),
    db=Depends(get_db),
):
    """Return last *limit* turns for *session_id*, filtered to the calling user.

    Access control: only returns turns where user_key == user.email.
    Prevents cross-user history leakage even if session_id is guessed.
    """
    from app.services.chat_history_service import ChatHistoryService

    svc = ChatHistoryService(db)
    turns = svc.rehydrate(session_id, limit)

    # Filter: only turns belonging to this authenticated user
    user_turns = [t for t in turns if t.user_key == user.email]

    if not user_turns and turns:
        # session exists but belongs to a different user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phiên không thuộc về người dùng hiện tại.",
        )

    return [
        {
            "role": t.role,
            "content": t.content,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in user_turns
    ]
