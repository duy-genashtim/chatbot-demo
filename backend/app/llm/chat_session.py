"""Per-session chat wrapper with manual history management and streaming.

Uses generate_content_stream + manual history (list[Content]) rather than
client.chats.create because chats.create does not compose with cached_content.

Stream flow per user turn:
  1. Persist user turn (role=user, tokens null) via ChatHistoryService
  2. Append user Content to in-memory history
  3. Build contents = history + current user message with RAG context block
  4. Call generate_content_stream with cached_content (or inline system_instruction)
  5. Yield text deltas as they arrive
  6. After stream ends: persist assistant turn with usage_metadata + latency
  7. Append assistant Content to in-memory history
"""

from __future__ import annotations

import logging
import time
from typing import AsyncIterator

from google.genai import types as gtypes

from app.core.db import SessionLocal
from app.core.request_context import record, record_tokens
from app.core.settings_service import SettingsService
from app.llm.gemini_client import get_client
from app.llm.system_prompt_builder import build_system_instruction

logger = logging.getLogger(__name__)


def _build_context_block(retrieved_ctx: list[dict]) -> str:
    """Format RAG results into a context block appended to the user message."""
    if not retrieved_ctx:
        return ""
    lines = ["\n\n--- Relevant context from knowledge base ---"]
    for i, chunk in enumerate(retrieved_ctx, 1):
        source = chunk.get("source", "unknown")
        text = chunk.get("text", "").strip()
        lines.append(f"[{i}] Source: {source}\n{text}")
    lines.append("--- End of context ---")
    return "\n".join(lines)


class ChatSession:
    """Holds per-session state: history, mode, optional cache reference."""

    def __init__(self, session_key: str, mode: str, cache_name: str | None = None) -> None:
        self.session_key = session_key
        self.mode = mode
        self.cache_name = cache_name  # Gemini resource name or None
        self.history: list[gtypes.Content] = []
        self.last_access: float = time.monotonic()

    # ------------------------------------------------------------------ #
    # Streaming entry point
    # ------------------------------------------------------------------ #

    async def stream(
        self,
        user_text: str,
        retrieved_ctx: list[dict],
        user_key: str,
    ) -> AsyncIterator[str]:
        """Yield assistant text deltas; persist both turns to DB."""
        self.last_access = time.monotonic()

        db = SessionLocal()
        try:
            svc = SettingsService(db)
            model = svc.get("GEMINI_MODEL", default="gemini-3.1-flash-lite-preview")
            temperature = svc.get("LLM_TEMPERATURE", default=0.2, cast=float)
            max_tokens = svc.get("LLM_MAX_OUTPUT_TOKENS", default=800, cast=int)
            # Admin-configurable text wrapped around every assistant reply.
            # Yielded to the client around the LLM stream but NOT persisted to
            # chat history or in-memory turns — keeps the LLM's view of the
            # conversation free of operator-injected boilerplate.
            mode_key = self.mode.upper()  # "INTERNAL" | "EXTERNAL"
            output_prefix = svc.get(f"{mode_key}_OUTPUT_PREFIX", default="", cast=str) or ""
            output_suffix = svc.get(f"{mode_key}_OUTPUT_SUFFIX", default="", cast=str) or ""
        finally:
            db.close()

        # 1. Persist user turn (tokens null)
        self._persist_turn(
            user_key=user_key,
            role="user",
            content=user_text,
        )

        # 2. Build user Content with RAG context appended
        context_block = _build_context_block(retrieved_ctx)
        full_user_text = user_text + context_block
        user_content = gtypes.Content(
            role="user",
            parts=[gtypes.Part(text=full_user_text)],
        )

        # 3. Compose contents = history + current user message
        contents = list(self.history) + [user_content]

        # 4. Build GenerateContentConfig
        if self.cache_name:
            # Cache holds system_instruction; do not duplicate it inline
            config = gtypes.GenerateContentConfig(
                cached_content=self.cache_name,
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
        else:
            config = gtypes.GenerateContentConfig(
                system_instruction=build_system_instruction(self.mode),
                temperature=temperature,
                max_output_tokens=max_tokens,
            )

        # 5. Stream response — instrument TTFT and total time
        t0 = time.perf_counter()
        accumulated_text = ""
        usage = None
        ttft_recorded = False

        # Yield admin-configured prefix BEFORE LLM stream starts, so the
        # client renders it first. Empty string yields nothing.
        if output_prefix:
            yield output_prefix + "\n\n"

        try:
            response_iter = get_client().models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )
            for chunk in response_iter:
                delta = ""
                if chunk.candidates:
                    candidate = chunk.candidates[0]
                    if candidate.content and candidate.content.parts:
                        delta = candidate.content.parts[0].text or ""
                if delta:
                    if not ttft_recorded:
                        record("llm_ttft_ms", int((time.perf_counter() - t0) * 1000))
                        ttft_recorded = True
                    accumulated_text += delta
                    yield delta
                # Capture usage_metadata from any chunk that has it
                if chunk.usage_metadata is not None:
                    usage = chunk.usage_metadata
        except Exception as exc:
            logger.error("generate_content_stream failed: %s", exc)
            error_msg = "An error occurred while generating a response. Please try again."
            yield error_msg
            accumulated_text = error_msg

        # Yield admin-configured suffix AFTER LLM stream completes.
        if output_suffix:
            yield "\n\n" + output_suffix

        latency_ms = int((time.perf_counter() - t0) * 1000)
        record("llm_total_ms", latency_ms)

        # 6. Persist assistant turn with tokens + latency
        tokens_in = tokens_cached = tokens_out = None
        if usage is not None:
            tokens_in = getattr(usage, "prompt_token_count", None)
            tokens_cached = getattr(usage, "cached_content_token_count", None)
            tokens_out = getattr(usage, "candidates_token_count", None)

        # Write token counts to request context for middleware to log
        record_tokens(in_=tokens_in, cached=tokens_cached, out=tokens_out)

        self._persist_turn(
            user_key=user_key,
            role="assistant",
            content=accumulated_text,
            tokens_in=tokens_in,
            tokens_cached=tokens_cached,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )

        # 7. Append both turns to in-memory history (use plain text for history)
        # Append original user text (without context block) for cleaner history
        self.history.append(
            gtypes.Content(role="user", parts=[gtypes.Part(text=user_text)])
        )
        self.history.append(
            gtypes.Content(role="model", parts=[gtypes.Part(text=accumulated_text)])
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _persist_turn(
        self,
        user_key: str,
        role: str,
        content: str,
        tokens_in: int | None = None,
        tokens_cached: int | None = None,
        tokens_out: int | None = None,
        latency_ms: int | None = None,
    ) -> None:
        """Fire-and-forget DB persist; logs but does not raise on failure."""
        from app.services.chat_history_service import ChatHistoryService

        db = SessionLocal()
        try:
            ChatHistoryService(db).persist_turn(
                session_id=self.session_key,
                user_key=user_key,
                mode=self.mode,
                role=role,
                content=content,
                tokens_in=tokens_in,
                tokens_cached=tokens_cached,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            logger.error("Failed to persist %s turn for %s: %s", role, self.session_key, exc)
        finally:
            db.close()
