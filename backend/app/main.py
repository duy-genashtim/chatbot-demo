"""FastAPI application factory for chatbotv2.

- CORS origins read from CORS_ALLOWED_ORIGINS env var (comma-separated)
- /healthz liveness probe
- Startup: creates all DB tables, seeds default admin (idempotent)
- Startup: initialises GeminiClient singleton, SessionStore, CacheManager
- Background tasks: session eviction (10 min), history purge (24 h)
- Auth router mounted under /api/auth
- Internal chat router under /api/internal (auth required)
- External chat router under /api/external (anonymous)
- Admin router under /api/admin (admin required)
- Timing middleware logs per-request stage durations
- SlowAPI rate-limit middleware for external + internal endpoints
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.core.logging_config import configure_logging

# Import models so their metadata is registered before create_all
import app.models  # noqa: F401

from app.api.routes.auth_routes import router as auth_router
from app.api.routes.internal_chat_routes import router as internal_router
from app.api.routes.external_chat_routes import router as external_router
from app.api.routes.admin_routes import router as admin_router

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Process-level singletons (populated in lifespan)
# ------------------------------------------------------------------ #
from app.llm.session_store import SessionStore
from app.llm.cache_manager import CacheManager
from app.rag.hybrid_retriever import HybridRetriever

_session_store: SessionStore | None = None
_cache_manager: CacheManager | None = None
_retriever: HybridRetriever | None = None


def get_session_store() -> SessionStore:
    """Return the process-level SessionStore. Raises if not initialised."""
    if _session_store is None:
        raise RuntimeError("SessionStore not initialised — call inside lifespan")
    return _session_store


def get_cache_manager() -> CacheManager:
    """Return the process-level CacheManager. Raises if not initialised."""
    if _cache_manager is None:
        raise RuntimeError("CacheManager not initialised — call inside lifespan")
    return _cache_manager


def get_retriever() -> HybridRetriever:
    """Return the process-level HybridRetriever. Raises if not initialised."""
    if _retriever is None:
        raise RuntimeError("HybridRetriever not initialised — call inside lifespan")
    return _retriever


# ------------------------------------------------------------------ #
# Background task coroutines
# ------------------------------------------------------------------ #

async def _eviction_loop() -> None:
    """Evict stale sessions every 10 minutes."""
    while True:
        await asyncio.sleep(600)  # 10 min
        try:
            if _session_store is not None:
                evicted = _session_store.evict_stale()
                if evicted:
                    logger.debug("Background eviction: removed %d stale sessions", evicted)
        except Exception as exc:
            logger.error("Session eviction error: %s", exc)


async def _purge_loop() -> None:
    """Purge chat_turn rows older than HISTORY_RETENTION_DAYS every 24 hours."""
    while True:
        await asyncio.sleep(86400)  # 24 h
        try:
            from app.services.chat_history_service import ChatHistoryService

            settings = get_settings()
            db = SessionLocal()
            try:
                deleted = ChatHistoryService(db).purge_older_than(
                    settings.HISTORY_RETENTION_DAYS
                )
                logger.info("Daily purge: removed %d chat_turn rows", deleted)
            finally:
                db.close()
        except Exception as exc:
            logger.error("History purge error: %s", exc)


def _purge_retired_settings_keys(keys: tuple[str, ...]) -> None:
    """Delete app_setting rows whose keys are no longer in SETTINGS_SCHEMA.

    Keeps the admin UI consistent with the DB after a key is retired.
    Failures are logged and swallowed — startup must never block on cleanup.
    """
    from app.models.app_setting import AppSetting

    db = SessionLocal()
    try:
        deleted = (
            db.query(AppSetting)
            .filter(AppSetting.key.in_(keys))
            .delete(synchronize_session=False)
        )
        if deleted:
            db.commit()
            logger.info("Purged %d retired app_setting row(s): %s", deleted, list(keys))
    except Exception as exc:
        logger.warning("Retired-keys cleanup skipped: %s", exc)
    finally:
        db.close()


# ------------------------------------------------------------------ #
# Lifespan
# ------------------------------------------------------------------ #

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: DB init, admin seed, LLM init, RAG init, background tasks. Shutdown: cleanup."""
    global _session_store, _cache_manager, _retriever

    settings = get_settings()

    # 0. Configure structured logging FIRST — before any other log output
    configure_logging(level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)

    # Safety guard: FAKE_AUTH_EMAIL must never be set in production
    if settings.ENVIRONMENT == "prod" and settings.FAKE_AUTH_EMAIL:
        raise RuntimeError(
            "FAKE_AUTH_EMAIL is set but ENVIRONMENT=prod — "
            "refusing to start. Remove FAKE_AUTH_EMAIL from prod config."
        )

    # 1. Create all tables (idempotent — skips existing)
    Base.metadata.create_all(bind=engine)

    # 2. Seed default admin
    from app.services.admin_service import AdminService
    db = SessionLocal()
    try:
        AdminService(db).seed_default_admin()
    finally:
        db.close()

    # 2b. Drop legacy app_setting rows for keys that have been retired from
    # the admin schema (idempotent; only runs at startup; safe to remove
    # this block once all envs are confirmed clean).
    _purge_retired_settings_keys((
        "INTERNAL_SYSTEM_PROMPT",
        "EXTERNAL_SYSTEM_PROMPT",
    ))

    # 3. Initialise Gemini client singleton
    from app.llm.gemini_client import init_client
    init_client()

    # 4. Initialise SessionStore + CacheManager
    _session_store = SessionStore(
        max_sessions=settings.MAX_SESSIONS,
        ttl_sec=settings.SESSION_TTL_SEC,
    )
    _cache_manager = CacheManager()
    logger.info(
        "SessionStore ready (max=%d ttl=%ds)", settings.MAX_SESSIONS, settings.SESSION_TTL_SEC
    )

    # 5. Initialise RAG pipeline (ChromaStore, BM25, Reranker, HybridRetriever)
    _retriever = await _init_rag()

    # 6. Pre-warm Gemini context caches for both modes
    _prewarm_caches()

    # 7. Launch background tasks
    eviction_task = asyncio.create_task(_eviction_loop(), name="session-eviction")
    purge_task = asyncio.create_task(_purge_loop(), name="history-purge")
    logger.info("Background tasks started: session-eviction, history-purge")

    yield  # ---- app running ----

    # Shutdown: cancel background tasks gracefully
    eviction_task.cancel()
    purge_task.cancel()
    try:
        await asyncio.gather(eviction_task, purge_task, return_exceptions=True)
    except Exception:
        pass
    logger.info("Background tasks stopped")


