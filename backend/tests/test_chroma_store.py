"""Tests for app.rag.chroma_store.ChromaStore.

Uses a real ChromaDB instance on a tmp_path (no mocking of Chroma internals).
Verifies upsert + query round-trip, delete_by_doc_id, count, and domain validation.
"""

from __future__ import annotations

import uuid

import pytest

from app.rag.chunker import Chunk
from app.rag.chroma_store import ChromaStore, _validate_domain, VALID_DOMAINS
from app.rag.retrieved_chunk import RetrievedChunk


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def store(tmp_path) -> ChromaStore:
    """Fresh ChromaStore pointing at a temp directory."""
    return ChromaStore(path=str(tmp_path / "chroma"))


def _fake_embedding(text: str, dim: int = 8) -> list[float]:
    """Deterministic fake embedding: hash-based, dimension dim."""
    h = hash(text) & 0xFFFFFFFF
    base = [(h >> i & 0xFF) / 255.0 for i in range(dim)]
    # normalise to unit vector
    norm = sum(x * x for x in base) ** 0.5 or 1.0
    return [x / norm for x in base]


def _make_chunk(text: str, doc_id: str, domain: str, idx: int = 0) -> Chunk:
    return Chunk(
        text=text,
        metadata={"doc_id": doc_id, "domain": domain, "source": "test.pdf",
                  "section": "", "chunk_index": idx},
    )


# ---------------------------------------------------------------------------
# Domain validation
# ---------------------------------------------------------------------------

class TestDomainValidation:
    def test_valid_domains_accepted(self):
        for d in VALID_DOMAINS:
            _validate_domain(d)  # should not raise

    def test_invalid_domain_raises(self):
        with pytest.raises(ValueError, match="Invalid domain"):
            _validate_domain("unknown_domain")


# ---------------------------------------------------------------------------
# Count
# ---------------------------------------------------------------------------

class TestChromaStoreCount:
    def test_empty_collection_count_zero(self, store):
        assert store.count("internal_hr") == 0

    def test_count_after_upsert(self, store):
        doc_id = str(uuid.uuid4())
        chunks = [_make_chunk("hello world", doc_id, "internal_hr", i) for i in range(3)]
        embs = [_fake_embedding(c.text) for c in chunks]
        store.upsert("internal_hr", chunks, embs)
        assert store.count("internal_hr") == 3


# ---------------------------------------------------------------------------
# Upsert + Query round-trip
# ---------------------------------------------------------------------------

class TestChromaStoreUpsertQuery:
    def test_upsert_then_query_returns_results(self, store):
        doc_id = str(uuid.uuid4())
        texts = ["The quick brown fox", "Lazy dog jumps over", "Python is awesome"]
        chunks = [_make_chunk(t, doc_id, "external_policy", i) for i, t in enumerate(texts)]
        embs = [_fake_embedding(t) for t in texts]
        store.upsert("external_policy", chunks, embs)

        query_emb = _fake_embedding("The quick brown fox")
        results = store.query("external_policy", query_emb, k=2)

        assert len(results) > 0
        assert all(isinstance(r, RetrievedChunk) for r in results)

    def test_query_returns_most_similar_first(self, store):
        doc_id = str(uuid.uuid4())
        # Use identical embedding for target text — should rank highest
        target = "exact match text"
        other = "completely different words"
        chunks = [
            _make_chunk(target, doc_id, "internal_hr", 0),
            _make_chunk(other, doc_id, "internal_hr", 1),
        ]
        embs = [_fake_embedding(t) for t in [target, other]]
        store.upsert("internal_hr", chunks, embs)

        query_emb = _fake_embedding(target)
        results = store.query("internal_hr", query_emb, k=2)
        assert results[0].text == target

    def test_upsert_idempotent_same_doc_id(self, store):
        """Re-ingesting same doc_id replaces rather than duplicates."""
        doc_id = str(uuid.uuid4())
        chunk_v1 = _make_chunk("version one text", doc_id, "internal_hr", 0)
        chunk_v2 = _make_chunk("version two text", doc_id, "internal_hr", 0)
        store.upsert("internal_hr", [chunk_v1], [_fake_embedding(chunk_v1.text)])
        store.upsert("internal_hr", [chunk_v2], [_fake_embedding(chunk_v2.text)])
        # Count should still be 1 (upsert replaces)
        assert store.count("internal_hr") == 1

    def test_query_empty_collection_returns_empty(self, store):
        query_emb = _fake_embedding("anything")
        results = store.query("internal_hr", query_emb, k=5)
        assert results == []

    def test_mismatched_chunks_embeddings_raises(self, store):
        doc_id = str(uuid.uuid4())
        chunks = [_make_chunk("text", doc_id, "internal_hr", 0)]
        with pytest.raises(ValueError, match="length mismatch"):
            store.upsert("internal_hr", chunks, [])


# ---------------------------------------------------------------------------
# Delete by doc_id
# ---------------------------------------------------------------------------

class TestChromaStoreDelete:
    def test_delete_removes_chunks(self, store):
        doc_id = str(uuid.uuid4())
        chunks = [_make_chunk(f"doc text {i}", doc_id, "internal_hr", i) for i in range(3)]
        embs = [_fake_embedding(c.text) for c in chunks]
        store.upsert("internal_hr", chunks, embs)
        assert store.count("internal_hr") == 3

        store.delete_by_doc_id("internal_hr", doc_id)
        assert store.count("internal_hr") == 0

    def test_delete_nonexistent_doc_id_is_safe(self, store):
        """Deleting a non-existent doc_id should not raise."""
        store.delete_by_doc_id("internal_hr", "nonexistent-uuid")

    def test_delete_only_removes_target_doc(self, store):
        doc_a = str(uuid.uuid4())
        doc_b = str(uuid.uuid4())
        chunks_a = [_make_chunk("doc A text", doc_a, "external_policy", 0)]
        chunks_b = [_make_chunk("doc B text", doc_b, "external_policy", 0)]
        store.upsert("external_policy", chunks_a, [_fake_embedding(chunks_a[0].text)])
        store.upsert("external_policy", chunks_b, [_fake_embedding(chunks_b[0].text)])
        assert store.count("external_policy") == 2

        store.delete_by_doc_id("external_policy", doc_a)
        assert store.count("external_policy") == 1


# ---------------------------------------------------------------------------
# get_all_documents
# ---------------------------------------------------------------------------

class TestChromaStoreGetAll:
    def test_get_all_returns_all_chunks(self, store):
        doc_id = str(uuid.uuid4())
        chunks = [_make_chunk(f"text {i}", doc_id, "internal_hr", i) for i in range(5)]
        embs = [_fake_embedding(c.text) for c in chunks]
        store.upsert("internal_hr", chunks, embs)
        all_docs = store.get_all_documents("internal_hr")
        assert len(all_docs) == 5

    def test_get_all_empty_returns_empty(self, store):
        assert store.get_all_documents("external_policy") == []
