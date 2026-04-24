"""Shared data type for chunks returned by retrieval components.

Kept in its own module to avoid circular imports between chroma_store,
bm25_index, hybrid_retriever, and reranker.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievedChunk:
    """A chunk returned from vector search or BM25 with its metadata."""

    text: str
    metadata: dict = field(default_factory=dict)
    score: float = 0.0  # raw retrieval score (distance, BM25 score, or rerank score)

    # Convenience accessors for common metadata keys
    @property
    def doc_id(self) -> str:
        return self.metadata.get("doc_id", "")

    @property
    def source(self) -> str:
        return self.metadata.get("source", "")

    @property
    def section(self) -> str:
        return self.metadata.get("section", "")

    @property
    def domain(self) -> str:
        return self.metadata.get("domain", "")
