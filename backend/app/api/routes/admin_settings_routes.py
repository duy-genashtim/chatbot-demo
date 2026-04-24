"""Admin settings routes — schema / get / put.

Mounted under /api/admin (router-level require_admin applied in main.py).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import User, require_admin
from app.core.db import get_db
from app.core.settings_service import SettingsService
from app.services import audit_service
from app.services.settings_schema import SETTINGS_SCHEMA

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-settings"])

# Settings whose change must invalidate the Gemini context cache for a
# specific domain — because the cache stores a system_instruction that the
# setting alters. After invalidation the next chat request rebuilds the
# cache with the new system_instruction (one slow turn, then cached again).
CACHE_AFFECTING_KEYS_TO_DOMAIN: dict[str, str] = {
    "INTERNAL_REQUIRE_CITATIONS": "internal_hr",
    "EXTERNAL_REQUIRE_CITATIONS": "external_policy",
}


# ------------------------------------------------------------------ #
# GET /settings/schema
# ------------------------------------------------------------------ #

@router.get("/settings/schema")
def get_settings_schema(_user: User = Depends(require_admin)) -> dict[str, Any]:
    """Return the whitelist schema: type, default, label, optional min/max."""
    return SETTINGS_SCHEMA


# ------------------------------------------------------------------ #
# GET /settings
# ------------------------------------------------------------------ #

@router.get("/settings")
def get_settings_values(
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Return current values for all whitelisted settings keys.

    Value resolution order: DB override → env var → schema hard default.
    """
    svc = SettingsService(db)
    result: dict[str, Any] = {}
    for key, meta in SETTINGS_SCHEMA.items():
        raw = svc.get(key, default=None, cast=str)
        if raw is None:
            result[key] = meta["default"]
        else:
            result[key] = _cast_value(raw, meta["type"], meta["default"])
    return result


# ------------------------------------------------------------------ #
# PUT /settings
# ------------------------------------------------------------------ #

@router.put("/settings")
def update_settings(
    body: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Upsert one or more whitelisted settings.

    Unknown keys → 400. Each accepted key is written to the DB via
    SettingsService.set().
    """
    unknown = [k for k in body if k not in SETTINGS_SCHEMA]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Khóa cài đặt không xác định: {unknown}. Cho phép: {sorted(SETTINGS_SCHEMA)}",
        )

    svc = SettingsService(db)
    updated: list[str] = []
    cache_rebuild_domains: set[str] = set()

    for key, value in body.items():
        # Read previous value so we only invalidate the cache on a real change.
        prev = svc.get(key, default=None, cast=str)
        new_str = str(value)
        svc.set(key, new_str)
        updated.append(key)

        if key in CACHE_AFFECTING_KEYS_TO_DOMAIN and prev != new_str:
            domain = CACHE_AFFECTING_KEYS_TO_DOMAIN[key]
            if _invalidate_cache(domain):
                cache_rebuild_domains.add(domain)

        audit_service.log(
            db,
            actor_email=user.email,
            action="settings.set",
            target=key,
            meta={"value": new_str[:200]},
        )
        logger.info("Setting updated by %s: %s = %r", user.email, key, value)

    response: dict[str, Any] = {"updated": updated}
    if cache_rebuild_domains:
        response["cache_rebuild_pending"] = sorted(cache_rebuild_domains)
        response["note"] = (
            "Gemini context cache invalidated for the listed domain(s). "
            "The first chat request after this change will be slower while "
            "the cache is rebuilt with the new system instruction."
        )
    return response


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _cast_value(raw: str, setting_type: str, default: Any) -> Any:
    """Cast a raw string value to the appropriate Python type."""
    try:
        if setting_type == "boolean":
            return raw.lower() in ("true", "1", "yes")
        if setting_type == "integer":
            return int(raw)
        if setting_type == "number":
            return float(raw)
        return raw  # string / text
    except (ValueError, TypeError):
        return default


def _invalidate_cache(domain: str) -> bool:
    """Drop the Gemini context cache for *domain*. Never raises.

    Returns True iff a cache entry actually existed and was deleted (so the
    response can hint at the next-request rebuild). Missing manager / cache
    silently returns False.
    """
    try:
        from app.main import get_cache_manager
        return bool(get_cache_manager().invalidate(domain))
    except Exception as exc:
        logger.warning("Could not invalidate Gemini cache for '%s': %s", domain, exc)
        return False
