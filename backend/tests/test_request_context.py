"""Unit tests for app.core.request_context — ContextVar isolation and helpers.

Verifies:
  - record() writes stage values into the current context dict
  - record_tokens() writes input/cached/output_tokens
  - No cross-task contamination (each asyncio task has its own copy)
  - Partial token args (None) are omitted from context
  - _get_or_create() auto-initialises when context is None
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.request_context import record, record_tokens, request_ctx


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _fresh_ctx() -> dict:
    """Install a clean dict into request_ctx and return it."""
    ctx: dict = {}
    request_ctx.set(ctx)
    return ctx


# ------------------------------------------------------------------ #
# record() tests
# ------------------------------------------------------------------ #

class TestRecord:
    def test_writes_value_to_context(self):
        ctx = _fresh_ctx()
        record("embed_ms", 42)
        assert ctx["embed_ms"] == 42

    def test_overwrites_existing_key(self):
        ctx = _fresh_ctx()
        record("embed_ms", 10)
        record("embed_ms", 99)
        assert ctx["embed_ms"] == 99

    def test_multiple_stages_independent(self):
        ctx = _fresh_ctx()
        record("embed_ms", 10)
        record("vector_ms", 20)
        record("rerank_ms", 30)
        assert ctx == {"embed_ms": 10, "vector_ms": 20, "rerank_ms": 30}

    def test_auto_creates_context_when_none(self):
        """record() must not raise when called before middleware sets the context."""
        request_ctx.set(None)  # simulate background task with no ctx
        record("llm_ttft_ms", 150)
        ctx = request_ctx.get(None)
        assert ctx is not None
        assert ctx["llm_ttft_ms"] == 150

    def test_accepts_string_value(self):
        ctx = _fresh_ctx()
        record("mode", "internal")
        assert ctx["mode"] == "internal"

    def test_accepts_none_value(self):
        ctx = _fresh_ctx()
        record("input_tokens", None)
        assert ctx["input_tokens"] is None


# ------------------------------------------------------------------ #
# record_tokens() tests
# ------------------------------------------------------------------ #

class TestRecordTokens:
    def test_all_tokens_written(self):
        ctx = _fresh_ctx()
        record_tokens(in_=100, cached=20, out=300)
        assert ctx["input_tokens"] == 100
        assert ctx["cached_tokens"] == 20
        assert ctx["output_tokens"] == 300

    def test_none_in_omitted(self):
        ctx = _fresh_ctx()
        record_tokens(in_=None, cached=5, out=10)
        assert "input_tokens" not in ctx
        assert ctx["cached_tokens"] == 5
        assert ctx["output_tokens"] == 10

    def test_all_none_writes_nothing(self):
        ctx = _fresh_ctx()
        record_tokens(in_=None, cached=None, out=None)
        assert "input_tokens" not in ctx
        assert "cached_tokens" not in ctx
        assert "output_tokens" not in ctx

    def test_partial_tokens_partial_write(self):
        ctx = _fresh_ctx()
        record_tokens(in_=50, cached=None, out=200)
        assert ctx["input_tokens"] == 50
        assert "cached_tokens" not in ctx
        assert ctx["output_tokens"] == 200

    def test_auto_creates_context_when_none(self):
        request_ctx.set(None)
        record_tokens(in_=10, cached=0, out=5)
        ctx = request_ctx.get(None)
        assert ctx is not None
        assert ctx["input_tokens"] == 10


# ------------------------------------------------------------------ #
# Cross-task isolation
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_no_cross_task_contamination():
    """ContextVar provides per-task isolation — task A's data must not leak to task B."""
    results: dict[str, dict] = {}

    async def task_a():
        ctx: dict = {}
        request_ctx.set(ctx)
        record("task", "A")
        record("embed_ms", 111)
        await asyncio.sleep(0)  # yield to event loop
        results["a"] = dict(request_ctx.get({}))

    async def task_b():
        ctx: dict = {}
        request_ctx.set(ctx)
        record("task", "B")
        record("embed_ms", 222)
        await asyncio.sleep(0)
        results["b"] = dict(request_ctx.get({}))

    await asyncio.gather(task_a(), task_b())

    assert results["a"]["task"] == "A"
    assert results["a"]["embed_ms"] == 111
    assert results["b"]["task"] == "B"
    assert results["b"]["embed_ms"] == 222


@pytest.mark.asyncio
async def test_context_reset_restores_prior_token():
    """Resetting the token reverts the ContextVar to the value before the set().

    This mirrors TimingMiddleware: it sets a fresh dict at request start
    (capturing a token), then resets that token on exit so the next
    request cannot see the previous request's data.
    """
    # Explicitly set a known "before" state first
    before_ctx: dict = {"before": True}
    before_token = request_ctx.set(before_ctx)

    # Now simulate middleware: set a fresh ctx for this "request"
    request_ctx_dict: dict = {}
    request_token = request_ctx.set(request_ctx_dict)
    record("embed_ms", 55)
    assert request_ctx.get(None) is request_ctx_dict

    # Reset: should restore before_ctx
    request_ctx.reset(request_token)
    assert request_ctx.get(None) is before_ctx

    # Cleanup
    request_ctx.reset(before_token)
