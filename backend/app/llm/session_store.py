"""In-memory session store — OrderedDict LRU with TTL eviction.

Design:
  - Access (get/set) promotes key to end (most-recently-used).
  - When capacity exceeded, evict the least-recently-used entry.
  - Stale entries (idle > SESSION_TTL_SEC) are evicted on access and
    by the periodic background task (evict_stale).
  - On cache miss, session history is rehydrated from DB (HISTORY_REHYDRATE_TURNS).
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict

from app.core.db import SessionLocal
from app.core.settings_service import SettingsService

logger = logging.getLogger(__name__)


class SessionStore:
    """Thread-safe-enough LRU store for ChatSession objects.

    Single-process, asyncio-only server — no explicit locking needed.
    """

    def __init__(self, max_sessions: int, ttl_sec: int) -> None:
        self._max = max_sessions
        self._ttl = ttl_sec
        self._store: OrderedDict = OrderedDict()  # key -> ChatSession

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_or_create(self, session_key: str, mode: str) -> "ChatSession":  # noqa: F821
        """Return existing live ChatSession or create a new one.

        On cold-start, rehydrates last N turns from DB into the new session's
        in-memory history so conversation context survives backend restarts.
        """
        from app.llm.chat_session import ChatSession  # local import avoids cycle

        # Fetch and validate TTL
        session = self._store.get(session_key)
        if session is not None:
            if self._is_stale(session):
                logger.debug("Session %s expired — evicting", session_key)
                del self._store[session_key]
                session = None
            else:
                # Promote to most-recently-used
                self._store.move_to_end(session_key)
                session.last_access = time.monotonic()
                return session

        # --- Cold start: build new session and rehydrate from DB ---
        session = ChatSession(session_key=session_key, mode=mode)
        self._rehydrate(session)
        self._put(session_key, session)
        return session

    def evict_stale(self) -> int:
        """Remove all sessions idle longer than TTL. Returns eviction count."""
        stale_keys = [k for k, s in self._store.items() if self._is_stale(s)]
        for k in stale_keys:
            del self._store[k]
        if stale_keys:
            logger.info("Evicted %d stale sessions", len(stale_keys))
        return len(stale_keys)

    def size(self) -> int:
        return len(self._store)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _is_stale(self, session) -> bool:
        return (time.monotonic() - session.last_access) > self._ttl

    def _put(self, key: str, session) -> None:
        """Insert or update session, evicting LRU when over capacity."""
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = session
        if len(self._store) > self._max:
            evicted_key, _ = self._store.popitem(last=False)
            logger.debug("LRU eviction: %s", evicted_key)

    def _rehydrate(self, session) -> None:
        """Load last N turns from DB into session.history as Content objects."""
        from app.services.chat_history_service import ChatHistoryService

        db = SessionLocal()
        try:
            svc = SettingsService(db)
            n = svc.get("HISTORY_REHYDRATE_TURNS", default=20, cast=int)
            if n <= 0:
                return
            history_svc = ChatHistoryService(db)
            turns = history_svc.rehydrate(session.session_key, n)
            if not turns:
                return

            from google.genai import types as gtypes

            for turn in turns:
                # Gemini history requires role="model" for assistant turns;
                # DB stores role="assistant" for cross-provider neutrality.
                gemini_role = "model" if turn.role == "assistant" else turn.role
                content = gtypes.Content(
                    role=gemini_role,
                    parts=[gtypes.Part(text=turn.content)],
                )
                session.history.append(content)
            logger.debug(
                "Rehydrated %d turns into session %s", len(turns), session.session_key
            )
        except Exception as exc:
            logger.warning("History rehydration failed for %s: %s", session.session_key, exc)
        finally:
            db.close()