async def _init_rag() -> "HybridRetriever":
    """Initialise RAG components: ChromaStore, reranker, BM25 pre-warm.

    Pre-warms BM25 for both domains (fixes V1 B4 — first-request rebuild lag).
    Reranker loaded once (model download happens here at startup).
    """
    from app.rag.chroma_store import get_chroma_store
    from app.rag.bm25_index import get_bm25_cache
    from app.rag.reranker import get_reranker
    from app.rag.hybrid_retriever import get_retriever as _build_retriever
    from app.rag.chroma_store import VALID_DOMAINS

    # Open ChromaDB persistent client
    get_chroma_store()
    logger.info("ChromaStore initialised")

    # Load cross-encoder reranker (downloads ~80MB model on first run)
    reranker = get_reranker()
    await asyncio.to_thread(reranker.initialize)

    # Pre-warm BM25 for all domains (safe when collections are empty)
    bm25 = get_bm25_cache()
    for domain in VALID_DOMAINS:
        try:
            await asyncio.to_thread(bm25.get, domain)
            logger.info("BM25 pre-warm complete for domain '%s'", domain)
        except Exception as exc:
            logger.warning("BM25 pre-warm skipped for '%s': %s", domain, exc)

    retriever = _build_retriever()
    logger.info("HybridRetriever ready")
    return retriever


def _prewarm_caches() -> None:
    """Attempt to pre-warm Gemini context caches for both modes.

    Skips silently when no documents have been ingested yet.
    """
    logger.info(
        "Gemini cache pre-warm: skipped at startup (no docs ingested yet). "
        "Cache will be created on first ingestion."
    )


# ------------------------------------------------------------------ #
# App factory
# ------------------------------------------------------------------ #

def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    from app.api.middleware.timing_middleware import TimingMiddleware
    from app.auth.dependencies import require_admin
    from app.services.rate_limiter import external_limiter, internal_limiter

    settings = get_settings()

    application = FastAPI(
        title="G-HelpDesk",
        description="Dual-domain RAG chatbot — internal HR + external policy",
        version="2.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------ #
    # SlowAPI — attach limiters to app state and register middleware
    # ------------------------------------------------------------------ #
    # SlowAPIMiddleware looks for app.state.limiter; we register both
    # limiters by patching the default one (external) onto app state and
    # letting each router's @limiter.limit decorator reference its own.
    application.state.limiter = external_limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    application.add_middleware(SlowAPIMiddleware)

    # ------------------------------------------------------------------ #
    # Timing middleware (logs per-request stage durations)
    # ------------------------------------------------------------------ #
    application.add_middleware(TimingMiddleware)

    # ------------------------------------------------------------------ #
    # CORS — must be added after other middleware so it runs outermost
    # ------------------------------------------------------------------ #
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------ #
    # Routes
    # ------------------------------------------------------------------ #
    @application.get("/healthz", tags=["ops"])
    async def healthz():
        """Liveness probe — returns 200 when app is running."""
        return {"status": "ok"}

    application.include_router(auth_router)

    # Internal chat — route-level auth via Depends(get_current_user_with_state)
    application.include_router(internal_router, prefix="/api/internal")

    # External chat — anonymous; rate-limited by IP via external_limiter
    application.include_router(external_router, prefix="/api/external")

    # Admin — router-level require_admin guard applied to all sub-routes
    application.include_router(
        admin_router,
        prefix="/api/admin",
        dependencies=[Depends(require_admin)],
    )

    return application


app = create_app()
