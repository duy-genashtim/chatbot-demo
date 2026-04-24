"""Embedding provider abstraction with Gemini and FastEmbed implementations.

Usage:
    provider = get_embedding_provider()
    vecs = provider.embed_documents(["text a", "text b"])
    qvec = embed_query_cached(provider, "search query")   # LRU-cached per (provider_id, query)

Query embedding is memoized in a module-level dict-based LRU to avoid the
instance-method cache-leak problem (lru_cache on bound methods leaks self).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import TYPE_CHECKING

from app.core.config import get_settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level LRU cache for query embeddings (avoids instance-method leak)
# ---------------------------------------------------------------------------

_QUERY_CACHE_MAX = 256
# Key: (provider_id, query_text) → list[float]
_query_cache: OrderedDict[tuple[str, str], list[float]] = OrderedDict()


def embed_query_cached(provider: "EmbeddingProvider", query: str) -> list[float]:
    """Return cached query embedding or compute and cache it.

    Fix for V1 B5: identical queries never re-embedded within the process lifetime.
    """
    key = (provider.provider_id, query)
    if key in _query_cache:
        _query_cache.move_to_end(key)  # LRU promotion
        return _query_cache[key]

    vec = provider.embed_query(query)
    _query_cache[key] = vec
    if len(_query_cache) > _QUERY_CACHE_MAX:
        _query_cache.popitem(last=False)  # evict LRU entry
    return vec


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class EmbeddingProvider(ABC):
    """Protocol-compatible abstract base for embedding providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique string identifying this provider instance (used as cache key)."""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of document texts. Batch-friendly."""

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Output vector dimension."""


# ---------------------------------------------------------------------------
# Gemini embedder
# ---------------------------------------------------------------------------

class GeminiEmbedder(EmbeddingProvider):
    """Embed via Gemini embedding API (gemini-embedding-001 default).

    Batches up to 100 documents per API call to stay within rate limits.
    Reuses the singleton genai.Client from app.llm.gemini_client.
    """

    _BATCH_SIZE = 100

    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        self._model = model or settings.EMBEDDING_MODEL
        self._dim: int | None = None  # discovered on first call

    @property
    def provider_id(self) -> str:
        return f"gemini:{self._model}"

    @property
    def dimension(self) -> int:
        if self._dim is None:
            raise RuntimeError("dimension unknown until first embed call")
        return self._dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents in batches of up to 100."""
        if not texts:
            return []
        from app.llm.gemini_client import get_client
        client = get_client()
        results: list[list[float]] = []

        for i in range(0, len(texts), self._BATCH_SIZE):
            batch = texts[i : i + self._BATCH_SIZE]
            resp = client.models.embed_content(
                model=self._model,
                contents=batch,
                config={"task_type": "RETRIEVAL_DOCUMENT"},
            )
            for emb in resp.embeddings:
                vec = list(emb.values)
                results.append(vec)
                if self._dim is None:
                    self._dim = len(vec)

        logger.debug("GeminiEmbedder: embedded %d docs via %s", len(texts), self._model)
        return results

    def embed_query(self, query: str) -> list[float]:
        from app.llm.gemini_client import get_client
        client = get_client()
        resp = client.models.embed_content(
            model=self._model,
            contents=[query],
            config={"task_type": "RETRIEVAL_QUERY"},
        )
        vec = list(resp.embeddings[0].values)
        if self._dim is None:
            self._dim = len(vec)
        return vec


# ---------------------------------------------------------------------------
# FastEmbed embedder (local CPU fallback)
# ---------------------------------------------------------------------------

class FastEmbedder(EmbeddingProvider):
    """Embed locally via fastembed (no API calls, zero cost).

    Uses a small English model by default. Slower than Gemini on CPU but
    requires no API key — useful for offline/dev environments.
    """

    _DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        self._model_name = model or settings.EMBEDDING_MODEL
        if self._model_name.startswith("gemini"):
            self._model_name = self._DEFAULT_MODEL
        self._model = None  # lazy init to avoid import cost at module load

    def _ensure_model(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self._model_name)
            logger.info("FastEmbedder loaded model: %s", self._model_name)

    @property
    def provider_id(self) -> str:
        return f"fastembed:{self._model_name}"

    @property
    def dimension(self) -> int:
        # bge-small-en-v1.5 → 384 dims
        return 384

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_model()
        embeddings = list(self._model.embed(texts))
        return [e.tolist() for e in embeddings]

    def embed_query(self, query: str) -> list[float]:
        self._ensure_model()
        embeddings = list(self._model.query_embed(query))
        return embeddings[0].tolist()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_provider_singleton: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """Return process-level embedding provider singleton.

    Provider type determined by EMBEDDING_PROVIDER env var ('gemini'|'fastembed').
    """
    global _provider_singleton
    if _provider_singleton is not None:
        return _provider_singleton

    settings = get_settings()
    if settings.EMBEDDING_PROVIDER == "fastembed":
        _provider_singleton = FastEmbedder()
        logger.info("EmbeddingProvider: FastEmbedder (%s)", settings.EMBEDDING_MODEL)
    else:
        _provider_singleton = GeminiEmbedder()
        logger.info("EmbeddingProvider: GeminiEmbedder (%s)", settings.EMBEDDING_MODEL)

    return _provider_singleton
