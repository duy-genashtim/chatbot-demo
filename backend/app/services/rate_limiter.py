"""Slowapi rate limiter configuration for dual-domain chat endpoints.

Two separate Limiter instances so each router can use its own key_func:
  - external_limiter: keyed by client IP (reads X-Forwarded-For first)
  - internal_limiter: keyed by authenticated user email stored in request.state

Design note — chicken-and-egg for internal rate limiting:
  The `get_current_user` dependency runs BEFORE the rate limit check inside
  the route function (FastAPI resolves Depends before executing the handler).
  We store the resolved User on `request.state.user` in the auth dependency
  via a thin wrapper `get_current_user_with_state`, then the internal key_func
  reads `request.state.user.email`.  This avoids re-running JWT validation
  inside the key_func.

  For routes that don't use the wrapper the limiter falls back to IP so the
  app never crashes, but internal routes MUST use get_current_user_with_state.
"""

from __future__ import annotations

import logging

from fastapi import Request
from slowapi import Limiter

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Key functions
# ------------------------------------------------------------------ #


def _get_forwarded_ip(request: Request) -> str:
    """Return the real client IP, honouring X-Forwarded-For behind nginx.

    Reads the first (leftmost) IP in X-Forwarded-For which is the original
    client; intermediate proxies append their own IPs to the right.
    Falls back to request.client.host when the header is absent.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        # First entry is the real client
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_user_email(request: Request) -> str:
    """Return authenticated user's email from request.state.

    Populated by get_current_user_with_state dependency before the
    rate-limit decorator runs.  Falls back to IP so the app never raises
    a KeyError (internal routes always set this, so fallback is belt+braces).
    """
    user = getattr(request.state, "user", None)
    if user and getattr(user, "email", None):
        return user.email
    # Fallback: use IP (should not happen on correctly-configured internal routes)
    logger.warning("Internal rate limiter: user.email missing, falling back to IP")
    return _get_forwarded_ip(request)


# ------------------------------------------------------------------ #
# Limiter singletons
# ------------------------------------------------------------------ #

# External endpoints: rate-limited by IP
external_limiter = Limiter(key_func=_get_forwarded_ip)

# Internal endpoints: rate-limited by authenticated email
internal_limiter = Limiter(key_func=_get_user_email)
