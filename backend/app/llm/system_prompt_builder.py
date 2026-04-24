"""Build the per-domain system_instruction sent to Gemini.

Single source of truth shared by:
  - chat_session.py        — inline system_instruction path
  - cache_manager / prewarm — cached_content path

The base prompt lives in app/llm/prompts/{internal,external}_system.txt.
A toggleable citation rule is wrapped in <!--CITATION_RULE--> markers and
stripped at build time when the corresponding admin flag is False:
  - INTERNAL_REQUIRE_CITATIONS → internal
  - EXTERNAL_REQUIRE_CITATIONS → external

NOTE on cache invalidation: the produced text is what the Gemini context
cache stores. Whenever one of the toggles flips, the cache for that domain
must be invalidated so the next request rebuilds it with the new text.
That invalidation is wired in app/api/routes/admin_settings_routes.py.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Stripped (with leading whitespace + trailing newline) when citation toggle off.
_CITATION_BLOCK = re.compile(
    r"\s*<!--CITATION_RULE-->.*?<!--/CITATION_RULE-->\s*",
    re.DOTALL,
)

# mode → (prompt filename, settings key)
_MODE_TO_SOURCES: dict[str, tuple[str, str]] = {
    "internal": ("internal_system.txt", "INTERNAL_REQUIRE_CITATIONS"),
    "external": ("external_system.txt", "EXTERNAL_REQUIRE_CITATIONS"),
}


def _load_raw(filename: str) -> str:
    """Read a prompt file from disk; return empty string on FileNotFoundError."""
    try:
        return (_PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.warning("Prompt file not found: %s", filename)
        return ""


def build_system_instruction(mode: str) -> str:
    """Return the final system_instruction text for the given mode.

    Reads the citation toggle live from admin settings (DB→env→default=True).
    Strips the <!--CITATION_RULE--> block when the toggle is False.
    """
    sources = _MODE_TO_SOURCES.get(mode)
    if sources is None:
        # Defensive: unknown mode → return empty so caller knows nothing applies
        logger.warning("Unknown chat mode for system prompt: %r", mode)
        return ""

    filename, settings_key = sources
    text = _load_raw(filename)

    if not _read_citation_toggle(settings_key):
        text = _CITATION_BLOCK.sub("\n", text).strip()
    else:
        # Toggle ON: drop only the marker tags, keep the rule text inside.
        text = text.replace("<!--CITATION_RULE-->", "").replace("<!--/CITATION_RULE-->", "").strip()

    return text


def _read_citation_toggle(settings_key: str) -> bool:
    """Read a boolean admin setting; default True if anything goes wrong."""
    from app.core.db import SessionLocal
    from app.core.settings_service import SettingsService

    db = SessionLocal()
    try:
        raw = SettingsService(db).get(settings_key, default="true", cast=str)
    except Exception:  # pragma: no cover — defensive
        return True
    finally:
        db.close()
    return str(raw).strip().lower() in ("true", "1", "yes", "on")
