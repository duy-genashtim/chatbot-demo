"""Shared streaming orchestrator for internal and external chat routes.

SSE event order:
  1. sources  — retrieved chunk metadata (before first token; improves perceived TTFB)
  2. delta    — one event per text token yielded by ChatSession.stream
  3. done     — session_id + total latency_ms

sync-to-async strategy:
  ChatSession.stream is an `async def` generator (yields via for-loop over a
  SYNC generate_content_stream iterator from google-genai 1.5.0).  The sync
  for-loop inside an async generator is fine as long as each `yield` releases
  control back to the event loop.  However the blocking `for chunk in
  response_iter` call inside ChatSession.stream holds the event loop for each
  chunk.  To avoid starvation on high concurrency we wrap the inner sync
  iterator consumption via `asyncio.to_thread` at the ChatSession level (phase
  03 design).  For phase 05 we simply `async for delta in session.stream()`
  which is already an async generator — no additional wrapping needed here.

  If the SDK ever exposes an async streaming API, ChatSession.stream can be
  updated in-place without changing this controller.

Error handling:
  Any exception during retrieval or streaming yields an `error` SSE event and
  closes the generator (no exception propagates to FastAPI so the HTTP response
  remains 200 with text/event-stream).
"""

from __future__ import annotations

import hashlib
import logging
from time import perf_counter
from typing import AsyncIterator, Literal

from app.api.sse import format_sse_event
from app.core.request_context import record

logger = logging.getLogger(__name__)

# Module-level references so tests can patch "app.services.chat_controller.get_retriever"
# and "app.services.chat_controller.get_session_store" cleanly.
# These are populated lazily on first call (app.main singletons set in lifespan).
def get_retriever():
    """Thin proxy to app.main.get_retriever — patchable in tests."""
    from app.main import get_retriever as _get
    return _get()


def get_session_store():
    """Thin proxy to app.main.get_session_store — patchable in tests."""
    from app.main import get_session_store as _get
    return _get()


async def stream_chat(
    mode: Literal["internal", "external"],
    session_id: str,
    session_key: str,
    user_key: str,
    message: str,
    show_sources: bool = True,
) -> AsyncIterator[str]:
    """Yield SSE-formatted strings for a single chat turn.

    Args:
        mode:         "internal" or "external" — controls domain + prompt.
        session_id:   Client-visible session identifier (returned in done event).
        session_key:  LRU store key (email for internal; "external:{id}" for external).
        user_key:     DB persistence key (email or hashed external id).
        message:      Raw user message text.
        show_sources: When False the sources event is suppressed (external anon config).

    Yields:
        SSE-formatted strings: sources? → delta* → done | error
    """
    t0 = perf_counter()

    try:
        from app.core.config import get_settings

        settings = get_settings()
        domain = "internal_hr" if mode == "internal" else "external_policy"

        # ── 1. Retrieve relevant chunks ───────────────────────────────────
        # Call module-level proxies (patchable in tests)
        retriever = get_retriever()
        t_ret_start = perf_counter()
        # k=None → retriever reads TOP_K_FINAL live from admin settings
        retrieved = await retriever.search(message, domain, k=None)
        retrieval_ms = int((perf_counter() - t_ret_start) * 1000)
        record("retrieval_ms", retrieval_ms)

        # ── 2. Emit sources event (before first token — B3 fix) ───────────
        if show_sources:
            sources_payload = [
                {"source": c.source, "section": c.section}
                for c in retrieved
            ]
            yield format_sse_event("sources", sources_payload)

        # ── 2b. Fail-closed: zero retrieval → hard fallback, no LLM call ──
        # Prevents hallucination from training knowledge or conversational
        # memory when the corpus has nothing relevant (or is empty).
        # We skip persistence so empty turns don't pollute rehydrated history.
        if not retrieved:
            fallback = (
                "I could not find this in current internal documents. "
                "Please contact hr@company.com or your People Manager."
                if mode == "internal"
                else "I don't have that in my current knowledge base. "
                "Please reach us at info@company.com or visit our website."
            )
            yield format_sse_event("delta", {"text": fallback})
            total_ms = int((perf_counter() - t0) * 1000)
            record("total_ms", total_ms)
            yield format_sse_event("done", {"session_id": session_id, "latency_ms": total_ms})
            return

        # ── 3. Get or create session ──────────────────────────────────────
        session_store = get_session_store()
        session = session_store.get_or_create(session_key, mode)

        # Convert RetrievedChunk list to dicts for ChatSession
        ctx_dicts = [
            {"text": c.text, "source": c.source, "section": c.section}
            for c in retrieved
        ]

        # ── 4. Stream LLM deltas ──────────────────────────────────────────
        first_token = True
        t_stream_start = perf_counter()

        async for delta in session.stream(message, ctx_dicts, user_key):
            if first_token:
                ttft_ms = int((perf_counter() - t_stream_start) * 1000)
                record("llm_ttft_ms", ttft_ms)
                first_token = False
            yield format_sse_event("delta", {"text": delta})

        llm_total_ms = int((perf_counter() - t_stream_start) * 1000)
        record("llm_total_ms", llm_total_ms)

    except Exception as exc:
        logger.error("stream_chat error [mode=%s session=%s]: %s", mode, session_id, exc)
        yield format_sse_event("error", {"message": "Đã xảy ra lỗi. Vui lòng thử lại."})
        return

    # ── 5. Done event ─────────────────────────────────────────────────────
    total_ms = int((perf_counter() - t0) * 1000)
    record("total_ms", total_ms)
    yield format_sse_event("done", {"session_id": session_id, "latency_ms": total_ms})


def hash_external_user_key(session_id: str, client_ip: str) -> str:
    """Derive a stable, non-reversible user_key for external sessions.

    SHA-256(session_id + ":" + client_ip), truncated to 16 hex chars.
    Prevents storing raw IP in the DB while still giving per-user isolation.

    Args:
        session_id: External session UUID.
        client_ip:  Real client IP (already resolved from X-Forwarded-For).

    Returns:
        "ext:" + 16-char hex digest.
    """
    raw = f"{session_id}:{client_ip}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"ext:{digest}"
