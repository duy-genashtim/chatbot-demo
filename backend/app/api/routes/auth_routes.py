"""Auth API routes — /api/auth/* endpoints.

GET /api/auth/me  — returns the authenticated user's profile + is_admin flag.

Logout is handled client-side by NextAuth (clears the session cookie);
no backend logout endpoint is needed for stateless JWT auth.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import User, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me", response_model=User, summary="Get current user profile")
async def get_me(user: User = Depends(get_current_user)) -> User:
    """Return the authenticated caller's email, display name, and admin flag.

    Requires a valid Entra ID bearer token in the Authorization header.
    Returns 401 if the token is missing or invalid.
    """
    return user
