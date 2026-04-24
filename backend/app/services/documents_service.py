"""Documents registry service — thin wrapper over the Document model.

Provides list/get/delete operations on the documents table.
Actual ingestion (parse → embed → store) is delegated to IngestionService.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.document import Document

logger = logging.getLogger(__name__)


class DocumentsService:
    """Read/delete operations on the documents registry for a single DB session."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_documents(self, domain: str | None = None) -> list[Document]:
        """Return all document rows, optionally filtered by domain."""
        q = self._db.query(Document).order_by(Document.uploaded_at.desc())
        if domain is not None:
            q = q.filter(Document.domain == domain)
        return q.all()

    def get_by_doc_id(self, doc_id: str) -> Document | None:
        """Return the Document row for a given doc_id UUID, or None."""
        return self._db.query(Document).filter(Document.doc_id == doc_id).first()

    def to_dict(self, doc: Document) -> dict[str, Any]:
        """Serialise a Document row to a plain dict for JSON responses."""
        return {
            "id": doc.id,
            "doc_id": doc.doc_id,
            "filename": doc.filename,
            "domain": doc.domain,
            "size_bytes": doc.size_bytes,
            "uploaded_by": doc.uploaded_by,
            "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            "status": doc.status,
            "error_msg": doc.error_msg,
        }


def get_documents_service(db: Session) -> DocumentsService:
    """FastAPI dependency factory."""
    return DocumentsService(db)
