"""Per-domain in-memory BM25 index with dirty-flag invalidation.

Fix for V1 bottlenecks:
  B4 — BM25 rebuilt on first request after restart: pre-warm at startup by
       calling get(domain) for both domains during lifespan.
  B4 — stale results after upload: mark_dirty(domain) in IngestionService
       forces rebuild on next search call.

Thread-safety: a threading.Lock per domain prevents concurrent rebuilds.
Rebuild fetches all docs from ChromaStore (blocking I/O wrapped in
asyncio.to_thread by HybridRetriever).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

from rank_bm25 import BM25Okapi

from app.rag.chroma_store import get_chroma_store  # module-level import so patch works
from app.rag.retrieved_chunk import RetrievedChunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal state per domain
# ---------------------------------------------------------------------------

@dataclass
class _DomainIndex:
    bm25: Optional[BM25Okapi] = None
    docs: list[RetrievedChunk] = field(default_factory=list)
    dirty: bool = True  # starts dirty → rebuilt on first access
    lock: threading.Lock = field(default_factory=threading.Lock)


# ---------------------------------------------------------------------------
# Public BM25 cache class
# ---------------------------------------------------------------------------

class BM25Cache:
    """Manages one BM25Okapi index per domain with lazy rebuild on dirty flag.

    Singleton created in main.py lifespan and pre-warmed for both domains.
    """

    def __init__(self) -> None:
        # domain → _DomainIndex
        self._indices: dict[str, _DomainIndex] = {}
        self._global_lock = threading.Lock()

    def _get_or_create_index(self, domain: str) -> _DomainIndex:
        with self._global_lock:
            if domain not in self._indices:
                self._indices[domain] = _DomainIndex()
            return self._indices[domain]

    def mark_dirty(self, domain: str) -> None:
        """Signal that domain corpus changed — next search triggers rebuild."""
        idx = self._get_or_create_index(domain)
        idx.dirty = True
        logger.debug("BM25Cache: marked '%s' dirty", domain)

    def get(self, domain: str) -> BM25Okapi | None:
        """Return the (possibly rebuilt) BM25 index for domain.

        Returns None if the domain collection is empty.
        Rebuilds synchronously when dirty — call from asyncio.to_thread.
        """
        idx = self._get_or_create_index(domain)
        with idx.lock:
            if idx.dirty or idx.bm25 is None:
                self._rebuild(domain, idx)
            return idx.bm25

    def search(self, domain: str, query: str, k: int) -> list[RetrievedChunk]:
        """BM25 keyword search. Returns up to k results (fewer if corpus empty).

        Designed to be called via asyncio.to_thread — fully synchronous.
        """
        idx = self._get_or_create_index(domain)
        with idx.lock:
            if idx.dirty or idx.bm25 is None:
                self._rebuild(domain, idx)

            if idx.bm25 is None or not idx.docs:
                return []

            tokens = query.lower().split()
            scores = idx.bm25.get_scores(tokens)
            top_indices = sorted(
                range(len(scores)), key=lambda i: scores[i], reverse=True
            )[:k]

            results = []
            for i in top_indices:
                if i < len(idx.docs) and scores[i] > -1e9:
                    # Include all non-trivially-absent results.
                    # BM25Okapi can return negative IDF scores on tiny corpora;
                    # we include them so callers always get candidates to rerank.
                    chunk = idx.docs[i]
                    results.append(
                        RetrievedChunk(
                            text=chunk.text,
                            metadata=chunk.metadata,
                            score=float(scores[i]),
                        )
                    )
            return results

    # ------------------------------------------------------------------ #
    # Internal rebuild
    # ------------------------------------------------------------------ #

    def _rebuild(self, domain: str, idx: _DomainIndex) -> None:
        """Fetch all docs from ChromaStore and rebuild BM25 index in-place.

        Must be called with idx.lock held.
        """
        logger.info("BM25Cache: rebuilding index for domain '%s'", domain)
        try:
            docs = get_chroma_store().get_all_documents(domain)
        except Exception as exc:
            logger.error("BM25Cache: failed to fetch docs for '%s': %s", domain, exc)
            idx.dirty = False  # stop infinite retry loop
            return

        if not docs:
            idx.bm25 = None
            idx.docs = []
            idx.dirty = False
            logger.debug("BM25Cache: '%s' is empty — no BM25 index built", domain)
            return

        tokenized = [doc.text.lower().split() for doc in docs]
        idx.bm25 = BM25Okapi(tokenized)
        idx.docs = docs
        idx.dirty = False
        logger.info(
            "BM25Cache: '%s' rebuilt with %d documents", domain, len(docs)
        )


# ------------------------------------------------------------------ #
# Singleton factory
# ------------------------------------------------------------------ #

_bm25_singleton: BM25Cache | None = None


def get_bm25_cache() -> BM25Cache:
    """Return process-level BM25Cache singleton."""
    global _bm25_singleton
    if _bm25_singleton is None:
        _bm25_singleton = BM25Cache()
    return _bm25_singleton
