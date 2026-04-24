"""Per-request context storage using ContextVar.

Provides a lightweight dict attached to the current async task so that
middleware, services, and route handlers can record timing/token data
without passing it explicitly through every call stack frame.

Usage:
    from app.core.request_context import request_ctx, record, record_tokens

    record("embed_ms", 14)
    record("vector_ms", 22)
    record("retrieval_total_ms", 80)
    record_tokens(in_=120, cached=0, out=310)

    # In timing middleware after response:
    data = request_ctx.get({})

Stage naming convention (all values in milliseconds unless noted):
  embed_ms, vector_ms, bm25_ms, rrf_ms, rerank_ms, retrieval_total_ms
  llm_ttft_ms, llm_total_ms, retrieval_ms (alias kept for back-compat)
  mode, session_id  (string metadata, not timing)

Token fields stored under keys: input_tokens, cached_tokens, output_tokens.
"""

from __future__ import annotations

from contextvars import ContextVar

# Each request gets its own dict; default is None (not {}) so middleware
# can distinguish "uninitialised" from "initialised but empty".
request_ctx: ContextVar[dict | None] = ContextVar("request_ctx", default=None)


def _get_or_create() -> dict:
    """Return the current context dict, creating one if absent."""
    ctx = request_ctx.get(None)
    if ctx is None:
        ctx = {}
        request_ctx.set(ctx)
    return ctx


def record(stage: str, value: object) -> None:
    """Write a named value into the current request context dict.

    Safe to call from async code; each asyncio Task has its own ContextVar
    copy so there is no cross-request contamination.

    Args:
        stage: Logical name for the measurement (e.g. "embed_ms").
        value: Any JSON-serialisable value.
    """
    _get_or_create()[stage] = value


def record_tokens(
    in_: int | None,
    cached: int | None,
    out: int | None,
) -> None:
    """Persist LLM token counts into the current request context.

    Args:
        in_:    Prompt token count (input_tokens).
        cached: Cached content token count (cached_tokens).
        out:    Generated token count (output_tokens).
    """
    ctx = _get_or_create()
    if in_ is not None:
        ctx["input_tokens"] = in_
    if cached is not None:
        ctx["cached_tokens"] = cached
    if out is not None:
        ctx["output_tokens"] = out
