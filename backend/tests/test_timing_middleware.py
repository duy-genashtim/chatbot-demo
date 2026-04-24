"""Tests for TimingMiddleware — verifies request_context capture and ring push.

Strategy:
  - Mount a minimal test FastAPI app with TimingMiddleware.
  - Inject a fake route that calls record() with known stage values.
  - Hit the route via httpx AsyncClient.
  - Assert metrics buffer received a summary with the expected fields.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.middleware.timing_middleware import TimingMiddleware
from app.core.request_context import record
from app.services.metrics_buffer import MetricsBuffer


# ------------------------------------------------------------------ #
# Minimal test app
# ------------------------------------------------------------------ #

def _make_test_app(extra_records: dict | None = None) -> tuple[FastAPI, MetricsBuffer]:
    """Build a tiny FastAPI app with TimingMiddleware + a fake /probe route.

    The /probe route calls record() for each key in extra_records so the
    middleware can collect them and push to the provided MetricsBuffer.
    """
    buf = MetricsBuffer()
    test_app = FastAPI()

    # Patch the buffer used inside TimingMiddleware to our isolated instance
    import app.services.metrics_buffer as _mb_mod
    original = _mb_mod._buffer

    _mb_mod._buffer = buf  # redirect singleton for this test app

    @test_app.get("/probe")
    async def probe():
        if extra_records:
            for k, v in extra_records.items():
                record(k, v)
        return {"ok": True}

    test_app.add_middleware(TimingMiddleware)
    return test_app, buf, _mb_mod, original


@pytest.mark.asyncio
async def test_middleware_pushes_summary_to_buffer():
    """Every request must push exactly one summary to MetricsBuffer."""
    test_app, buf, _mb_mod, original = _make_test_app()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as c:
            resp = await c.get("/probe")
    finally:
        _mb_mod._buffer = original

    assert resp.status_code == 200
    assert len(buf) == 1


@pytest.mark.asyncio
async def test_middleware_summary_has_required_fields():
    """Summary must contain req_id, method, path, status, total_ms."""
    test_app, buf, _mb_mod, original = _make_test_app()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as c:
            await c.get("/probe")
    finally:
        _mb_mod._buffer = original

    summary = buf.snapshot()[0]
    assert "req_id" in summary
    assert summary["method"] == "GET"
    assert summary["path"] == "/probe"
    assert summary["status"] == 200
    assert isinstance(summary["total_ms"], int)
    assert summary["total_ms"] >= 0


@pytest.mark.asyncio
async def test_middleware_captures_stage_values_from_request_context():
    """Stage values written via record() inside the handler appear in summary."""
    stages = {
        "retrieval_total_ms": 50,
        "embed_ms": 12,
        "vector_ms": 20,
        "bm25_ms": 10,
        "rerank_ms": 8,
        "llm_ttft_ms": 180,
        "llm_total_ms": 400,
    }
    test_app, buf, _mb_mod, original = _make_test_app(extra_records=stages)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as c:
            await c.get("/probe")
    finally:
        _mb_mod._buffer = original

    summary = buf.snapshot()[0]
    for key, expected in stages.items():
        assert summary.get(key) == expected, f"{key}: expected {expected}, got {summary.get(key)}"


@pytest.mark.asyncio
async def test_middleware_multiple_requests_multiple_summaries():
    """Each request produces an independent summary entry."""
    test_app, buf, _mb_mod, original = _make_test_app()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as c:
            await c.get("/probe")
            await c.get("/probe")
            await c.get("/probe")
    finally:
        _mb_mod._buffer = original

    assert len(buf) == 3
    req_ids = [s["req_id"] for s in buf.snapshot()]
    # Each request gets a unique req_id
    assert len(set(req_ids)) == 3


@pytest.mark.asyncio
async def test_middleware_no_cross_request_context_contamination():
    """Stage values from one request must not leak into the next."""
    call_count = {"n": 0}

    test_app2 = FastAPI()
    buf2 = MetricsBuffer()
    import app.services.metrics_buffer as _mb_mod2
    original2 = _mb_mod2._buffer
    _mb_mod2._buffer = buf2

    @test_app2.get("/conditional")
    async def conditional():
        call_count["n"] += 1
        if call_count["n"] == 1:
            record("embed_ms", 99)  # only first request records this
        return {"n": call_count["n"]}

    test_app2.add_middleware(TimingMiddleware)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app2), base_url="http://test"
        ) as c:
            await c.get("/conditional")
            await c.get("/conditional")
    finally:
        _mb_mod2._buffer = original2

    snapshots = buf2.snapshot()
    assert snapshots[0].get("embed_ms") == 99
    assert "embed_ms" not in snapshots[1]  # second request never called record()
