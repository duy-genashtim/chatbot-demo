"""In-memory ring buffer for recent request metrics summaries.

Thread-safe deque(maxlen=100) storing per-request timing/token dicts pushed
by TimingMiddleware after each response.  Provides a lightweight alternative
to a full APM system for small-scale deployments.

Usage:
    from app.services.metrics_buffer import get_metrics_buffer

    buf = get_metrics_buffer()
    buf.push({"req_id": "abc", "total_ms": 420, ...})
    items = buf.snapshot()   # list[dict], newest last
    buf.clear()
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

# Maximum number of summaries to retain in memory.
_MAX_SIZE = 100


class MetricsBuffer:
    """Thread-safe ring buffer holding the last _MAX_SIZE request summaries."""

    def __init__(self, maxlen: int = _MAX_SIZE) -> None:
        self._lock = threading.Lock()
        self._buf: deque[dict[str, Any]] = deque(maxlen=maxlen)

    def push(self, summary: dict[str, Any]) -> None:
        """Append a request summary dict (drops oldest when full)."""
        with self._lock:
            self._buf.append(summary)

    def snapshot(self) -> list[dict[str, Any]]:
        """Return a shallow copy of all retained summaries (oldest first)."""
        with self._lock:
            return list(self._buf)

    def clear(self) -> None:
        """Remove all retained summaries."""
        with self._lock:
            self._buf.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)


# ------------------------------------------------------------------ #
# Process-level singleton
# ------------------------------------------------------------------ #

_buffer: MetricsBuffer | None = None
_singleton_lock = threading.Lock()


def get_metrics_buffer() -> MetricsBuffer:
    """Return (or lazily create) the process-level MetricsBuffer singleton."""
    global _buffer
    if _buffer is None:
        with _singleton_lock:
            if _buffer is None:
                _buffer = MetricsBuffer()
    return _buffer
