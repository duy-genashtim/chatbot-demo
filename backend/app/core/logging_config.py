"""Structured logging configuration for chatbotv2.

Env-driven:
  LOG_LEVEL  — root log level (default INFO)
  LOG_FORMAT — "pretty" (default in dev) or "json" (default/required in prod)

JSON output uses python-json-logger with fields:
  timestamp, level, logger, message, request_id, session_id, mode,
  stage_timings{...}, tokens{in, cached, out}

Call configure_logging() once at app startup (main.py lifespan), before
any other imports that create logger instances.
"""

from __future__ import annotations

import logging
import sys
from typing import Literal


def configure_logging(
    level: str = "INFO",
    log_format: Literal["pretty", "json"] = "pretty",
) -> None:
    """Wire root logger with either JSON or human-readable handlers.

    Args:
        level:      Logging level string (DEBUG/INFO/WARNING/ERROR).
        log_format: "json" for structured JSON lines (prod), "pretty" for
                    human-readable coloured output (dev).
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    if log_format == "json":
        _configure_json(numeric_level)
    else:
        _configure_pretty(numeric_level)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").propagate = True


def _configure_json(level: int) -> None:
    """Configure root logger with JSON formatter (python-json-logger)."""
    try:
        from pythonjsonlogger.json import JsonFormatter  # type: ignore[import]

        formatter = JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger",
            },
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    except ImportError:
        # Fall back to hand-rolled JSON if library unavailable
        formatter = _FallbackJsonFormatter()  # type: ignore[assignment]

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    _apply_handler(handler, level)


def _configure_pretty(level: int) -> None:
    """Configure root logger with a human-readable formatter."""
    fmt = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
    _apply_handler(handler, level)


def _apply_handler(handler: logging.Handler, level: int) -> None:
    """Remove existing handlers from root logger and install new one."""
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


class _FallbackJsonFormatter(logging.Formatter):
    """Hand-rolled JSON formatter — used when python-json-logger is absent."""

    import json as _json  # module-level import OK inside class scope

    def format(self, record: logging.LogRecord) -> str:
        import json
        import datetime

        payload = {
            "timestamp": datetime.datetime.utcfromtimestamp(record.created).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge in any extra dict fields (e.g. from timing middleware)
        for key, val in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "message", "module",
                "msecs", "pathname", "process", "processName", "relativeCreated",
                "stack_info", "thread", "threadName", "exc_info", "exc_text",
            }:
                payload[key] = val
        return json.dumps(payload, default=str)
