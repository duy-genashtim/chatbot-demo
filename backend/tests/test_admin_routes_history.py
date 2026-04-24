"""Tests for admin history routes: list / export CSV / purge."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import User, require_admin
from app.main import app
from app.models.chat_turn import ChatTurn

ADMIN_USER = User(email="admin@example.com", name="Admin", is_admin=True)


def _make_client() -> TestClient:
    app.dependency_overrides[require_admin] = lambda: ADMIN_USER
    return TestClient(app, raise_server_exceptions=False)


def _clear():
    app.dependency_overrides.pop(require_admin, None)


def _fake_turn(**kwargs) -> ChatTurn:
    turn = ChatTurn(
        session_id=kwargs.get("session_id", "sess-1"),
        user_key=kwargs.get("user_key", "user@example.com"),
        mode=kwargs.get("mode", "internal"),
        role=kwargs.get("role", "user"),
        content=kwargs.get("content", "Hello"),
        tokens_in=kwargs.get("tokens_in", 10),
        tokens_cached=kwargs.get("tokens_cached", 0),
        tokens_out=kwargs.get("tokens_out", 20),
        latency_ms=kwargs.get("latency_ms", 500),
    )
    turn.id = kwargs.get("id", 1)
    turn.created_at = kwargs.get("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    return turn


# ------------------------------------------------------------------ #
# GET /history
# ------------------------------------------------------------------ #

class TestListHistory:
    def setup_method(self):
        self.client = _make_client()

    def teardown_method(self):
        _clear()

    def test_list_returns_200_array(self):
        mock_svc = MagicMock()
        mock_svc.list_turns.return_value = [_fake_turn()]
        with patch(
            "app.api.routes.admin_history_routes.ChatHistoryService",
            return_value=mock_svc,
        ):
            resp = self.client.get("/api/admin/history")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_list_turn_has_expected_fields(self):
        mock_svc = MagicMock()
        mock_svc.list_turns.return_value = [_fake_turn()]
        with patch(
            "app.api.routes.admin_history_routes.ChatHistoryService",
            return_value=mock_svc,
        ):
            resp = self.client.get("/api/admin/history")
        turn = resp.json()[0]
        for field in ("id", "session_id", "user_key", "mode", "role", "content",
                       "tokens_in", "tokens_cached", "tokens_out", "latency_ms", "created_at"):
            assert field in turn, f"Missing field: {field}"

    def test_list_passes_mode_filter(self):
        mock_svc = MagicMock()
        mock_svc.list_turns.return_value = []
        with patch(
            "app.api.routes.admin_history_routes.ChatHistoryService",
            return_value=mock_svc,
        ):
            resp = self.client.get("/api/admin/history?mode=internal")
        assert resp.status_code == 200
        mock_svc.list_turns.assert_called_once()
        call_kwargs = mock_svc.list_turns.call_args.kwargs
        assert call_kwargs.get("mode") == "internal"

    def test_list_passes_user_key_filter(self):
        mock_svc = MagicMock()
        mock_svc.list_turns.return_value = []
        with patch(
            "app.api.routes.admin_history_routes.ChatHistoryService",
            return_value=mock_svc,
        ):
            resp = self.client.get("/api/admin/history?user_key=alice%40example.com")
        assert resp.status_code == 200
        call_kwargs = mock_svc.list_turns.call_args.kwargs
        assert call_kwargs.get("user_key") == "alice@example.com"

    def test_list_respects_limit_and_offset(self):
        mock_svc = MagicMock()
        mock_svc.list_turns.return_value = []
        with patch(
            "app.api.routes.admin_history_routes.ChatHistoryService",
            return_value=mock_svc,
        ):
            resp = self.client.get("/api/admin/history?limit=10&offset=20")
        assert resp.status_code == 200
        call_kwargs = mock_svc.list_turns.call_args.kwargs
        assert call_kwargs.get("limit") == 10
        assert call_kwargs.get("offset") == 20

    def test_list_empty_result(self):
        mock_svc = MagicMock()
        mock_svc.list_turns.return_value = []
        with patch(
            "app.api.routes.admin_history_routes.ChatHistoryService",
            return_value=mock_svc,
        ):
            resp = self.client.get("/api/admin/history")
        assert resp.status_code == 200
        assert resp.json() == []


# ------------------------------------------------------------------ #
# GET /history/export.csv
# ------------------------------------------------------------------ #

class TestExportHistoryCsv:
    def setup_method(self):
        self.client = _make_client()

    def teardown_method(self):
        _clear()

    def test_export_returns_csv_content_type(self):
        mock_svc = MagicMock()
        mock_svc.export_csv.return_value = b"id,session_id\n1,sess-1\n"
        with patch(
            "app.api.routes.admin_history_routes.ChatHistoryService",
            return_value=mock_svc,
        ):
            resp = self.client.get("/api/admin/history/export.csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_export_has_content_disposition_attachment(self):
        mock_svc = MagicMock()
        mock_svc.export_csv.return_value = b"id\n1\n"
        with patch(
            "app.api.routes.admin_history_routes.ChatHistoryService",
            return_value=mock_svc,
        ):
            resp = self.client.get("/api/admin/history/export.csv")
        assert "attachment" in resp.headers.get("content-disposition", "")

    def test_export_passes_filters_to_service(self):
        mock_svc = MagicMock()
        mock_svc.export_csv.return_value = b""
        with patch(
            "app.api.routes.admin_history_routes.ChatHistoryService",
            return_value=mock_svc,
        ):
            resp = self.client.get("/api/admin/history/export.csv?mode=external")
        assert resp.status_code == 200
        call_kwargs = mock_svc.export_csv.call_args.kwargs
        assert call_kwargs.get("mode") == "external"


# ------------------------------------------------------------------ #
# DELETE /history
# ------------------------------------------------------------------ #

class TestPurgeHistory:
    def setup_method(self):
        self.client = _make_client()

    def teardown_method(self):
        _clear()

    def test_purge_without_confirm_header_returns_400(self):
        resp = self.client.delete("/api/admin/history")
        assert resp.status_code == 400
        assert "X-Confirm-Delete" in resp.json()["detail"]

    def test_purge_with_confirm_header_returns_deleted_count(self):
        mock_svc = MagicMock()
        mock_svc.purge_by_filters.return_value = 42
        with patch(
            "app.api.routes.admin_history_routes.ChatHistoryService",
            return_value=mock_svc,
        ):
            resp = self.client.delete(
                "/api/admin/history",
                headers={"X-Confirm-Delete": "yes"},
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 42

    def test_purge_wrong_confirm_value_returns_400(self):
        resp = self.client.delete(
            "/api/admin/history",
            headers={"X-Confirm-Delete": "maybe"},
        )
        assert resp.status_code == 400

    def test_purge_passes_filters_to_service(self):
        mock_svc = MagicMock()
        mock_svc.purge_by_filters.return_value = 5
        with patch(
            "app.api.routes.admin_history_routes.ChatHistoryService",
            return_value=mock_svc,
        ):
            resp = self.client.delete(
                "/api/admin/history?mode=internal&user_key=bob%40example.com",
                headers={"X-Confirm-Delete": "yes"},
            )
        assert resp.status_code == 200
        call_kwargs = mock_svc.purge_by_filters.call_args.kwargs
        assert call_kwargs.get("mode") == "internal"
        assert call_kwargs.get("user_key") == "bob@example.com"
