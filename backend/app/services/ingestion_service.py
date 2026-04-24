"""Ingestion service — orchestrates PDF upload → parse → chunk → embed → store.

Public API:
    ingest(file_bytes, filename, domain, uploaded_by, invalidate_cache=True) -> str
    delete_doc(doc_id, invalidate_cache=True)

All blocking I/O (parse, embed, chroma upsert) is dispatched via asyncio.to_thread
so the FastAPI event loop is never blocked (B8 fix).

On ingest success:
  1. Document row created (status=processing)
  2. PDF parsed + chunked
  3. Embeddings computed (batched)
  4. Chunks upserted to ChromaDB
  5. BM25 dirty flag set for domain (B4 fix)
  6. Gemini context cache optionally invalidated
  7. Document row updated to status=ready

On any exception: Document row updated to status=failed with error_msg.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.rag.bm25_index import get_bm25_cache
from app.rag.chroma_store import get_chroma_store
from app.rag.chunker import chunk
from app.rag.embedding_provider import get_embedding_provider
from app.rag.parsers.pdf_parser import parse_pdf

logger = logging.getLogger(__name__)


class IngestionService:
    """Handles document ingestion lifecycle for a single DB session."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------ #
    # Public: ingest
    # ------------------------------------------------------------------ #

    async def ingest(
        self,
        file_bytes: bytes,
        filename: str,
        domain: str,
        uploaded_by: str = "",
        invalidate_cache: bool = True,
    ) -> str:
        """Ingest a PDF document into the RAG pipeline.

        Returns:
            doc_id (UUID string) assigned to the document.

        Raises:
            ValueError: If the file is not a valid PDF.
            RuntimeError: On any other ingestion failure (after DB update).
        """
        # Validate PDF header before touching DB
        _validate_pdf_header(file_bytes)

        doc_id = str(uuid.uuid4())
        doc = _create_document_row(
            db=self._db,
            doc_id=doc_id,
            filename=filename,
            domain=domain,
            size_bytes=len(file_bytes),
            uploaded_by=uploaded_by,
        )

        try:
            # Parse (blocking) → chunk → embed (blocking) → upsert (blocking)
            parsed = await asyncio.to_thread(parse_pdf, file_bytes, filename)
            chunks = await asyncio.to_thread(chunk, parsed, doc_id, domain)

            if not chunks:
                raise ValueError(f"PDF '{filename}' produced no text chunks after parsing")

            texts = [c.text for c in chunks]
            provider = get_embedding_provider()
            embeddings = await asyncio.to_thread(provider.embed_documents, texts)

            store = get_chroma_store()
            await asyncio.to_thread(store.upsert, domain, chunks, embeddings)

            # Mark BM25 dirty so next search triggers rebuild (B4 fix)
            get_bm25_cache().mark_dirty(domain)

            # Optionally invalidate Gemini context cache
            if invalidate_cache:
                _try_invalidate_cache(domain)

            # Update document status to ready
            doc.status = "ready"
            self._db.commit()

            logger.info(
                "Ingestion complete: doc_id=%s filename=%r domain=%s chunks=%d",
                doc_id, filename, domain, len(chunks),
            )
            return doc_id

        except Exception as exc:
            logger.error(
                "Ingestion failed: doc_id=%s filename=%r: %s", doc_id, filename, exc
            )
            doc.status = "failed"
            doc.error_msg = str(exc)[:1000]
            self._db.commit()
            raise

    # ------------------------------------------------------------------ #
    # Public: delete
    # ------------------------------------------------------------------ #

    async def delete_doc(self, doc_id: str, invalidate_cache: bool = True) -> None:
        """Remove a document from Chroma, BM25, and the Document table.

        Args:
            doc_id: UUID string of the document to delete.
            invalidate_cache: Whether to invalidate the Gemini context cache.
        """
        from app.models.document import Document

        doc = self._db.query(Document).filter(Document.doc_id == doc_id).first()
        if doc is None:
            raise ValueError(f"Document not found: doc_id={doc_id}")

        domain = doc.domain

        # Remove from Chroma
        store = get_chroma_store()
        await asyncio.to_thread(store.delete_by_doc_id, domain, doc_id)

        # Mark BM25 dirty
        get_bm25_cache().mark_dirty(domain)

        # Optionally invalidate Gemini cache
        if invalidate_cache:
            _try_invalidate_cache(domain)

        # Remove DB row
        self._db.delete(doc)
        self._db.commit()

        logger.info("Document deleted: doc_id=%s domain=%s", doc_id, domain)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

_PDF_MAGIC = b"%PDF"


def _validate_pdf_header(file_bytes: bytes) -> None:
    if file_bytes[:4] != _PDF_MAGIC:
        raise ValueError("Only PDF files are supported. Convert to PDF first.")


def _create_document_row(
    db: Session,
    doc_id: str,
    filename: str,
    domain: str,
    size_bytes: int,
    uploaded_by: str,
):
    from app.models.document import Document

    doc = Document(
        doc_id=doc_id,
        filename=filename,
        domain=domain,
        size_bytes=size_bytes,
        uploaded_by=uploaded_by,
        uploaded_at=datetime.now(timezone.utc),
        status="processing",
        error_msg=None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _try_invalidate_cache(domain: str) -> None:
    """Attempt to invalidate Gemini context cache for domain. Logs but never raises."""
    try:
        from app.main import get_cache_manager
        mgr = get_cache_manager()
        # Cache display_name matches the domain string (convention from phase 03)
        invalidated = mgr.invalidate(domain)
        if invalidated:
            logger.info("Gemini context cache invalidated for domain '%s'", domain)
    except Exception as exc:
        logger.warning("Could not invalidate Gemini cache for '%s': %s", domain, exc)


# ------------------------------------------------------------------ #
# Dependency factory for FastAPI Depends
# ------------------------------------------------------------------ #

def get_ingestion_service(db: Session) -> IngestionService:
    """FastAPI dependency factory — phase 06 admin routes use Depends(get_ingestion_service)."""
    return IngestionService(db)
