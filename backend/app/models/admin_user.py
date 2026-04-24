"""SQLAlchemy model for the admin_users allowlist table.

Email stored lowercase and indexed for fast case-insensitive lookup.
Managed via AdminService — never mutated directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AdminUser(Base):
    """Rows = email addresses permitted to access /api/admin/* routes."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Stored lowercase; unique constraint enforces one row per address
    email: Mapped[str] = mapped_column(
        String(254), unique=True, nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AdminUser id={self.id} email={self.email!r}>"
