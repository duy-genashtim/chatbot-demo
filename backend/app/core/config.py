"""Pydantic BaseSettings for chatbotv2 — reads from .env, provides typed defaults.

All keys match deploy guide §4 exactly. Secrets default to empty string;
phase-02 fills them. Call get_settings() (lru_cache'd) everywhere in app.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration for chatbotv2 backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # ENVIRONMENT
    # ------------------------------------------------------------------ #
    ENVIRONMENT: Literal["dev", "prod"] = "dev"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_FORMAT: Literal["pretty", "json"] = "pretty"

    # ------------------------------------------------------------------ #
    # SERVER
    # ------------------------------------------------------------------ #
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000"

    # ------------------------------------------------------------------ #
    # DATABASE
    # ------------------------------------------------------------------ #
    DATABASE_URL: str = "sqlite:///./data/chatbotv2.db"

    # ------------------------------------------------------------------ #
    # MICROSOFT ENTRA ID (AUTH) — filled in phase-02
    # ------------------------------------------------------------------ #
    AZURE_TENANT_ID: str = ""
    AZURE_CLIENT_ID: str = ""
    AZURE_CLIENT_SECRET: str = ""
    AZURE_REDIRECT_URI: str = "http://localhost:8000/api/auth/callback/microsoft-entra-id"
    DEFAULT_ADMIN_EMAIL: str = "admin@company.com"

    # ------------------------------------------------------------------ #
    # GEMINI API
    # ------------------------------------------------------------------ #
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.1-flash-lite-preview"
    LLM_TEMPERATURE: float = Field(default=0.2, ge=0.0, le=2.0)
    LLM_MAX_OUTPUT_TOKENS: int = Field(default=800, ge=1)

    # ------------------------------------------------------------------ #
    # RAG / EMBEDDING
    # ------------------------------------------------------------------ #
    EMBEDDING_PROVIDER: Literal["gemini", "fastembed"] = "gemini"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    CHROMA_PATH: str = "/app/chroma_data"
    TOP_K_VECTOR: int = Field(default=5, ge=1)
    TOP_K_FINAL: int = Field(default=3, ge=1)

    # ------------------------------------------------------------------ #
    # SESSIONS & CACHE (stateful chat)
    # ------------------------------------------------------------------ #
    SESSION_TTL_SEC: int = Field(default=1800, ge=60)
    MAX_SESSIONS: int = Field(default=500, ge=1)
    CACHE_TTL_SEC: int = Field(default=1800, ge=60)

    # ------------------------------------------------------------------ #
    # CHAT HISTORY PERSISTENCE
    # ------------------------------------------------------------------ #
    HISTORY_RETENTION_DAYS: int = Field(default=90, ge=1)
    HISTORY_REHYDRATE_TURNS: int = Field(default=20, ge=0)

    # ------------------------------------------------------------------ #
    # RATE LIMITS
    # ------------------------------------------------------------------ #
    RATE_LIMIT_EXTERNAL_PER_MIN: int = Field(default=10, ge=1)
    RATE_LIMIT_INTERNAL_PER_MIN: int = Field(default=60, ge=1)
    ANONYMOUS_SHOW_SOURCES: bool = True

    # ------------------------------------------------------------------ #
    # UPLOADS (PDF only)
    # ------------------------------------------------------------------ #
    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_SIZE_MB: int = Field(default=20, ge=1)
    ALLOWED_UPLOAD_TYPES: str = "pdf"

    # ------------------------------------------------------------------ #
    # NEXTAUTH (shared with frontend)
    # ------------------------------------------------------------------ #
    NEXTAUTH_SECRET: str = ""
    NEXTAUTH_URL: str = "http://localhost:3000"

    # ------------------------------------------------------------------ #
    # DEV-ONLY: fake auth bypass for E2E / Playwright tests
    # HARD GUARD: main.py lifespan raises RuntimeError if set in prod.
    # ------------------------------------------------------------------ #
    FAKE_AUTH_EMAIL: str = ""

    # ------------------------------------------------------------------ #
    # Derived helpers (not from env)
    # ------------------------------------------------------------------ #
    @property
    def cors_origins_list(self) -> list[str]:
        """Split CORS_ALLOWED_ORIGINS into a list."""
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance (reads .env once at startup)."""
    return Settings()
