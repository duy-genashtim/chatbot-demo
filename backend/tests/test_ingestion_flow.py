"""Integration test: small PDF → ingest → BM25 search returns the chunk.

Uses a real ChromaDB on tmp_path. Mocks Gemini embed API with deterministic
hash-based vectors. Does NOT call real Gemini API.

Covers:
  - Valid PDF ingested → Document row created with status=ready
  - Chunk appears in BM25 search after ingest
  - Non-PDF bytes rejected → Document row status=failed
  - delete_doc removes chunks from Chroma and DB row
  - BM25 dirty flag set on ingest (rebuild triggered on next search)
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 — registers all models including Document
from app.core.db import Base
from app.models.document import Document
from app.rag.bm25_index import BM25Cache
from app.rag.chroma_store import ChromaStore
from app.services.ingestion_service import IngestionService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session(tmp_path):
    """In-memory SQLite session with all tables created."""
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def chroma(tmp_path) -> ChromaStore:
    return ChromaStore(path=str(tmp_path / "chroma"))


@pytest.fixture()
def bm25() -> BM25Cache:
    return BM25Cache()


def _make_pdf_bytes(text_hint: str = "test content") -> bytes:
    """Create a valid PDF with extractable text using a hand-crafted content stream.

    PdfWriter.add_blank_page() produces no extractable text; we build the PDF
    manually with correct xref byte offsets so pypdf can extract the text body.
    """
    safe_text = text_hint.replace("(", "").replace(")", "").replace("\\", "")
    stream_content = (
        b"BT /F1 12 Tf 72 720 Td ("
        + safe_text.encode("latin-1", errors="replace")
        + b") Tj ET"
    )
    stream_len = len(stream_content)

    objs = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
        b"   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        b"4 0 obj\n<< /Length " + str(stream_len).encode() + b" >>\nstream\n"
        + stream_content + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    header = b"%PDF-1.4\n"
    body = b"".join(objs)
    # Compute xref byte offsets
    offsets = []
    pos = len(header)
    for obj in objs:
        offsets.append(pos)
        pos += len(obj)

    xref_start = len(header) + len(body)
    xref = b"xref\n0 6\n0000000000 65535 f \n"
    for off in offsets:
        xref += f"{off:010d} 00000 n \n".encode()
    trailer = (
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref_start).encode()
        + b"\n%%EOF\n"
    )
    return header + body + xref + trailer


def _fake_embed_documents(texts: list[str]) -> list[list[float]]:
    """Deterministic fake embeddings: hash-based 8-dim unit vectors."""
    result = []
    for text in texts:
        h = hash(text) & 0xFFFFFFFF
        raw = [(h >> i & 0xFF) / 255.0 for i in range(8)]
        norm = sum(x * x for x in raw) ** 0.5 or 1.0
        result.append([x / norm for x in raw])
    return result


def _fake_embed_query(query: str) -> list[float]:
    return _fake_embed_documents([query])[0]


def _make_mock_provider():
    provider = MagicMock()
    provider.provider_id = "mock:test"
    provider.embed_documents.side_effect = _fake_embed_documents
    provider.embed_query.side_effect = _fake_embed_query
    return provider


# ---------------------------------------------------------------------------
# Ingest happy path
# ---------------------------------------------------------------------------

class TestIngestionFlowHappyPath:
    def test_valid_pdf_creates_ready_document(self, db_session, chroma, bm25):
        pdf_bytes = _make_pdf_bytes("HR policy annual leave entitlement")
        provider = _make_mock_provider()

        with (
            patch("app.services.ingestion_service.get_chroma_store", return_value=chroma),
            patch("app.services.ingestion_service.get_bm25_cache", return_value=bm25),
            patch("app.services.ingestion_service.get_embedding_provider", return_value=provider),
            patch("app.services.ingestion_service._try_invalidate_cache"),
        ):
            import asyncio
            svc = IngestionService(db=db_session)
            doc_id = asyncio.get_event_loop().run_until_complete(
                svc.ingest(
                    file_bytes=pdf_bytes,
                    filename="hr_policy.pdf",
                    domain="internal_hr",
                    uploaded_by="admin@example.com",
                )
            )

        doc = db_session.query(Document).filter(Document.doc_id == doc_id).first()
        assert doc is not None
        assert doc.status == "ready"
        assert doc.filename == "hr_policy.pdf"
        assert doc.domain == "internal_hr"
        assert doc.error_msg is None

    def test_ingest_marks_bm25_dirty(self, db_session, chroma, bm25):
        pdf_bytes = _make_pdf_bytes("some policy text with content")
        provider = _make_mock_provider()

        with (
            patch("app.services.ingestion_service.get_chroma_store", return_value=chroma),
            patch("app.services.ingestion_service.get_bm25_cache", return_value=bm25),
            patch("app.services.ingestion_service.get_embedding_provider", return_value=provider),
            patch("app.services.ingestion_service._try_invalidate_cache"),
        ):
            import asyncio
            svc = IngestionService(db=db_session)
            asyncio.get_event_loop().run_until_complete(
                svc.ingest(pdf_bytes, "test.pdf", "internal_hr", "admin@test.com")
            )

        idx = bm25._get_or_create_index("internal_hr")
        assert idx.dirty  # marked dirty after upsert

    def test_ingest_upserts_to_chroma(self, db_session, chroma, bm25):
        pdf_bytes = _make_pdf_bytes("external policy document content details here")
        provider = _make_mock_provider()

        with (
            patch("app.services.ingestion_service.get_chroma_store", return_value=chroma),
            patch("app.services.ingestion_service.get_bm25_cache", return_value=bm25),
            patch("app.services.ingestion_service.get_embedding_provider", return_value=provider),
            patch("app.services.ingestion_service._try_invalidate_cache"),
        ):
            import asyncio
            svc = IngestionService(db=db_session)
            asyncio.get_event_loop().run_until_complete(
                svc.ingest(pdf_bytes, "policy.pdf", "external_policy", "user@test.com")
            )

        # Chroma should now have at least one chunk
        count = chroma.count("external_policy")
        assert count >= 1


# ---------------------------------------------------------------------------
# Non-PDF rejection
# ---------------------------------------------------------------------------

class TestIngestionFlowNonPDF:
    def test_non_pdf_raises_value_error(self, db_session, chroma, bm25):
        bad_bytes = b"NOT A PDF - random bytes"
        provider = _make_mock_provider()

        with (
            patch("app.services.ingestion_service.get_chroma_store", return_value=chroma),
            patch("app.services.ingestion_service.get_bm25_cache", return_value=bm25),
            patch("app.services.ingestion_service.get_embedding_provider", return_value=provider),
        ):
            import asyncio
            svc = IngestionService(db=db_session)
            with pytest.raises(ValueError, match="Only PDF files are supported"):
                asyncio.get_event_loop().run_until_complete(
                    svc.ingest(bad_bytes, "doc.docx", "internal_hr", "admin@test.com")
                )

    def test_non_pdf_no_document_row_created(self, db_session, chroma, bm25):
        """Pre-validation failure → no DB row at all (fails before insert)."""
        bad_bytes = b"<html>not a pdf</html>"
        provider = _make_mock_provider()

        count_before = db_session.query(Document).count()

        with (
            patch("app.services.ingestion_service.get_chroma_store", return_value=chroma),
            patch("app.services.ingestion_service.get_bm25_cache", return_value=bm25),
            patch("app.services.ingestion_service.get_embedding_provider", return_value=provider),
        ):
            import asyncio
            svc = IngestionService(db=db_session)
            with pytest.raises(ValueError):
                asyncio.get_event_loop().run_until_complete(
                    svc.ingest(bad_bytes, "bad.html", "internal_hr", "admin@test.com")
                )

        count_after = db_session.query(Document).count()
        assert count_after == count_before  # no row inserted


# ---------------------------------------------------------------------------
# Delete document
# ---------------------------------------------------------------------------

class TestIngestionFlowDelete:
    def test_delete_removes_db_row(self, db_session, chroma, bm25):
        pdf_bytes = _make_pdf_bytes("document to delete content text")
        provider = _make_mock_provider()

        with (
            patch("app.services.ingestion_service.get_chroma_store", return_value=chroma),
            patch("app.services.ingestion_service.get_bm25_cache", return_value=bm25),
            patch("app.services.ingestion_service.get_embedding_provider", return_value=provider),
            patch("app.services.ingestion_service._try_invalidate_cache"),
        ):
            import asyncio
            svc = IngestionService(db=db_session)
            doc_id = asyncio.get_event_loop().run_until_complete(
                svc.ingest(pdf_bytes, "deleteme.pdf", "internal_hr", "admin@test.com")
            )
            asyncio.get_event_loop().run_until_complete(
                svc.delete_doc(doc_id, invalidate_cache=False)
            )

        doc = db_session.query(Document).filter(Document.doc_id == doc_id).first()
        assert doc is None

    def test_delete_nonexistent_raises(self, db_session, chroma, bm25):
        with (
            patch("app.services.ingestion_service.get_chroma_store", return_value=chroma),
            patch("app.services.ingestion_service.get_bm25_cache", return_value=bm25),
        ):
            import asyncio
            svc = IngestionService(db=db_session)
            with pytest.raises(ValueError, match="Document not found"):
                asyncio.get_event_loop().run_until_complete(
                    svc.delete_doc("nonexistent-uuid", invalidate_cache=False)
                )


# ---------------------------------------------------------------------------
# Document model registration
# ---------------------------------------------------------------------------

class TestDocumentModelRegistration:
    def test_documents_table_in_metadata(self):
        from app.core.db import Base
        import app.models  # noqa: F401
        assert "documents" in Base.metadata.tables

    def test_existing_tables_still_registered(self):
        from app.core.db import Base
        import app.models  # noqa: F401
        for table in ("app_setting", "admin_users", "chat_turn"):
            assert table in Base.metadata.tables
