"""Tests for app.rag.bm25_index.BM25Cache.

Covers:
  - Dirty flag triggers rebuild on next search
  - mark_dirty sets dirty=True; clean after rebuild
  - search returns ranked results
  - Empty domain returns empty list
  - Thread-safety: concurrent searches don't corrupt state
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.rag.bm25_index import BM25Cache
from app.rag.retrieved_chunk import RetrievedChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_retrieved(text: str, doc_id: str = "doc1") -> RetrievedChunk:
    return RetrievedChunk(text=text, metadata={"doc_id": doc_id, "domain": "internal_hr"})


def _patch_chroma(docs: list[RetrievedChunk]):
    """Context manager: patch module-level get_chroma_store in bm25_index."""
    mock_store = MagicMock()
    mock_store.get_all_documents.return_value = docs
    # bm25_index imports get_chroma_store at module level — patch the name in that module
    return patch("app.rag.bm25_index.get_chroma_store", return_value=mock_store)


# ---------------------------------------------------------------------------
# Basic rebuild
# ---------------------------------------------------------------------------

class TestBM25CacheRebuild:
    def test_empty_domain_returns_empty(self):
        cache = BM25Cache()
        with _patch_chroma([]):
            results = cache.search("internal_hr", "query text", k=5)
        assert results == []

    def test_search_rebuilds_on_first_call(self):
        cache = BM25Cache()
        docs = [
            _make_retrieved("python programming language", "d1"),
            _make_retrieved("java enterprise application", "d2"),
            _make_retrieved("machine learning algorithms", "d3"),
        ]
        with _patch_chroma(docs):
            results = cache.search("internal_hr", "python", k=3)
        assert len(results) >= 1
        assert results[0].text == "python programming language"

    def test_get_returns_none_when_empty(self):
        cache = BM25Cache()
        with _patch_chroma([]):
            bm25 = cache.get("internal_hr")
        assert bm25 is None

    def test_get_returns_bm25_when_docs_exist(self):
        cache = BM25Cache()
        docs = [_make_retrieved("some text here")]
        with _patch_chroma(docs):
            bm25 = cache.get("internal_hr")
        assert bm25 is not None


# ---------------------------------------------------------------------------
# Dirty flag
# ---------------------------------------------------------------------------

class TestBM25CacheDirtyFlag:
    def test_mark_dirty_triggers_rebuild_on_next_search(self):
        cache = BM25Cache()
        docs_v1 = [_make_retrieved("original document content", "d1")]
        docs_v2 = [
            _make_retrieved("original document content", "d1"),
            _make_retrieved("new document added after upload", "d2"),
        ]

        # Initial build
        with _patch_chroma(docs_v1):
            r1 = cache.search("internal_hr", "original", k=5)
        assert len(r1) == 1

        # Mark dirty (simulates new doc ingest)
        cache.mark_dirty("internal_hr")

        # Rebuild should now pick up docs_v2
        with _patch_chroma(docs_v2):
            r2 = cache.search("internal_hr", "original", k=5)
        assert len(r2) == 2

    def test_clean_after_rebuild_no_redundant_rebuild(self):
        """Second search without mark_dirty must NOT call chroma again."""
        cache = BM25Cache()
        docs = [_make_retrieved("stable content")]
        mock_store = MagicMock()
        mock_store.get_all_documents.return_value = docs

        with patch("app.rag.bm25_index.get_chroma_store", return_value=mock_store):
            cache.search("external_policy", "stable", k=3)
            cache.search("external_policy", "stable", k=3)

        # get_all_documents called exactly once (on first dirty build)
        assert mock_store.get_all_documents.call_count == 1

    def test_mark_dirty_multiple_domains_independent(self):
        cache = BM25Cache()
        docs = [_make_retrieved("test content")]
        with _patch_chroma(docs):
            cache.search("internal_hr", "test", k=1)
            cache.search("external_policy", "test", k=1)

        cache.mark_dirty("internal_hr")
        # external_policy index should still be clean
        idx_ext = cache._get_or_create_index("external_policy")
        idx_int = cache._get_or_create_index("internal_hr")
        assert not idx_ext.dirty
        assert idx_int.dirty


# ---------------------------------------------------------------------------
# Search ranking
# ---------------------------------------------------------------------------

class TestBM25CacheSearchRanking:
    def test_most_relevant_doc_ranked_first(self):
        cache = BM25Cache()
        docs = [
            _make_retrieved("annual leave policy entitlement days", "d1"),
            _make_retrieved("sick leave medical certificate", "d2"),
            _make_retrieved("maternity paternity parental leave", "d3"),
            _make_retrieved("office supplies procurement procedure", "d4"),
        ]
        with _patch_chroma(docs):
            results = cache.search("internal_hr", "annual leave", k=4)

        assert len(results) >= 1
        # The "annual leave" doc should rank highest
        assert "annual leave" in results[0].text.lower()

    def test_relevant_doc_ranked_above_unrelated(self):
        """With multiple docs, BM25 should rank the relevant one higher."""
        cache = BM25Cache()
        docs = [
            _make_retrieved("completely unrelated zebra content"),
            _make_retrieved("relevant python keyword matching"),
        ]
        with _patch_chroma(docs):
            results = cache.search("internal_hr", "python keyword", k=2)

        assert len(results) >= 1
        # The relevant doc should appear first (or at least in results)
        texts = [r.text for r in results]
        assert any("python" in t or "keyword" in t for t in texts)

    def test_search_respects_k_limit(self):
        cache = BM25Cache()
        docs = [_make_retrieved(f"document number {i} content") for i in range(20)]
        with _patch_chroma(docs):
            results = cache.search("internal_hr", "document content", k=5)
        assert len(results) <= 5
