"""Whitelist of admin-editable runtime settings with type/default/label metadata.

This is the single source of truth consumed by:
  - GET /api/admin/settings/schema  (returns this dict as JSON)
  - PUT /api/admin/settings          (validates keys against this dict)

Keys NOT in this dict are never exposed or writable via the admin UI.
Sensitive env vars (API keys, tenant IDs, secrets) are intentionally absent.
"""

from __future__ import annotations

from typing import Any

# Each entry:
#   type    : "string" | "number" | "integer" | "boolean" | "text"
#   default : hard-coded fallback shown in UI when DB and env are both absent
#   label   : human-readable label for the settings form
#   min/max : optional numeric bounds (number / integer types only)
#
# Labels suffixed "(requires restart)" mean the value is captured at process
# startup and is NOT re-read on every request — admin save persists it but
# the running container must be restarted before the new value takes effect.

SETTINGS_SCHEMA: dict[str, dict[str, Any]] = {
    "LLM_MODEL": {
        "type": "string",
        "default": "gemini-3.1-flash-lite-preview",
        "label": "Gemini model",
    },
    "LLM_TEMPERATURE": {
        "type": "number",
        "default": 0.2,
        "min": 0.0,
        "max": 1.0,
        "label": "LLM temperature",
    },
    "LLM_MAX_OUTPUT_TOKENS": {
        "type": "integer",
        "default": 800,
        "min": 64,
        "max": 4096,
        "label": "Max output tokens",
    },
    "SESSION_TTL_SEC": {
        "type": "integer",
        "default": 1800,
        "min": 60,
        "label": "Session idle TTL (s) (requires restart)",
    },
    "CACHE_TTL_SEC": {
        "type": "integer",
        "default": 1800,
        "min": 60,
        "label": "Gemini cache TTL (s)",
    },
    "TOP_K_VECTOR": {
        "type": "integer",
        "default": 5,
        "min": 1,
        "max": 50,
        "label": "Top-K vector candidates",
    },
    "TOP_K_FINAL": {
        "type": "integer",
        "default": 3,
        "min": 1,
        "max": 10,
        "label": "Top-K after rerank",
    },
    "RATE_LIMIT_EXTERNAL_PER_MIN": {
        "type": "integer",
        "default": 10,
        "min": 1,
        "label": "External rate limit (req/min/IP) (requires restart)",
    },
    "RATE_LIMIT_INTERNAL_PER_MIN": {
        "type": "integer",
        "default": 60,
        "min": 1,
        "label": "Internal rate limit (req/min/email) (requires restart)",
    },
    "ANONYMOUS_SHOW_SOURCES": {
        "type": "boolean",
        "default": True,
        "label": "Show sources in external mode",
    },
    "INTERNAL_REQUIRE_CITATIONS": {
        "type": "boolean",
        "default": True,
        "label": "Internal: require policy citations (e.g. \"Per Policy §3.2\")",
    },
    "EXTERNAL_REQUIRE_CITATIONS": {
        "type": "boolean",
        "default": True,
        "label": "External: require source citations in replies",
    },
    "HISTORY_RETENTION_DAYS": {
        "type": "integer",
        "default": 90,
        "min": 1,
        "max": 3650,
        "label": "Chat history retention (days)",
    },
    "HISTORY_REHYDRATE_TURNS": {
        "type": "integer",
        "default": 20,
        "min": 0,
        "max": 200,
        "label": "History rehydrate turns",
    },
    "MAX_UPLOAD_SIZE_MB": {
        "type": "integer",
        "default": 20,
        "min": 1,
        "max": 200,
        "label": "Max upload size (MB)",
    },
    "INTERNAL_OUTPUT_PREFIX": {
        "type": "text",
        "default": "",
        "label": "Internal: text prepended to every assistant reply",
    },
    "INTERNAL_OUTPUT_SUFFIX": {
        "type": "text",
        "default": "",
        "label": "Internal: text appended to every assistant reply",
    },
    "EXTERNAL_OUTPUT_PREFIX": {
        "type": "text",
        "default": "",
        "label": "External: text prepended to every assistant reply",
    },
    "EXTERNAL_OUTPUT_SUFFIX": {
        "type": "text",
        "default": "",
        "label": "External: text appended to every assistant reply",
    },
}
