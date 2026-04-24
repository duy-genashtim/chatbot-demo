"""Tests for app.api.sse — SSE event formatting helpers."""

from __future__ import annotations

import json

import pytest

from app.api.sse import format_sse_event, keepalive_comment


class TestFormatSseEvent:
    def test_basic_dict_event(self):
        result = format_sse_event("delta", {"text": "hello"})
        assert result == 'event: delta\ndata: {"text":"hello"}\n\n'

    def test_event_ends_with_double_newline(self):
        result = format_sse_event("done", {"session_id": "abc", "latency_ms": 100})
        assert result.endswith("\n\n")

    def test_event_name_in_output(self):
        result = format_sse_event("sources", [])
        assert result.startswith("event: sources\n")

    def test_list_payload(self):
        payload = [{"source": "doc.pdf", "section": "intro"}]
        result = format_sse_event("sources", payload)
        assert "data: " in result
        # Extract the JSON from data line
        data_line = [l for l in result.splitlines() if l.startswith("data: ")][0]
        parsed = json.loads(data_line[len("data: "):])
        assert parsed == payload

    def test_json_escaping_special_chars(self):
        # newlines and quotes in text must be JSON-escaped
        result = format_sse_event("delta", {"text": 'line1\nline2 "quoted"'})
        data_line = [l for l in result.splitlines() if l.startswith("data: ")][0]
        parsed = json.loads(data_line[len("data: "):])
        assert parsed["text"] == 'line1\nline2 "quoted"'

    def test_unicode_preserved(self):
        result = format_sse_event("delta", {"text": "こんにちは"})
        data_line = [l for l in result.splitlines() if l.startswith("data: ")][0]
        parsed = json.loads(data_line[len("data: "):])
        assert parsed["text"] == "こんにちは"

    def test_error_event(self):
        result = format_sse_event("error", {"message": "something failed"})
        assert "event: error" in result
        assert "something failed" in result

    def test_empty_list_payload(self):
        result = format_sse_event("sources", [])
        data_line = [l for l in result.splitlines() if l.startswith("data: ")][0]
        parsed = json.loads(data_line[len("data: "):])
        assert parsed == []

    def test_done_event_structure(self):
        result = format_sse_event("done", {"session_id": "xyz", "latency_ms": 250})
        data_line = [l for l in result.splitlines() if l.startswith("data: ")][0]
        parsed = json.loads(data_line[len("data: "):])
        assert parsed["session_id"] == "xyz"
        assert parsed["latency_ms"] == 250


class TestKeepaliveComment:
    def test_starts_with_colon(self):
        result = keepalive_comment()
        assert result.startswith(":")

    def test_ends_with_double_newline(self):
        result = keepalive_comment()
        assert result.endswith("\n\n")
