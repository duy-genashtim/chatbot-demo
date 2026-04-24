"""Unit tests for ChatHistoryService using an in-memory SQLite database.

Covers:
  - persist_turn + rehydrate round-trip
  - rehydrate ordering (ascending) and limit (last N)
  - list_sessions filtering by mode, user_key, since, until
  - purge_older_than cutoff (deletes old, keeps recent)
  - export_csv column headers and row content
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.chat_turn import ChatTurn
from app.services.chat_history_service import ChatHistoryService


# ------------------------------------------------------------------ #
# Test DB fixture — in-memory SQLite, isolated per test
# ------------------------------------------------------------------ #

@pytest.fixture()
def db():
    """Provide a fresh in-memory SQLite session for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def svc(db):
    return ChatHistoryService(db)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _ts(days_ago: int = 0, seconds_ago: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago, seconds=seconds_ago)


def _insert_turn(svc, session_id="s1", user_key="alice", mode="internal",
                 role="user", content="hello", days_ago=0, **kwargs) -> ChatTurn:
    turn = svc.persist_turn(
        session_id=session_id,
        user_key=user_key,
        mode=mode,
        role=role,
        content=content,
        **kwargs,
    )
    # Manually backdate created_at if needed (after commit)
    if days_ago:
        turn.created_at = _ts(days_ago=days_ago)
        svc._db.commit()
    return turn


# ------------------------------------------------------------------ #
# persist_turn + rehydrate round-trip
# ------------------------------------------------------------------ #

class TestPersistAndRehydrate:
    def test_single_turn_round_trip(self, svc):
        _insert_turn(svc, content="What is the leave policy?")
        turns = svc.rehydrate("s1", n=10)
        assert len(turns) == 1
        assert turns[0].content == "What is the leave policy?"
        assert turns[0].role == "user"

    def test_assistant_turn_with_tokens(self, svc):
        _insert_turn(svc, role="assistant", content="You get 20 days.",
                     tokens_in=100, tokens_cached=50, tokens_out=30, latency_ms=250)
        turns = svc.rehydrate("s1", n=10)
        t = turns[0]
        assert t.tokens_in == 100
        assert t.tokens_cached == 50
        assert t.tokens_out == 30
        assert t.latency_ms == 250

    def test_user_turn_has_null_tokens(self, svc):
        _insert_turn(svc, role="user", content="Hi")
        turns = svc.rehydrate("s1", n=10)
        t = turns[0]
        assert t.tokens_in is None
        assert t.tokens_out is None
        assert t.latency_ms is None

    def test_rehydrate_returns_ascending_order(self, svc):
        for i in range(5):
            _insert_turn(svc, content=f"msg {i}")
        turns = svc.rehydrate("s1", n=10)
        contents = [t.content for t in turns]
        assert contents == [f"msg {i}" for i in range(5)]

    def test_rehydrate_limit_returns_last_n(self, svc):
        for i in range(10):
            _insert_turn(svc, content=f"msg {i}")
        turns = svc.rehydrate("s1", n=3)
        assert len(turns) == 3
        # Last 3 in ascending order: msg 7, msg 8, msg 9
        assert turns[0].content == "msg 7"
        assert turns[-1].content == "msg 9"

    def test_rehydrate_zero_returns_empty(self, svc):
        _insert_turn(svc, content="irrelevant")
        assert svc.rehydrate("s1", n=0) == []

    def test_rehydrate_unknown_session_returns_empty(self, svc):
        assert svc.rehydrate("no_such_session", n=10) == []

    def test_rehydrate_isolates_by_session_id(self, svc):
        _insert_turn(svc, session_id="s1", content="session 1 msg")
        _insert_turn(svc, session_id="s2", content="session 2 msg")
        turns = svc.rehydrate("s1", n=10)
        assert len(turns) == 1
        assert turns[0].content == "session 1 msg"


# ------------------------------------------------------------------ #
# list_sessions
# ------------------------------------------------------------------ #

