"""SSE (Server-Sent Events) formatting helpers.

format_sse_event  — serialise a single event to the SSE wire format.
keepalive_comment — blank comment line to keep connections alive.

Wire format per spec:
    event: <name>\n
    data: <json-string>\n
    \n
"""

from __future__ import annotations

import json


def format_sse_event(event: str, data: dict | list) -> str:
    """Return a correctly-formatted SSE event string.

    Args:
        event: SSE event name (e.g. "sources", "delta", "done", "error").
        data:  JSON-serialisable payload (dict or list).

    Returns:
        Multi-line string ending with a blank line (\\n\\n) as required by
        the SSE spec. Safe for all nested JSON — no manual escaping needed.

    Example:
        >>> format_sse_event("delta", {"text": "Hello"})
        'event: delta\\ndata: {"text": "Hello"}\\n\\n'
    """
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def keepalive_comment() -> str:
    """Return an SSE comment line that keeps the connection alive.

    SSE comments (lines starting with ':') are ignored by clients but
    prevent proxy timeouts on long-running streams.

    Returns:
        ': keepalive\\n\\n'
    """
    return ": keepalive\n\n"
