"""Chat history persistence service.

Provides:
  - persist_turn()       — insert one ChatTurn row (non-blocking design)
  - rehydrate()          — fetch last N turns for a session (asc order)
  - list_sessions()      — admin viewer: distinct session summary rows
  - export_csv()         — CSV bytes for download
  - purge_older_than()   — retention cron: delete rows older than N days
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import asc, delete, distinct, func, select
from sqlalchemy.orm import Session

from app.models.chat_turn import ChatTurn

logger = logging.getLogger(__name__)


class ChatHistoryService:
    """Operate on the chat_turn table via a provided SQLAlchemy session."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------ #
    # Write path
    # ------------------------------------------------------------------ #

    def persist_turn(
        self,
        session_id: str,
        user_key: str,
        mode: str,
        role: str,
        content: str,
        tokens_in: int | None = None,
        tokens_cached: int | None = None,
        tokens_out: int | None = None,
        latency_ms: int | None = None,
    ) -> ChatTurn:
        """Insert a ChatTurn row and return it.

        User turns: call with tokens_* and latency_ms omitted (all None).
        Assistant turns: supply token counts and latency_ms after stream ends.
        """
        turn = ChatTurn(
            session_id=session_id,
            user_key=user_key,
            mode=mode,
            role=role,
            content=content,
            tokens_in=tokens_in,
            tokens_cached=tokens_cached,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            created_at=datetime.now(timezone.utc),
        )
        try:
            self._db.add(turn)
            self._db.commit()
            self._db.refresh(turn)
        except Exception:
            self._db.rollback()
            raise
        return turn

    # ------------------------------------------------------------------ #
    # Read path
    # ------------------------------------------------------------------ #

    def rehydrate(self, session_id: str, n: int) -> list[ChatTurn]:
        """Return the last *n* turns for *session_id* in ascending order.

        Used to rebuild in-memory history after a backend restart.
        Returns empty list when n == 0 or session has no history.
        """
        if n <= 0:
            return []
        stmt = (
            select(ChatTurn)
            .where(ChatTurn.session_id == session_id)
            .order_by(ChatTurn.created_at.desc())
            .limit(n)
        )
        rows = self._db.execute(stmt).scalars().all()
        # Reverse so oldest is first (ascending conversation order)
        return list(reversed(rows))

    def list_sessions(
        self,
        mode: str | None = None,
        user_key: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        session_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return per-session summary rows for the admin history viewer.

        Each row: session_id, user_key, mode, turn_count, first_at, last_at,
        tokens_in_sum, tokens_out_sum, tokens_cached_sum, avg_latency_ms.
        """
        stmt = (
            select(
                ChatTurn.session_id,
                ChatTurn.user_key,
                ChatTurn.mode,
                func.count(ChatTurn.id).label("turn_count"),
                func.min(ChatTurn.created_at).label("first_at"),
                func.max(ChatTurn.created_at).label("last_at"),
                func.coalesce(func.sum(ChatTurn.tokens_in), 0).label("tokens_in_sum"),
                func.coalesce(func.sum(ChatTurn.tokens_out), 0).label("tokens_out_sum"),
                func.coalesce(func.sum(ChatTurn.tokens_cached), 0).label("tokens_cached_sum"),
                func.avg(ChatTurn.latency_ms).label("avg_latency_ms"),
            )
            .group_by(ChatTurn.session_id, ChatTurn.user_key, ChatTurn.mode)
            .order_by(func.max(ChatTurn.created_at).desc())
            .limit(limit)
            .offset(offset)
        )

        if mode is not None:
            stmt = stmt.where(ChatTurn.mode == mode)
        if user_key is not None:
            stmt = stmt.where(ChatTurn.user_key == user_key)
        if since is not None:
            stmt = stmt.where(ChatTurn.created_at >= since)
        if until is not None:
            stmt = stmt.where(ChatTurn.created_at <= until)
        if session_id is not None:
            stmt = stmt.where(ChatTurn.session_id == session_id)

        rows = self._db.execute(stmt).all()
        return [
            {
                "session_id": r.session_id,
                "user_key": r.user_key,
                "mode": r.mode,
                "turn_count": r.turn_count,
                "first_at": r.first_at,
                "last_at": r.last_at,
                "tokens_in_sum": int(r.tokens_in_sum or 0),
                "tokens_out_sum": int(r.tokens_out_sum or 0),
                "tokens_cached_sum": int(r.tokens_cached_sum or 0),
                "avg_latency_ms": float(r.avg_latency_ms) if r.avg_latency_ms is not None else None,
            }
            for r in rows
        ]

    def count_sessions(
        self,
        mode: str | None = None,
        user_key: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        session_id: str | None = None,
    ) -> int:
        """Return total distinct sessions matching filters (for pagination + stats)."""
        inner = select(ChatTurn.session_id).group_by(ChatTurn.session_id)
        if mode is not None:
            inner = inner.where(ChatTurn.mode == mode)
        if user_key is not None:
            inner = inner.where(ChatTurn.user_key == user_key)
        if since is not None:
            inner = inner.where(ChatTurn.created_at >= since)
        if until is not None:
            inner = inner.where(ChatTurn.created_at <= until)
        if session_id is not None:
            inner = inner.where(ChatTurn.session_id == session_id)

        return int(self._db.execute(select(func.count()).select_from(inner.subquery())).scalar() or 0)

    def stats_summary(
        self,
        mode: str | None = None,
        user_key: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate stats across filter: sessions, turns, tokens, avg latency."""
        stmt = select(
            func.count(func.distinct(ChatTurn.session_id)).label("sessions"),
            func.count(ChatTurn.id).label("turns"),
            func.coalesce(func.sum(ChatTurn.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(ChatTurn.tokens_out), 0).label("tokens_out"),
            func.coalesce(func.sum(ChatTurn.tokens_cached), 0).label("tokens_cached"),
            func.avg(ChatTurn.latency_ms).label("avg_latency_ms"),
        )
        if mode is not None:
            stmt = stmt.where(ChatTurn.mode == mode)
        if user_key is not None:
            stmt = stmt.where(ChatTurn.user_key == user_key)
        if since is not None:
            stmt = stmt.where(ChatTurn.created_at >= since)
        if until is not None:
            stmt = stmt.where(ChatTurn.created_at <= until)
        if session_id is not None:
            stmt = stmt.where(ChatTurn.session_id == session_id)

        r = self._db.execute(stmt).one()
        return {
            "sessions": int(r.sessions or 0),
            "turns": int(r.turns or 0),
            "tokens_in": int(r.tokens_in or 0),
            "tokens_out": int(r.tokens_out or 0),
            "tokens_cached": int(r.tokens_cached or 0),
            "avg_latency_ms": float(r.avg_latency_ms) if r.avg_latency_ms is not None else None,
        }

    def list_turns(
        self,
        mode: str | None = None,
        user_key: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChatTurn]:
        """Return individual ChatTurn rows for the admin history browser.

        Supports the same filters as list_sessions but returns raw turns
        (not aggregated per-session summaries) with pagination.
        """
        stmt = (
            select(ChatTurn)
            .order_by(ChatTurn.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if mode is not None:
            stmt = stmt.where(ChatTurn.mode == mode)
        if user_key is not None:
            stmt = stmt.where(ChatTurn.user_key == user_key)
        if since is not None:
            stmt = stmt.where(ChatTurn.created_at >= since)
        if until is not None:
            stmt = stmt.where(ChatTurn.created_at <= until)
        if session_id is not None:
            stmt = stmt.where(ChatTurn.session_id == session_id)

        return list(self._db.execute(stmt).scalars().all())

    def purge_by_filters(
        self,
        mode: str | None = None,
        user_key: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        session_id: str | None = None,
    ) -> int:
        """Delete turns matching the given filters. Returns deleted row count."""
        stmt = delete(ChatTurn)

        conditions = []
        if mode is not None:
            conditions.append(ChatTurn.mode == mode)
        if user_key is not None:
            conditions.append(ChatTurn.user_key == user_key)
        if since is not None:
            conditions.append(ChatTurn.created_at >= since)
        if until is not None:
            conditions.append(ChatTurn.created_at <= until)
        if session_id is not None:
            conditions.append(ChatTurn.session_id == session_id)

        if conditions:
            from sqlalchemy import and_
            stmt = stmt.where(and_(*conditions))

        try:
            result = self._db.execute(stmt)
            self._db.commit()
            deleted = result.rowcount
            logger.info("Admin purge: removed %d chat_turn rows", deleted)
            return deleted
        except Exception:
            self._db.rollback()
            raise

    def purge_session(self, session_id: str) -> int:
        """Delete all turns for a single session. Returns deleted count."""
        stmt = delete(ChatTurn).where(ChatTurn.session_id == session_id)
        try:
            result = self._db.execute(stmt)
            self._db.commit()
            deleted = result.rowcount
            logger.info("Admin purge_session %s: removed %d rows", session_id, deleted)
            return deleted
        except Exception:
            self._db.rollback()
            raise

    def get_session_turns(self, session_id: str) -> list[ChatTurn]:
        """Return all turns for a session in ascending order (for export)."""
        stmt = (
            select(ChatTurn)
            .where(ChatTurn.session_id == session_id)
            .order_by(asc(ChatTurn.created_at))
        )
        return list(self._db.execute(stmt).scalars().all())

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #

    def export_csv(
        self,
        mode: str | None = None,
        user_key: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        session_id: str | None = None,
    ) -> bytes:
        """Return UTF-8 CSV bytes of matching ChatTurn rows.

        Columns: id, session_id, user_key, mode, role, content,
                 tokens_in, tokens_cached, tokens_out, latency_ms, created_at
        """
        stmt = select(ChatTurn).order_by(asc(ChatTurn.created_at))

        if mode is not None:
            stmt = stmt.where(ChatTurn.mode == mode)
        if user_key is not None:
            stmt = stmt.where(ChatTurn.user_key == user_key)
        if since is not None:
            stmt = stmt.where(ChatTurn.created_at >= since)
        if until is not None:
            stmt = stmt.where(ChatTurn.created_at <= until)
        if session_id is not None:
            stmt = stmt.where(ChatTurn.session_id == session_id)

        turns = self._db.execute(stmt).scalars().all()

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "id", "session_id", "user_key", "mode", "role", "content",
            "tokens_in", "tokens_cached", "tokens_out", "latency_ms", "created_at",
        ])
        for t in turns:
            writer.writerow([
                t.id, t.session_id, t.user_key, t.mode, t.role, t.content,
                t.tokens_in, t.tokens_cached, t.tokens_out, t.latency_ms,
                t.created_at.isoformat() if t.created_at else "",
            ])

        return buf.getvalue().encode("utf-8")

    # ------------------------------------------------------------------ #
    # Retention / purge
    # ------------------------------------------------------------------ #

    def purge_older_than(self, days: int) -> int:
        """Delete turns older than *days* days. Returns deleted row count."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = delete(ChatTurn).where(ChatTurn.created_at < cutoff)
        try:
            result = self._db.execute(stmt)
            self._db.commit()
            deleted = result.rowcount
            if deleted:
                logger.info("Purged %d chat_turn rows older than %d days", deleted, days)
            return deleted
        except Exception:
            self._db.rollback()
            raise
