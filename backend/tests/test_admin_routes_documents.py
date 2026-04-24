"""Tests for admin document routes: upload / list / delete.

IngestionService is overridden so no real Chroma / Gemini calls occur.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.auth.dependencies import User, require_admin


# ------------------------------------------------------------------ #
# Shared fixtures
# ------------------------------------------------------------------ #

ADMIN_USER = User(email="admin@example.com", name="Admin", is_admin=True)

# Minimal valid PDF bytes
_PDF_BYTES = b"%PDF-1.4 test content"


def _make_client() -> TestClient:
    app.dependency_overrides[require_admin] = lambda: ADMIN_USER
    return TestClient(app, raise_server_exceptions=False)


def _clear_overrides():
    app.dependency_overrides.pop(require_admin, None)


# ------------------------------------------------------------------ #
# Helper: build a fake IngestionService
# ------------------------------------------------------------------ #

def _mock_ingest_svc(doc_id="test-doc-id-123"):
    svc = MagicMock()
    svc.ingest = AsyncMock(return_value=doc_id)
    svc.delete_doc = AsyncMock(return_value=None)
    return svc


# ------------------------------------------------------------------ #
# Upload tests
# ------------------------------------------------------------------ #

class TestDocumentUpload:
    def setup_method(self):
        self.client = _make_client()

    def teardown_method(self):
        _clear_overrides()

    def test_upload_valid_pdf_returns_202(self):
        mock_svc = _mock_ingest_svc()
        with patch(
            "app.api.routes.admin_documents_routes.get_ingestion_service",
            return_value=mock_svc,
        ):
            resp = self.client.post(
                "/api/admin/documents/upload?domain=internal_hr",
                files={"file": ("test.pdf", io.BytesIO(_PDF_BYTES), "application/pdf")},
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "processing"
        assert data["filename"] == "test.pdf"
        assert data["domain"] == "internal_hr"

    def test_upload_non_pdf_returns_400(self):
        resp = self.client.post(
            "/api/admin/documents/upload?domain=internal_hr",
            files={"file": ("test.txt", io.BytesIO(b"not a pdf"), "text/plain")},
        )
        assert resp.status_code == 400
        assert "not a valid PDF" in resp.json()["detail"]

    def test_upload_invalid_domain_returns_400(self):
        resp = self.client.post(
            "/api/admin/documents/upload?domain=bad_domain",
            files={"file": ("test.pdf", io.BytesIO(_PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 400
        assert "Invalid domain" in resp.json()["detail"]

    def test_upload_empty_file_returns_400(self):
        resp = self.client.post(
            "/api/admin/documents/upload?domain=internal_hr",
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        )
        assert resp.status_code == 400

    def test_upload_external_policy_domain_accepted(self):
        mock_svc = _mock_ingest_svc()
        with patch(
            "app.api.routes.admin_documents_routes.get_ingestion_service",
            return_value=mock_svc,
        ):
            resp = self.client.post(
                "/api/admin/documents/upload?domain=external_policy",
                files={"file": ("policy.pdf", io.BytesIO(_PDF_BYTES), "application/pdf")},
            )
        assert resp.status_code == 202


# ------------------------------------------------------------------ #
# List tests
# ------------------------------------------------------------------ #

class TestDocumentList:
    def setup_method(self):
        self.client = _make_client()

    def teardown_method(self):
        _clear_overrides()

    def test_list_returns_200_with_array(self):
        from app.services.documents_service import DocumentsService

        mock_svc = MagicMock(spec=DocumentsService)
        mock_svc.list_documents.return_value = []
        mock_svc.to_dict.return_value = {}

        with patch(
            "app.api.routes.admin_documents_routes.DocumentsService",
            return_value=mock_svc,
        ):
            resp = self.client.get("/api/admin/documents")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_with_domain_filter(self):
        from app.services.documents_service import DocumentsService

        mock_svc = MagicMock(spec=DocumentsService)
        mock_svc.list_documents.return_value = []
        mock_svc.to_dict.return_value = {}

        with patch(
            "app.api.routes.admin_documents_routes.DocumentsService",
            return_value=mock_svc,
        ):
            resp = self.client.get("/api/admin/documents?domain=internal_hr")
        assert resp.status_code == 200
        mock_svc.list_documents.assert_called_once_with(domain="internal_hr")


# ------------------------------------------------------------------ #
# Delete tests
# ------------------------------------------------------------------ #

class TestDocumentDelete:
    def setup_method(self):
        self.client = _make_client()

    def teardown_method(self):
        _clear_overrides()

    def test_delete_existing_doc_returns_200(self):
        mock_svc = _mock_ingest_svc()
        with patch(
            "app.api.routes.admin_documents_routes.get_ingestion_service",
            return_value=mock_svc,
        ):
            resp = self.client.delete("/api/admin/documents/some-doc-id")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == "some-doc-id"

    def test_delete_nonexistent_doc_returns_404(self):
        from app.services.ingestion_service import IngestionService

        mock_svc = MagicMock(spec=IngestionService)
        mock_svc.delete_doc = AsyncMock(side_effect=ValueError("Document not found"))

        with patch(
            "app.api.routes.admin_documents_routes.get_ingestion_service",
            return_value=mock_svc,
        ):
            resp = self.client.delete("/api/admin/documents/no-such-id")
        assert resp.status_code == 404

    def test_delete_passes_invalidate_cache_flag(self):
        mock_svc = _mock_ingest_svc()
        with patch(
            "app.api.routes.admin_documents_routes.get_ingestion_service",
            return_value=mock_svc,
        ):
            resp = self.client.delete(
                "/api/admin/documents/some-doc-id?invalidate_cache=false"
            )
        assert resp.status_code == 200
        mock_svc.delete_doc.assert_awaited_once_with(
            "some-doc-id", invalidate_cache=False
        )
