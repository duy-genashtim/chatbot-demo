"""Two-tier settings resolver for chatbotv2.

Resolution order (highest → lowest priority):
  1. app_setting table (DB — admin UI writes here at runtime)
  2. Pydantic Settings (env / .env file)
  3. caller-supplied hard default

Usage:
    svc = SettingsService(db)
    val = svc.get("LLM_TEMPERATURE", default="0.2", cast=float)
    svc.set("LLM_TEMPERATURE", "0.5")   # upsert + invalidate cache
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.app_setting import AppSetting

T = TypeVar("T")

# Module-level simple cache: {key: value_str}
# Cleared entirely whenever set() is called (safe for single-process SQLite).
_cache: dict[str, str] = {}


class SettingsService:
    """Resolve runtime settings with DB-override > env fallback > hard default."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get(self, key: str, default: Any = None, cast: Callable[[str], T] = str) -> T:
        """Return setting value for *key*, applying *cast*.

        Lookup chain:
          1. Module-level in-memory cache (populated from DB on first miss)
          2. app_setting table
          3. Pydantic Settings attribute matching *key*
          4. *default*
        """
        raw = self._resolve(key)
        if raw is None:
            return default  # type: ignore[return-value]
        try:
            return cast(raw)  # type: ignore[return-value]
        except (ValueError, TypeError):
            return default  # type: ignore[return-value]

    def set(self, key: str, value: str) -> None:
        """Upsert a setting in the DB and clear the in-memory cache."""
        existing = self._db.get(AppSetting, key)
        now = datetime.now(timezone.utc)
        if existing:
            existing.value = value
            existing.updated_at = now
        else:
            self._db.add(AppSetting(key=key, value=value, updated_at=now))
        self._db.commit()
        _cache.clear()

    def delete(self, key: str) -> bool:
        """Remove a DB override; env default resumes. Returns True if deleted."""
        row = self._db.get(AppSetting, key)
        if row:
            self._db.delete(row)
            self._db.commit()
            _cache.clear()
            return True
        return False

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _resolve(self, key: str) -> str | None:
        # 1. In-memory cache hit
        if key in _cache:
            return _cache[key]

        # 2. DB lookup
        row = self._db.get(AppSetting, key)
        if row is not None:
            _cache[key] = row.value
            return row.value

        # 3. Env / Pydantic Settings
        env_val = self._from_env(key)
        if env_val is not None:
            return env_val

        return None

    @staticmethod
    def _from_env(key: str) -> str | None:
        """Read value from Pydantic Settings by attribute name (case-sensitive)."""
        settings = get_settings()
        val = getattr(settings, key, None)
        if val is None:
            return None
        # Convert non-string primitives to strings for uniform handling
        return str(val)
