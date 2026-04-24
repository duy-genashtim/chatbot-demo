"""Cross-encoder reranker using sentence-transformers.

Loads 'cross-encoder/ms-marco-MiniLM-L-6-v2' ONCE at startup via initialize().
The model is called synchronously — wrap in asyncio.to_thread from HybridRetriever.

If sentence-transformers or the model download is unavailable, initialize()
logs a warning and sets _model = None. rerank() then returns the input list
unchanged (passthrough fallback so the pipeline does not crash).
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.rag.retrieved_chunk import RetrievedChunk

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Wraps a sentence-transformers CrossEncoder for passage reranking."""

    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.RERANKER_MODEL
        self._model = None  # loaded lazily via initialize()

    def initialize(self) -> None:
        """Load the CrossEncoder model. Called once from main.py lifespan.

        Logs a warning and continues (with passthrough fallback) if the model
        cannot be loaded (e.g. no internet, sentence-transformers not installed).
        """
        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self._model_name)
            logger.info("CrossEncoderReranker loaded: %s", self._model_name)
        except Exception as exc:
            logger.warning(
                "CrossEncoderReranker: could not load '%s': %s — reranking disabled (passthrough)",
                self._model_name,
                exc,
            )
            self._model = None

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top: int,
    ) -> list[RetrievedChunk]:
        """Score each chunk against query and return top-k reranked results.

        Falls back to returning the first ``top`` chunks unchanged when the
        model is not loaded (preserves pipeline correctness under any env).
        """
        if not chunks:
            return []

        if self._model is None:
            # Passthrough fallback — preserve original order
            logger.debug("CrossEncoderReranker: passthrough (model not loaded)")
            return chunks[:top]

        pairs = [(query, chunk.text) for chunk in chunks]
        try:
            scores = self._model.predict(pairs)
        except Exception as exc:
            logger.error("CrossEncoderReranker.predict failed: %s", exc)
            return chunks[:top]

        scored = sorted(
            zip(scores, chunks), key=lambda x: float(x[0]), reverse=True
        )
        result = []
        for score, chunk in scored[:top]:
            result.append(
                RetrievedChunk(
                    text=chunk.text,
                    metadata=chunk.metadata,
                    score=float(score),
                )
            )
        return result


# ------------------------------------------------------------------ #
# Singleton factory
# ------------------------------------------------------------------ #

_reranker_singleton: CrossEncoderReranker | None = None


def get_reranker() -> CrossEncoderReranker:
    """Return process-level CrossEncoderReranker singleton (NOT yet initialised)."""
    global _reranker_singleton
    if _reranker_singleton is None:
        _reranker_singleton = CrossEncoderReranker()
    return _reranker_singleton
