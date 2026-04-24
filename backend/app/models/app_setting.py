"""SQLAlchemy model for the app_setting table.

Stores admin-editable runtime overrides. Resolution priority:
  app_setting (DB) > .env > hard default  (see core/settings-service.py)

Columns:
  key        — setting name, e.g. "LLM_TEMPERATURE" (PK)
  value      — always stored as TEXT; caller casts to desired type
  updated_at — UTC timestamp of last write
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AppSetting(Base):
    """Runtime setting override stored in SQLite."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<AppSetting key={self.key!r} value={self.value!r}>"
