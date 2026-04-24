"""Hybrid retriever: parallel vector + BM25 → RRF merge → cross-encoder rerank.

Fixes V1 bottlenecks:
  B3 — retrieval no longer blocks SSE TTFB (caller awaits before streaming)
  B5 — query embedding cached via embed_query_cached()
  B6 — vector search and BM25 run in PARALLEL via asyncio.gather + to_thread
  B7 — candidate pool k*4 reduced to top_k_final=3 after rerank
  B8 — all blocking calls go through asyncio.to_thread (never blocks event loop)
"""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter

from app.rag.bm25_index import BM25Cache, get_bm25_cache
from app.rag.chroma_store import ChromaStore, get_chroma_store
from app.rag.embedding_provider import EmbeddingProvider, embed_query_cached, get_embedding_provider
from app.rag.reranker import CrossEncoderReranker, get_reranker
from app.rag.retrieved_chunk import RetrievedChunk
from app.core.request_context import record

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Orchestrates parallel vector + BM25 search, RRF fusion, and reranking.

    Designed to be created once (singleton) and called from async FastAPI handlers.
    All CPU/IO-bound operations are dispatched via asyncio.to_thread.
    """

    def __init__(
        self,
        store: ChromaStore,
        embedder: EmbeddingProvider,
        bm25: BM25Cache,
        reranker: CrossEncoderReranker,
        top_k_final: int = 3,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._bm25 = bm25
        self._reranker = reranker
        self._top_k_final = top_k_final

    async def search(
        self,
        query: str,
        domain: str,
        k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Full hybrid retrieval pipeline for a single query.

        Args:
            query:  User question text.
            domain: Collection name ('internal_hr' or 'external_policy').
            k:      Final number of chunks to return. If None, reads
                    TOP_K_FINAL live from admin settings (DB→env→default).

        Returns:
            Up to k RetrievedChunk objects, reranked by cross-encoder score.
        """
        # Both Top-K knobs are read from admin settings on every request so
        # that admin changes take effect without a restart. The constructor
        # default (self._top_k_final) is the last-resort fallback only.
        if k is None:
            k = self._read_setting_int("TOP_K_FINAL", self._top_k_final)
        candidate_k = self._read_setting_int("TOP_K_VECTOR", max(k * 4, 5))

        t0 = perf_counter()

        # ── B6: embed query and BM25 search run in PARALLEL ──────────────
        emb_task = asyncio.to_thread(embed_query_cached, self._embedder, query)
        bm25_task = asyncio.to_thread(self._bm25.search, domain, query, candidate_k)
        embedding, bm25_hits = await asyncio.gather(emb_task, bm25_task)

        t_parallel = perf_counter()
        # embed and bm25 ran in parallel — attribute elapsed to both stages
        _parallel_ms = int((t_parallel - t0) * 1000)
        record("embed_ms", _parallel_ms)
        record("bm25_ms", _parallel_ms)

        # ── Vector search (after embedding is ready) ──────────────────────
        vec_hits = await asyncio.to_thread(
            self._store.query, domain, embedding, candidate_k
        )

        t_vec = perf_counter()
        record("vector_ms", int((t_vec - t_parallel) * 1000))

        # ── RRF merge ─────────────────────────────────────────────────────
        merged = self._rrf(vec_hits, bm25_hits, rrf_k=60, take=k * 2)

        t_rrf = perf_counter()
        record("rrf_ms", int((t_rrf - t_vec) * 1000))

        # ── Cross-encoder rerank → top k ──────────────────────────────────
        reranked = await asyncio.to_thread(
            self._reranker.rerank, query, merged, k
        )

        t_end = perf_counter()
        record("rerank_ms", int((t_end - t_rrf) * 1000))
        record("retrieval_total_ms", int((t_end - t0) * 1000))

        logger.debug(
            "HybridRetriever.search domain=%s k=%d "
            "parallel(embed+bm25)=%.1fms vec=%.1fms rrf=%.1fms rerank=%.1fms total=%.1fms",
            domain, k,
            (t_parallel - t0) * 1000,
            (t_vec - t_parallel) * 1000,
            (t_rrf - t_vec) * 1000,
            (t_end - t_rrf) * 1000,
            (t_end - t0) * 1000,
        )

        return reranked

    # ------------------------------------------------------------------ #
    # Live admin-settings lookup
    # ------------------------------------------------------------------ #

    @staticmethod
    def _read_setting_int(key: str, fallback: int) -> int:
        """Read an integer admin setting from DB→env, with hard fallback.

        Opens a short-lived DB session per call. Failures (missing DB,
        invalid cast) silently return *fallback* so retrieval never breaks
        on a settings problem.
        """
        from app.core.db import SessionLocal
        from app.core.settings_service import SettingsService

        db = SessionLocal()
        try:
            return SettingsService(db).get(key, default=fallback, cast=int)
        except Exception:  # pragma: no cover — defensive
            return fallback
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Reciprocal Rank Fusion
    # ------------------------------------------------------------------ #

    @staticmethod
    def _rrf(
        vec_hits: list[RetrievedChunk],
        bm25_hits: list[RetrievedChunk],
        rrf_k: int = 60,
        take: int = 10,
    ) -> list[RetrievedChunk]:
        """Merge two ranked lists via Reciprocal Rank Fusion.

        RRF score = sum(1 / (rrf_k + rank)) across all lists.
        Deduplication key: first 80 chars of text (fast, avoids exact-dup noise).
        """
        scores: dict[str, float] = {}
        data: dict[str, RetrievedChunk] = {}

        for rank, chunk in enumerate(vec_hits):
            key = chunk.text[:80]
            scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank + 1)
            if key not in data:
                data[key] = chunk

        for rank, chunk in enumerate(bm25_hits):
            key = chunk.text[:80]
            scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank + 1)
            if key not in data:
                data[key] = chunk

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        result = []
        for key, rrf_score in ranked[:take]:
            chunk = data[key]
            result.append(
                RetrievedChunk(text=chunk.text, metadata=chunk.metadata, score=rrf_score)
            )
        return result


# ------------------------------------------------------------------ #
# Singleton factory
# ------------------------------------------------------------------ #

_retriever_singleton: HybridRetriever | None = None


def get_retriever() -> HybridRetriever:
    """Return process-level HybridRetriever singleton.

    Depends on get_chroma_store(), get_embedding_provider(), get_bm25_cache(),
    get_reranker() — all must be available (initialised at startup).
    """
    global _retriever_singleton
    if _retriever_singleton is None:
        from app.core.config import get_settings
        settings = get_settings()
        _retriever_singleton = HybridRetriever(
            store=get_chroma_store(),
            embedder=get_embedding_provider(),
            bm25=get_bm25_cache(),
            reranker=get_reranker(),
            top_k_final=settings.TOP_K_FINAL,
        )
        logger.info(
            "HybridRetriever initialised (top_k_final=%d)", settings.TOP_K_FINAL
        )
    return _retriever_singleton
