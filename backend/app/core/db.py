"""SQLAlchemy engine, session factory, declarative Base, and FastAPI dependency.

Uses DATABASE_URL from settings; defaults to SQLite at ./data/chatbotv2.db.
SQLite connect_args only applied when using sqlite:// scheme.
"""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


def _build_engine():
    settings = get_settings()
    url = settings.DATABASE_URL

    # Ensure local SQLite data directory exists
    if url.startswith("sqlite:///"):
        db_path = url.replace("sqlite:///", "")
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(url, connect_args=connect_args, echo=False)


engine = _build_engine()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy models."""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
