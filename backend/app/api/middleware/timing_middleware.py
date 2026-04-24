"""Per-request timing middleware.

Logs a structured timing record after every response.  All timing values
come from app.core.request_context (populated by HybridRetriever and
ChatSession during the request).

Log fields:
  req_id, method, path, status, mode, session_id
  embed_ms, vector_ms, bm25_ms, rrf_ms, rerank_ms
  retrieval_ms (alias: retrieval_total_ms)
  llm_ttft_ms, llm_total_ms, total_ms
  input_tokens, cached_tokens, output_tokens

Fields absent from context (e.g. non-chat endpoints) are omitted.
After logging, the summary dict is pushed to MetricsBuffer for
GET /api/admin/metrics.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.request_context import request_ctx

logger = logging.getLogger(__name__)

# Context keys forwarded verbatim into the log / metrics summary
_CTX_KEYS = (
    "mode",
    "session_id",
    "embed_ms",
    "vector_ms",
    "bm25_ms",
    "rrf_ms",
    "rerank_ms",
    "retrieval_ms",        # alias written by chat_controller (back-compat)
    "retrieval_total_ms",  # explicit total written by hybrid_retriever
    "llm_ttft_ms",
    "llm_total_ms",
    "input_tokens",
    "cached_tokens",
    "output_tokens",
)


class TimingMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that emits a timing log line after each request.

    Uses BaseHTTPMiddleware so it runs after the StreamingResponse has been
    fully consumed by the client (dispatch returns only after call_next and
    the response body is exhausted), giving ChatSession time to write token
    counts and LLM timings into request_ctx before we read them here.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = str(uuid.uuid4())[:8]

        # Fresh context dict for this request — reset on exit via token
        ctx: dict[str, Any] = {}
        token = request_ctx.set(ctx)

        t_start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            total_ms = int((time.perf_counter() - t_start) * 1000)
            request_ctx.reset(token)

        # Build summary — always-present fields first
        summary: dict[str, Any] = {
            "req_id": req_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "total_ms": total_ms,
        }
        # Merge optional context fields
        for key in _CTX_KEYS:
            if key in ctx:
                summary[key] = ctx[key]

        # Emit structured log line (human-readable; JSON formatter adds JSON wrapping)
        logger.info(
            "request %s",
            " ".join(f"{k}={v}" for k, v in summary.items()),
            extra=summary,
        )

        # Push to in-memory ring buffer for /api/admin/metrics
        try:
            from app.services.metrics_buffer import get_metrics_buffer
            get_metrics_buffer().push(summary)
        except Exception:
            pass  # never let metrics failure affect the response

        return response
