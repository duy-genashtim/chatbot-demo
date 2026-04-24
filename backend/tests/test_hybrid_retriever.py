"""Tests for app.rag.hybrid_retriever.HybridRetriever.

Covers:
  - RRF merges two lists correctly (unit test on _rrf)
  - Parallel execution path (both gather branches exercised)
  - Reranker passthrough when model not loaded
  - Empty corpus returns empty results
  - Deduplication in RRF (same chunk from both sources counted once with higher score)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.hybrid_retriever import HybridRetriever
from app.rag.retrieved_chunk import RetrievedChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk(text: str, score: float = 0.5) -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        metadata={"doc_id": "d1", "source": "test.pdf", "domain": "internal_hr"},
        score=score,
    )


def _build_retriever(
    vec_results=None,
    bm25_results=None,
    reranker_passthrough=True,
) -> HybridRetriever:
    """Build a HybridRetriever with mocked dependencies."""
    mock_store = MagicMock()
    mock_store.query.return_value = vec_results or []

    mock_embedder = MagicMock()
    mock_embedder.provider_id = "mock:test"
    mock_embedder.embed_query.return_value = [0.1] * 8

    mock_bm25 = MagicMock()
    mock_bm25.search.return_value = bm25_results or []

    mock_reranker = MagicMock()
    if reranker_passthrough:
        # Passthrough: return chunks unchanged up to top
        mock_reranker.rerank.side_effect = lambda q, chunks, top: chunks[:top]
    else:
        mock_reranker.rerank.return_value = []

    return HybridRetriever(
        store=mock_store,
        embedder=mock_embedder,
        bm25=mock_bm25,
        reranker=mock_reranker,
        top_k_final=3,
    )


# ---------------------------------------------------------------------------
# RRF unit tests
# ---------------------------------------------------------------------------

class TestRRF:
    def test_empty_lists_return_empty(self):
        result = HybridRetriever._rrf([], [], rrf_k=60, take=5)
        assert result == []

    def test_single_list_ranked_in_order(self):
        chunks = [_chunk(f"chunk {i}") for i in range(5)]
        result = HybridRetriever._rrf(chunks, [], rrf_k=60, take=3)
        assert len(result) == 3
        # First chunk should have highest RRF score (rank 0)
        assert result[0].text == "chunk 0"

    def test_deduplication_boosts_shared_chunk(self):
        """Chunk appearing in both lists gets boosted RRF score."""
        shared = _chunk("shared important text")
        vec_only = _chunk("vector only result")
        bm25_only = _chunk("bm25 only result")

        vec_list = [shared, vec_only]
        bm25_list = [shared, bm25_only]

        result = HybridRetriever._rrf(vec_list, bm25_list, rrf_k=60, take=3)
        # shared appears in both → highest combined score
        assert result[0].text == "shared important text"

    def test_take_limits_output(self):
        chunks_a = [_chunk(f"a{i}") for i in range(10)]
        chunks_b = [_chunk(f"b{i}") for i in range(10)]
        result = HybridRetriever._rrf(chunks_a, chunks_b, rrf_k=60, take=5)
        assert len(result) == 5

    def test_rrf_score_decreases_with_rank(self):
        chunks = [_chunk(f"chunk {i}") for i in range(4)]
        result = HybridRetriever._rrf(chunks, [], rrf_k=60, take=4)
        scores = [r.score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_rrf_output_type_is_retrieved_chunk(self):
        chunks = [_chunk("text")]
        result = HybridRetriever._rrf(chunks, [], rrf_k=60, take=1)
        assert all(isinstance(r, RetrievedChunk) for r in result)


# ---------------------------------------------------------------------------
# Async search pipeline
# ---------------------------------------------------------------------------

class TestHybridRetrieverSearch:
    def test_empty_corpus_returns_empty(self):
        retriever = _build_retriever(vec_results=[], bm25_results=[])
        result = asyncio.get_event_loop().run_until_complete(
            retriever.search("test query", "internal_hr")
        )
        assert result == []

    def test_search_returns_up_to_k_results(self):
        vec = [_chunk(f"vec chunk {i}") for i in range(6)]
        bm25 = [_chunk(f"bm25 chunk {i}") for i in range(6)]
        retriever = _build_retriever(vec_results=vec, bm25_results=bm25)
        result = asyncio.get_event_loop().run_until_complete(
            retriever.search("query", "internal_hr", k=3)
        )
        assert len(result) <= 3

    def test_search_calls_embedder(self):
        retriever = _build_retriever()
        asyncio.get_event_loop().run_until_complete(
            retriever.search("some question", "internal_hr")
        )
        retriever._embedder.embed_query.assert_called_once_with("some question")

    def test_search_calls_bm25_with_candidate_k(self):
        retriever = _build_retriever()
        k = 3
        asyncio.get_event_loop().run_until_complete(
            retriever.search("query", "external_policy", k=k)
        )
        # candidate_k is read live from admin settings (TOP_K_VECTOR),
        # with max(k * 4, 5) as the constructor fallback. In the test
        # environment SettingsService resolves TOP_K_VECTOR from config,
        # so read the same value to compute the expected argument.
        from app.core.config import get_settings
        expected = get_settings().TOP_K_VECTOR
        call_args = retriever._bm25.search.call_args
        assert call_args[0][2] == expected  # positional arg: k param

    def test_search_calls_reranker(self):
        vec = [_chunk("relevant text")]
        retriever = _build_retriever(vec_results=vec)
        asyncio.get_event_loop().run_until_complete(
            retriever.search("query", "internal_hr", k=3)
        )
        retriever._reranker.rerank.assert_called_once()

    def test_parallel_execution_both_sources_called(self):
        """Both vec query and bm25 search must be invoked on each search call."""
        vec = [_chunk("vec result")]
        bm25 = [_chunk("bm25 result")]
        retriever = _build_retriever(vec_results=vec, bm25_results=bm25)
        asyncio.get_event_loop().run_until_complete(
            retriever.search("parallel query", "internal_hr")
        )
        retriever._store.query.assert_called_once()
        retriever._bm25.search.assert_called_once()

    def test_custom_k_overrides_default(self):
        vec = [_chunk(f"chunk {i}") for i in range(10)]
        retriever = _build_retriever(vec_results=vec)
        result = asyncio.get_event_loop().run_until_complete(
            retriever.search("query", "internal_hr", k=2)
        )
        assert len(result) <= 2
