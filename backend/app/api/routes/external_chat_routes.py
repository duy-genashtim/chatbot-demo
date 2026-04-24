"""External (anonymous) chat routes — no authentication required.

Endpoints:
  POST /chat  — stream SSE chat response (external_policy domain)

Session continuity:
  - Reads session_id from 'sid' cookie, then request body, then generates new UUID.
  - Sets 'sid' httpOnly cookie (24h, SameSite=Lax, Secure in prod) on first call.
  - session_key = "external:{session_id}"  (LRU store key)
  - user_key    = "ext:{sha256(session_id:client_ip)[:16]}"  (DB key, no raw PII)

Rate limit: RATE_LIMIT_EXTERNAL_PER_MIN req/min keyed by real client IP.
X-Forwarded-For header is honoured (nginx proxy setup).

Sources event suppressed when ANONYMOUS_SHOW_SOURCES setting is False.

Cookie strategy:
  FastAPI's `response: Response` injection does not propagate Set-Cookie to a
  returned StreamingResponse.  We build the Set-Cookie header string manually
  and inject it into the StreamingResponse headers dict instead.

Slowapi decorator order:
  @router.post is outermost (last applied). @limiter.limit is inner.
  from __future__ import annotations is intentionally OMITTED — it turns all
  annotations into strings which breaks slowapi's wrapping + FastAPI's
  dependant resolution for Pydantic body models.
"""

import logging
import uuid
from http.cookies import SimpleCookie
from typing import Optional

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.settings_service import SettingsService
from app.services.chat_controller import hash_external_user_key, stream_chat
from app.services.rate_limiter import _get_forwarded_ip, external_limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["external-chat"])

_SSE_HEADERS = {
    "X-Accel-Buffering": "no",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
}

_COOKIE_NAME = "sid"
_COOKIE_MAX_AGE = 60 * 60 * 24  # 24 hours in seconds

# Rate limit string evaluated once at import time
_EXTERNAL_RATE_LIMIT = f"{get_settings().RATE_LIMIT_EXTERNAL_PER_MIN}/minute"


# ------------------------------------------------------------------ #
# Cookie helper
# ------------------------------------------------------------------ #

def _build_set_cookie(session_id: str, secure: bool) -> str:
    """Return a Set-Cookie header value for the sid cookie.

    Uses stdlib SimpleCookie for correct quoting/escaping.
    """
    c = SimpleCookie()
    c[_COOKIE_NAME] = session_id
    c[_COOKIE_NAME]["max-age"] = _COOKIE_MAX_AGE
    c[_COOKIE_NAME]["httponly"] = True
    c[_COOKIE_NAME]["samesite"] = "Lax"
    c[_COOKIE_NAME]["path"] = "/"
    if secure:
        c[_COOKIE_NAME]["secure"] = True
    # SimpleCookie.output() → "Set-Cookie: key=value; ..."
    # Strip the "Set-Cookie: " prefix to get just the value
    return c.output(header="").strip()


# ------------------------------------------------------------------ #
# Request schema
# ------------------------------------------------------------------ #


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


# ------------------------------------------------------------------ #
# POST /chat — anonymous SSE stream
# ------------------------------------------------------------------ #


@router.post("/chat", response_class=StreamingResponse)
@external_limiter.limit(_EXTERNAL_RATE_LIMIT)
async def external_chat(
    request: Request,
    body: ChatRequest,
    sid: Optional[str] = Cookie(default=None),
):
    """Stream a chat response for an anonymous external visitor.

    Cookie lifecycle:
      1. Check 'sid' cookie — use it if present.
      2. Fall back to body.session_id.
      3. Generate a new UUID if both are absent.
      4. Inject Set-Cookie header into StreamingResponse on new session.
    """
    settings = get_settings()

    # Resolve session ID (cookie > body > new)
    is_new_session = False
    session_id = sid or body.session_id
    if not session_id:
        session_id = str(uuid.uuid4())
        is_new_session = True

    # Derive stable user_key from session_id + real client IP
    client_ip = _get_forwarded_ip(request)
    user_key = hash_external_user_key(session_id, client_ip)
    session_key = f"external:{session_id}"

    # Check whether anonymous users should see sources
    db = SessionLocal()
    try:
        svc = SettingsService(db)
        show_sources = svc.get(
            "ANONYMOUS_SHOW_SOURCES",
            default=True,
            cast=lambda v: v.lower() not in ("false", "0", "no") if isinstance(v, str) else bool(v),
        )
    finally:
        db.close()

    logger.info(
        "external_chat session=%s ip_hash=%s msg_len=%d show_sources=%s",
        session_id, user_key, len(body.message), show_sources,
    )

    # Build response headers — inject Set-Cookie directly when new session
    resp_headers = dict(_SSE_HEADERS)
    if is_new_session:
        resp_headers["Set-Cookie"] = _build_set_cookie(
            session_id, secure=(settings.ENVIRONMENT == "prod")
        )

    return StreamingResponse(
        stream_chat(
            mode="external",
            session_id=session_id,
            session_key=session_key,
            user_key=user_key,
            message=body.message,
            show_sources=show_sources,
        ),
        media_type="text/event-stream",
        headers=resp_headers,
    )
