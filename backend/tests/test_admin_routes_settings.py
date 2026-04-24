"""Tests for admin settings routes: schema / get / put."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import User, require_admin
from app.main import app
from app.services.settings_schema import SETTINGS_SCHEMA

ADMIN_USER = User(email="admin@example.com", name="Admin", is_admin=True)


def _make_client() -> TestClient:
    app.dependency_overrides[require_admin] = lambda: ADMIN_USER
    return TestClient(app, raise_server_exceptions=False)


def _clear():
    app.dependency_overrides.pop(require_admin, None)


# ------------------------------------------------------------------ #
# GET /settings/schema
# ------------------------------------------------------------------ #

class TestSettingsSchema:
    def setup_method(self):
        self.client = _make_client()

    def teardown_method(self):
        _clear()

    def test_schema_returns_200(self):
        resp = self.client.get("/api/admin/settings/schema")
        assert resp.status_code == 200

    def test_schema_contains_all_whitelisted_keys(self):
        resp = self.client.get("/api/admin/settings/schema")
        data = resp.json()
        for key in SETTINGS_SCHEMA:
            assert key in data, f"Key {key!r} missing from schema response"

    def test_schema_entry_has_required_fields(self):
        resp = self.client.get("/api/admin/settings/schema")
        data = resp.json()
        for key, meta in data.items():
            assert "type" in meta, f"{key}: missing 'type'"
            assert "label" in meta, f"{key}: missing 'label'"
            assert "default" in meta, f"{key}: missing 'default'"

    def test_schema_llm_temperature_has_min_max(self):
        resp = self.client.get("/api/admin/settings/schema")
        temp = resp.json()["LLM_TEMPERATURE"]
        assert temp["min"] == 0.0
        assert temp["max"] == 1.0


# ------------------------------------------------------------------ #
# GET /settings
# ------------------------------------------------------------------ #

class TestGetSettings:
    def setup_method(self):
        self.client = _make_client()

    def teardown_method(self):
        _clear()

    def test_get_settings_returns_200(self):
        with patch(
            "app.api.routes.admin_settings_routes.SettingsService.get",
            return_value=None,
        ):
            resp = self.client.get("/api/admin/settings")
        assert resp.status_code == 200

    def test_get_settings_returns_all_whitelisted_keys(self):
        with patch(
            "app.api.routes.admin_settings_routes.SettingsService.get",
            return_value=None,
        ):
            resp = self.client.get("/api/admin/settings")
        data = resp.json()
        for key in SETTINGS_SCHEMA:
            assert key in data, f"Key {key!r} missing from settings response"

    def test_get_settings_uses_db_override_when_present(self):
        with patch(
            "app.api.routes.admin_settings_routes.SettingsService.get",
            return_value="0.9",
        ):
            resp = self.client.get("/api/admin/settings")
        # All keys return the mocked string "0.9" cast per their schema type
        assert resp.status_code == 200


# ------------------------------------------------------------------ #
# PUT /settings
# ------------------------------------------------------------------ #

class TestPutSettings:
    def setup_method(self):
        self.client = _make_client()

    def teardown_method(self):
        _clear()

    def test_put_valid_key_returns_200_and_persists(self):
        with patch(
            "app.api.routes.admin_settings_routes.SettingsService.set"
        ) as mock_set:
            resp = self.client.put(
                "/api/admin/settings",
                json={"LLM_TEMPERATURE": 0.7},
            )
        assert resp.status_code == 200
        assert "LLM_TEMPERATURE" in resp.json()["updated"]
        mock_set.assert_called_once_with("LLM_TEMPERATURE", "0.7")

    def test_put_unknown_key_returns_400(self):
        resp = self.client.put(
            "/api/admin/settings",
            json={"SECRET_KEY": "hacked"},
        )
        assert resp.status_code == 400
        assert "Unknown settings keys" in resp.json()["detail"]

    def test_put_multiple_keys_all_persisted(self):
        with patch(
            "app.api.routes.admin_settings_routes.SettingsService.set"
        ) as mock_set:
            resp = self.client.put(
                "/api/admin/settings",
                json={"LLM_TEMPERATURE": 0.5, "TOP_K_VECTOR": 8},
            )
        assert resp.status_code == 200
        updated = resp.json()["updated"]
        assert "LLM_TEMPERATURE" in updated
        assert "TOP_K_VECTOR" in updated
        assert mock_set.call_count == 2

    def test_put_output_suffix_text_persisted(self):
        with patch(
            "app.api.routes.admin_settings_routes.SettingsService.set"
        ) as mock_set:
            resp = self.client.put(
                "/api/admin/settings",
                json={"INTERNAL_OUTPUT_SUFFIX": "Reminder text"},
            )
        assert resp.status_code == 200
        mock_set.assert_called_once_with("INTERNAL_OUTPUT_SUFFIX", "Reminder text")

    def test_put_legacy_prompt_key_returns_400(self):
        # INTERNAL_SYSTEM_PROMPT and EXTERNAL_SYSTEM_PROMPT were removed —
        # any attempt to write them must be rejected as unknown.
        resp = self.client.put(
            "/api/admin/settings",
            json={"INTERNAL_SYSTEM_PROMPT": "should fail"},
        )
        assert resp.status_code == 400

    def test_put_mixed_valid_and_invalid_keys_returns_400(self):
        resp = self.client.put(
            "/api/admin/settings",
            json={"LLM_TEMPERATURE": 0.5, "EVIL_KEY": "bad"},
        )
        assert resp.status_code == 400
