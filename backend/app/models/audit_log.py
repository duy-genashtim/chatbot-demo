"""SQLAlchemy model for the audit_log table.

Records every admin action: who did what, when, to which target.
Immutable — no delete endpoint exposed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    """One row per audited admin action."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Email of the admin who triggered the action
    actor_email: Mapped[str] = mapped_column(String(256), nullable=False)

    # Short action identifier, e.g. "document.upload", "settings.set"
    action: Mapped[str] = mapped_column(String(128), nullable=False)

    # Primary target of the action (doc_id, setting key, email, etc.)
    target: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)

    # Optional JSON-encoded extra context (serialised dict)
    meta: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} actor={self.actor_email!r} "
            f"action={self.action!r} target={self.target!r}>"
        )
