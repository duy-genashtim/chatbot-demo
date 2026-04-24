"""Unit tests for MetricsBuffer ring buffer.

Verifies thread-safety, maxlen eviction, push/snapshot/clear semantics,
and singleton factory behaviour.
"""

from __future__ import annotations

import threading

import pytest

from app.services.metrics_buffer import MetricsBuffer, get_metrics_buffer


class TestMetricsBufferBasics:
    def test_empty_snapshot_is_empty_list(self):
        buf = MetricsBuffer(maxlen=10)
        assert buf.snapshot() == []

    def test_push_and_snapshot_roundtrip(self):
        buf = MetricsBuffer(maxlen=10)
        buf.push({"req_id": "a", "total_ms": 100})
        snap = buf.snapshot()
        assert len(snap) == 1
        assert snap[0]["req_id"] == "a"

    def test_snapshot_returns_shallow_copy(self):
        buf = MetricsBuffer(maxlen=10)
        buf.push({"req_id": "b"})
        s1 = buf.snapshot()
        buf.push({"req_id": "c"})
        s2 = buf.snapshot()
        # s1 captured before second push — must still have length 1
        assert len(s1) == 1
        assert len(s2) == 2

    def test_clear_empties_buffer(self):
        buf = MetricsBuffer(maxlen=10)
        buf.push({"x": 1})
        buf.push({"x": 2})
        buf.clear()
        assert buf.snapshot() == []
        assert len(buf) == 0

    def test_len_reflects_current_size(self):
        buf = MetricsBuffer(maxlen=5)
        assert len(buf) == 0
        buf.push({})
        assert len(buf) == 1
        buf.push({})
        assert len(buf) == 2

    def test_maxlen_evicts_oldest(self):
        buf = MetricsBuffer(maxlen=3)
        for i in range(5):
            buf.push({"i": i})
        snap = buf.snapshot()
        assert len(snap) == 3
        # Oldest (i=0, i=1) should be gone; newest retained
        values = [s["i"] for s in snap]
        assert values == [2, 3, 4]

    def test_snapshot_order_oldest_first(self):
        buf = MetricsBuffer(maxlen=10)
        buf.push({"seq": 1})
        buf.push({"seq": 2})
        buf.push({"seq": 3})
        seqs = [s["seq"] for s in buf.snapshot()]
        assert seqs == [1, 2, 3]

    def test_push_accepts_arbitrary_dict(self):
        buf = MetricsBuffer(maxlen=5)
        summary = {
            "req_id": "abc123",
            "method": "POST",
            "path": "/api/internal/chat",
            "status": 200,
            "total_ms": 420,
            "llm_ttft_ms": 180,
            "input_tokens": 100,
        }
        buf.push(summary)
        assert buf.snapshot()[0] == summary


class TestMetricsBufferThreadSafety:
    def test_concurrent_pushes_no_data_loss(self):
        """100 threads each pushing 10 items → exactly 1000 in a buf(maxlen=1000)."""
        buf = MetricsBuffer(maxlen=1000)
        threads = []
        for t in range(100):
            def _push(tid=t):
                for i in range(10):
                    buf.push({"tid": tid, "i": i})
            threads.append(threading.Thread(target=_push))

        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert len(buf) == 1000

    def test_concurrent_clear_and_push_no_exception(self):
        """Interleaved push + clear must not raise."""
        buf = MetricsBuffer(maxlen=50)
        errors = []

        def _pusher():
            try:
                for _ in range(200):
                    buf.push({"v": 1})
            except Exception as exc:
                errors.append(exc)

        def _clearer():
            try:
                for _ in range(50):
                    buf.clear()
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=_pusher),
            threading.Thread(target=_pusher),
            threading.Thread(target=_clearer),
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert errors == [], f"Thread errors: {errors}"


class TestGetMetricsBufferSingleton:
    def test_returns_same_instance(self):
        b1 = get_metrics_buffer()
        b2 = get_metrics_buffer()
        assert b1 is b2

    def test_singleton_is_metrics_buffer_instance(self):
        assert isinstance(get_metrics_buffer(), MetricsBuffer)
