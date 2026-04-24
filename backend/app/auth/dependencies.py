"""FastAPI dependencies for authentication and authorisation.

get_current_user  — validates bearer token, returns User DTO, raises 401.
require_admin     — wraps get_current_user, raises 403 if not admin.

User DTO is a plain Pydantic model (not a DB row) so it serialises cleanly
into JSON responses and can be injected anywhere without a DB session.

fastapi-azure-auth 5.x injects a fastapi_azure_auth.user.User object that
carries typed Pydantic fields (email, name, preferred_username) sourced
from the validated JWT claims.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi_azure_auth.user import User as AzureUser
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.entra_validator import azure_scheme
from app.core.db import get_db
from app.services.admin_service import AdminService

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# User DTO — returned by get_current_user
# ------------------------------------------------------------------ #


class User(BaseModel):
    """Lightweight DTO representing the authenticated caller."""

    email: str
    name: str
    is_admin: bool


# ------------------------------------------------------------------ #
# Internal helper
# ------------------------------------------------------------------ #


def _extract_email(token: AzureUser) -> str:
    """Return lowercase email from token; falls back to preferred_username (R1)."""
    email: str = token.email or ""
    if not email:
        email = token.preferred_username or ""
        if email:
            logger.warning(
                "Token missing 'email' claim — fell back to preferred_username: %s",
                email,
            )
    return email.lower().strip()


# ------------------------------------------------------------------ #
# Dependencies
# ------------------------------------------------------------------ #


async def get_current_user(
    token: Optional[AzureUser] = Security(azure_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Validate the bearer token and return a User DTO.

    Dev-only shortcut: when FAKE_AUTH_EMAIL is set AND ENVIRONMENT != "prod",
    skip JWT validation entirely and return a synthetic User with that email.
    The hard guard in main.py lifespan prevents this path in production.

    When the dev bypass is active, azure_scheme is built with auto_error=False
    so `token` is None instead of a 401 — we short-circuit before reading it.

    fastapi-azure-auth raises HTTP 401 automatically when the token is
    missing or the signature is invalid (normal prod path).
    """
    from app.core.config import get_settings
    settings = get_settings()

    if settings.ENVIRONMENT != "prod" and settings.FAKE_AUTH_EMAIL:
        fake_email = settings.FAKE_AUTH_EMAIL.lower().strip()
        admin_svc = AdminService(db)
        return User(
            email=fake_email,
            name="Dev User",
            is_admin=admin_svc.is_admin(fake_email),
        )

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chưa xác thực.",
        )

    email = _extract_email(token)
    if not email:
        logger.warning("Token claims contain no usable email; rejecting.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token thiếu thông tin email.",
        )

    # Display name: prefer name, fall back to given_name, then email
    name: str = token.name or token.given_name or email

    admin_svc = AdminService(db)
    is_admin = admin_svc.is_admin(email)

    return User(email=email, name=name, is_admin=is_admin)


async def get_current_user_with_state(
    request: "Request",
    user: User = Depends(get_current_user),
) -> User:
    """Same as get_current_user but also stores the User on request.state.

    Required by the internal rate limiter which reads request.state.user.email
    inside its key_func — FastAPI resolves Depends before the handler runs so
    the user is available when the limiter inspects the request.
    """
    request.state.user = user
    return user


async def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    """Dependency that allows only admin users.

    Raises HTTP 403 if the authenticated user is not in the admin allowlist.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cần quyền quản trị.",
        )
    return user
