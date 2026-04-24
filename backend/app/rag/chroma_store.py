"""ChromaDB persistent store wrapper — dual-collection, externally-managed embeddings.

One ChromaStore is shared process-wide (singleton from get_chroma_store()).
Collections are created lazily per domain on first access.
We never set an embedding_function on collections — embeddings are computed
externally by EmbeddingProvider and passed in explicitly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import get_settings
from app.rag.chunker import Chunk
from app.rag.retrieved_chunk import RetrievedChunk

if TYPE_CHECKING:
    from chromadb import Collection

logger = logging.getLogger(__name__)

# Valid domain names — enforced to prevent collection-name injection
VALID_DOMAINS = {"internal_hr", "external_policy"}


class ChromaStore:
    """Thin wrapper around a persistent ChromaDB client.

    Collections are named exactly by domain string.
    Embeddings are always supplied by the caller — no built-in embedding function.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._client: chromadb.ClientAPI = chromadb.PersistentClient(
            path=path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        logger.info("ChromaStore opened at %s", path)

    # ------------------------------------------------------------------ #
    # Collection management
    # ------------------------------------------------------------------ #

    def get_or_create_collection(self, domain: str) -> "Collection":
        """Return existing collection or create it (no embedding function)."""
        _validate_domain(domain)
        return self._client.get_or_create_collection(
            name=domain,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------ #
    # Write operations
    # ------------------------------------------------------------------ #

    def upsert(
        self,
        domain: str,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> None:
        """Upsert chunks with their precomputed embeddings.

        IDs are derived from doc_id + chunk_index to make upserts idempotent
        (re-ingesting the same doc_id replaces prior chunks).
        """
        if not chunks:
            return
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) length mismatch"
            )

        col = self.get_or_create_collection(domain)
        ids = [_chunk_id(c) for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = [c.metadata for c in chunks]

        col.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
        logger.debug("ChromaStore.upsert: %d chunks into '%s'", len(chunks), domain)

    def delete_by_doc_id(self, domain: str, doc_id: str) -> None:
        """Remove all chunks belonging to doc_id from the domain collection."""
        _validate_domain(domain)
        col = self._client.get_or_create_collection(name=domain)
        col.delete(where={"doc_id": {"$eq": doc_id}})
        logger.info("ChromaStore: deleted chunks for doc_id=%s from '%s'", doc_id, domain)

    # ------------------------------------------------------------------ #
    # Read operations
    # ------------------------------------------------------------------ #

    def query(
        self,
        domain: str,
        embedding: list[float],
        k: int,
    ) -> list[RetrievedChunk]:
        """Vector similarity search. Returns up to k results (fewer if collection smaller)."""
        _validate_domain(domain)
        col = self._client.get_or_create_collection(name=domain)
        n = col.count()
        if n == 0:
            return []

        actual_k = min(k, n)
        result = col.query(
            query_embeddings=[embedding],
            n_results=actual_k,
            include=["documents", "metadatas", "distances"],
        )

        chunks: list[RetrievedChunk] = []
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]

        for text, meta, dist in zip(docs, metas, dists):
            # Cosine distance in Chroma: 0 = identical, 2 = opposite.
            # Convert to similarity score (higher = more relevant).
            score = 1.0 - (dist / 2.0)
            chunks.append(RetrievedChunk(text=text, metadata=meta or {}, score=score))

        return chunks

    def get_all_documents(self, domain: str) -> list[RetrievedChunk]:
        """Fetch all stored documents for BM25 index rebuild."""
        _validate_domain(domain)
        col = self._client.get_or_create_collection(name=domain)
        n = col.count()
        if n == 0:
            return []

        result = col.get(include=["documents", "metadatas"])
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []

        return [
            RetrievedChunk(text=text, metadata=meta or {})
            for text, meta in zip(docs, metas)
        ]

    def count(self, domain: str) -> int:
        """Return number of chunks stored for domain."""
        _validate_domain(domain)
        col = self._client.get_or_create_collection(name=domain)
        return col.count()

    def get_chunks_by_doc_id(self, domain: str, doc_id: str) -> list[RetrievedChunk]:
        """Return all chunks whose metadata.doc_id matches — ordered by chunk_index."""
        _validate_domain(domain)
        col = self._client.get_or_create_collection(name=domain)
        result = col.get(
            where={"doc_id": {"$eq": doc_id}},
            include=["documents", "metadatas"],
        )
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
        items = [
            RetrievedChunk(text=text, metadata=meta or {})
            for text, meta in zip(docs, metas)
        ]
        items.sort(key=lambda c: int(c.metadata.get("chunk_index", 0) or 0))
        return items


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _validate_domain(domain: str) -> None:
    if domain not in VALID_DOMAINS:
        raise ValueError(f"Invalid domain '{domain}'. Must be one of {VALID_DOMAINS}")


def _chunk_id(chunk: Chunk) -> str:
    """Stable deterministic ID for a chunk — doc_id + chunk_index."""
    doc_id = chunk.metadata.get("doc_id", "unknown")
    idx = chunk.metadata.get("chunk_index", 0)
    return f"{doc_id}_{idx}"


# ------------------------------------------------------------------ #
# Singleton factory
# ------------------------------------------------------------------ #

_store_singleton: ChromaStore | None = None


def get_chroma_store() -> ChromaStore:
    """Return process-level ChromaStore singleton."""
    global _store_singleton
    if _store_singleton is None:
        path = get_settings().CHROMA_PATH
        _store_singleton = ChromaStore(path=path)
    return _store_singleton
