"""SQLAlchemy model for the document registry table.

Tracks every PDF uploaded for ingestion with its processing status.
Used by IngestionService to record state transitions and by admin routes
(phase 06) to list/delete documents.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Document(Base):
    """Registry of ingested PDF documents."""

    __tablename__ = "documents"

    # Primary key — internal auto-increment
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Public document identifier (UUID string) — used in Chroma metadata
    doc_id: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, default=_new_uuid
    )

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False, default=0)

    # Who uploaded it (email from JWT claim)
    uploaded_by: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # Lifecycle: processing → ready | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="processing")

    # Populated on failure; NULL when ready
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    __table_args__ = (
        Index("ix_documents_doc_id", "doc_id"),
        Index("ix_documents_domain", "domain"),
        Index("ix_documents_status", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} doc_id={self.doc_id!r} "
            f"filename={self.filename!r} domain={self.domain!r} status={self.status!r}>"
        )
