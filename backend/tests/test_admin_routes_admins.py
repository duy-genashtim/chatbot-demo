"""Tests for admin allowlist routes: list / add / remove."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import User, require_admin
from app.main import app
from app.models.admin_user import AdminUser

ADMIN_USER = User(email="admin@example.com", name="Admin", is_admin=True)


def _make_client() -> TestClient:
    app.dependency_overrides[require_admin] = lambda: ADMIN_USER
    return TestClient(app, raise_server_exceptions=False)


def _clear():
    app.dependency_overrides.pop(require_admin, None)


def _fake_admin(email: str) -> AdminUser:
    row = AdminUser(email=email)
    row.id = 1
    row.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return row


# ------------------------------------------------------------------ #
# GET /admins
# ------------------------------------------------------------------ #

class TestListAdmins:
    def setup_method(self):
        self.client = _make_client()

    def teardown_method(self):
        _clear()

    def test_list_returns_200_array(self):
        mock_svc = MagicMock()
        mock_svc.list_admins.return_value = [_fake_admin("admin@example.com")]
        with patch(
            "app.api.routes.admin_admins_routes.AdminService",
            return_value=mock_svc,
        ):
            resp = self.client.get("/api/admin/admins")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["email"] == "admin@example.com"

    def test_list_returns_created_at(self):
        mock_svc = MagicMock()
        mock_svc.list_admins.return_value = [_fake_admin("admin@example.com")]
        with patch(
            "app.api.routes.admin_admins_routes.AdminService",
            return_value=mock_svc,
        ):
            resp = self.client.get("/api/admin/admins")
        assert "created_at" in resp.json()[0]


# ------------------------------------------------------------------ #
# POST /admins
# ------------------------------------------------------------------ #

class TestAddAdmin:
    def setup_method(self):
        self.client = _make_client()

    def teardown_method(self):
        _clear()

    def test_add_new_admin_returns_201(self):
        new_row = _fake_admin("new@example.com")
        mock_svc = MagicMock()
        mock_svc.add_admin.return_value = new_row
        with patch(
            "app.api.routes.admin_admins_routes.AdminService",
            return_value=mock_svc,
        ):
            resp = self.client.post(
                "/api/admin/admins", json={"email": "new@example.com"}
            )
        assert resp.status_code == 201
        assert resp.json()["email"] == "new@example.com"

    def test_add_duplicate_returns_400(self):
        mock_svc = MagicMock()
        mock_svc.add_admin.side_effect = ValueError("Email already in admin list")
        with patch(
            "app.api.routes.admin_admins_routes.AdminService",
            return_value=mock_svc,
        ):
            resp = self.client.post(
                "/api/admin/admins", json={"email": "admin@example.com"}
            )
        assert resp.status_code == 400

    def test_add_invalid_email_returns_400(self):
        resp = self.client.post(
            "/api/admin/admins", json={"email": "not-an-email"}
        )
        assert resp.status_code == 400
        assert "Invalid email" in resp.json()["detail"]

    def test_add_email_is_lowercased(self):
        new_row = _fake_admin("upper@example.com")
        mock_svc = MagicMock()
        mock_svc.add_admin.return_value = new_row
        with patch(
            "app.api.routes.admin_admins_routes.AdminService",
            return_value=mock_svc,
        ):
            resp = self.client.post(
                "/api/admin/admins", json={"email": "UPPER@EXAMPLE.COM"}
            )
        assert resp.status_code == 201
        mock_svc.add_admin.assert_called_once_with("upper@example.com")


# ------------------------------------------------------------------ #
# DELETE /admins/{email}
# ------------------------------------------------------------------ #

class TestRemoveAdmin:
    def setup_method(self):
        self.client = _make_client()

    def teardown_method(self):
        _clear()

    def test_remove_other_admin_succeeds(self):
        mock_svc = MagicMock()
        mock_svc.count_admins.return_value = 2
        mock_svc.remove_admin.return_value = None
        with patch(
            "app.api.routes.admin_admins_routes.AdminService",
            return_value=mock_svc,
        ):
            resp = self.client.delete("/api/admin/admins/other@example.com")
        assert resp.status_code == 200
        assert resp.json()["removed"] == "other@example.com"

    def test_self_removal_returns_400(self):
        resp = self.client.delete("/api/admin/admins/admin@example.com")
        assert resp.status_code == 400
        assert "yourself" in resp.json()["detail"]

    def test_last_admin_removal_returns_400(self):
        mock_svc = MagicMock()
        mock_svc.count_admins.return_value = 1
        with patch(
            "app.api.routes.admin_admins_routes.AdminService",
            return_value=mock_svc,
        ):
            resp = self.client.delete("/api/admin/admins/other@example.com")
        assert resp.status_code == 400
        assert "last admin" in resp.json()["detail"]

    def test_remove_nonexistent_email_returns_404(self):
        mock_svc = MagicMock()
        mock_svc.count_admins.return_value = 3
        mock_svc.remove_admin.side_effect = ValueError("Email not in admin list")
        with patch(
            "app.api.routes.admin_admins_routes.AdminService",
            return_value=mock_svc,
        ):
            resp = self.client.delete("/api/admin/admins/ghost@example.com")
        assert resp.status_code == 404
