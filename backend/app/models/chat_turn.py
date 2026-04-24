"""SQLAlchemy model for persisted chat turns.

Every user message and assistant response is stored here for analytics,
history rehydration on reconnect, and admin audit / export.

Token fields and latency_ms are nullable:
  - user turn: tokens_in/cached/out and latency_ms are all NULL
  - assistant turn: all fields populated after stream completes
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ChatTurn(Base):
    """One turn (user OR assistant) within a chat session."""

    __tablename__ = "chat_turn"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Session / ownership
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_key: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # internal | external

    # Conversation content
    role: Mapped[str] = mapped_column(String(16), nullable=False)   # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Token accounting (null for user turns)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_cached: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Latency in milliseconds (null for user turns)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # Composite index for session timeline queries
    __table_args__ = (
        Index("ix_chat_turn_session_created", "session_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ChatTurn id={self.id} session={self.session_id!r} "
            f"role={self.role!r} mode={self.mode!r}>"
        )