class TestListSessions:
    def test_list_all_sessions(self, svc):
        _insert_turn(svc, session_id="s1", mode="internal", user_key="alice")
        _insert_turn(svc, session_id="s2", mode="external", user_key="bob")
        rows = svc.list_sessions()
        assert len(rows) == 2

    def test_filter_by_mode(self, svc):
        _insert_turn(svc, session_id="s1", mode="internal", user_key="alice")
        _insert_turn(svc, session_id="s2", mode="external", user_key="bob")
        rows = svc.list_sessions(mode="internal")
        assert len(rows) == 1
        assert rows[0]["mode"] == "internal"

    def test_filter_by_user_key(self, svc):
        _insert_turn(svc, session_id="s1", user_key="alice")
        _insert_turn(svc, session_id="s2", user_key="carol")
        rows = svc.list_sessions(user_key="alice")
        assert len(rows) == 1
        assert rows[0]["user_key"] == "alice"

    def test_filter_since(self, svc):
        _insert_turn(svc, session_id="old", content="old", days_ago=10)
        _insert_turn(svc, session_id="new", content="new", days_ago=0)
        cutoff = _ts(days_ago=5)
        rows = svc.list_sessions(since=cutoff)
        session_ids = [r["session_id"] for r in rows]
        assert "new" in session_ids
        assert "old" not in session_ids

    def test_filter_until(self, svc):
        _insert_turn(svc, session_id="old", content="old", days_ago=10)
        _insert_turn(svc, session_id="new", content="new", days_ago=0)
        cutoff = _ts(days_ago=5)
        rows = svc.list_sessions(until=cutoff)
        session_ids = [r["session_id"] for r in rows]
        assert "old" in session_ids
        assert "new" not in session_ids

    def test_turn_count_correct(self, svc):
        for _ in range(4):
            _insert_turn(svc, session_id="multi")
        rows = svc.list_sessions()
        assert rows[0]["turn_count"] == 4

    def test_limit_and_offset(self, svc):
        for i in range(5):
            _insert_turn(svc, session_id=f"s{i}")
        rows_page1 = svc.list_sessions(limit=3, offset=0)
        rows_page2 = svc.list_sessions(limit=3, offset=3)
        assert len(rows_page1) == 3
        assert len(rows_page2) == 2


# ------------------------------------------------------------------ #
# purge_older_than
# ------------------------------------------------------------------ #

class TestPurgeOlderThan:
    def test_purge_removes_old_rows(self, svc):
        _insert_turn(svc, session_id="old", days_ago=100)
        _insert_turn(svc, session_id="recent", days_ago=1)
        deleted = svc.purge_older_than(days=30)
        assert deleted == 1
        remaining = svc.rehydrate("old", n=10)
        assert len(remaining) == 0

    def test_purge_keeps_recent_rows(self, svc):
        _insert_turn(svc, session_id="recent", days_ago=1)
        deleted = svc.purge_older_than(days=30)
        assert deleted == 0
        assert len(svc.rehydrate("recent", n=10)) == 1

    def test_purge_exact_boundary(self, svc):
        # Row at exactly 30 days ago should be deleted (< cutoff becomes >=)
        _insert_turn(svc, session_id="boundary", days_ago=31)
        deleted = svc.purge_older_than(days=30)
        assert deleted == 1

    def test_purge_returns_correct_count(self, svc):
        for i in range(5):
            _insert_turn(svc, session_id=f"old{i}", days_ago=100)
        for i in range(3):
            _insert_turn(svc, session_id=f"new{i}", days_ago=1)
        deleted = svc.purge_older_than(days=30)
        assert deleted == 5


# ------------------------------------------------------------------ #
# export_csv
# ------------------------------------------------------------------ #

class TestExportCsv:
    def test_csv_has_header_row(self, svc):
        csv_bytes = svc.export_csv()
        lines = csv_bytes.decode("utf-8").splitlines()
        assert lines[0].startswith("id,session_id,user_key")

    def test_csv_contains_expected_columns(self, svc):
        csv_bytes = svc.export_csv()
        header = csv_bytes.decode("utf-8").splitlines()[0]
        for col in ["id", "session_id", "user_key", "mode", "role", "content",
                    "tokens_in", "tokens_cached", "tokens_out", "latency_ms", "created_at"]:
            assert col in header

    def test_csv_row_count_matches_turns(self, svc):
        for i in range(3):
            _insert_turn(svc, session_id="s1", content=f"turn {i}")
        csv_bytes = svc.export_csv()
        lines = [l for l in csv_bytes.decode("utf-8").splitlines() if l]
        assert len(lines) == 4  # 1 header + 3 data rows

    def test_csv_filter_by_mode(self, svc):
        _insert_turn(svc, session_id="s1", mode="internal", content="internal msg")
        _insert_turn(svc, session_id="s2", mode="external", content="external msg")
        csv_bytes = svc.export_csv(mode="internal")
        text = csv_bytes.decode("utf-8")
        assert "internal msg" in text
        assert "external msg" not in text

    def test_csv_is_valid_utf8(self, svc):
        _insert_turn(svc, content="Unicode: café résumé")
        csv_bytes = svc.export_csv()
        text = csv_bytes.decode("utf-8")
        assert "café" in text
