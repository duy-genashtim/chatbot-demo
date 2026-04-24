"""Admin document management routes — upload / list / delete.

Mounted under /api/admin (router-level require_admin already applied in main.py).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.dependencies import User, require_admin
from app.core.db import get_db
from app.services import audit_service
from app.services.documents_service import DocumentsService, get_documents_service
from app.services.ingestion_service import IngestionService, get_ingestion_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-documents"])


# ------------------------------------------------------------------ #
# POST /documents/upload
# ------------------------------------------------------------------ #

@router.post("/documents/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    domain: str = Query(..., description="Target domain: internal_hr or external_policy"),
    invalidate_cache: bool = Query(True),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Accept a PDF upload and queue background ingestion.

    Returns immediately with status=processing and the assigned doc_id.
    Poll GET /documents to track completion.
    """
    from app.rag.chroma_store import VALID_DOMAINS

    if domain not in VALID_DOMAINS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Miền không hợp lệ '{domain}'. Phải là một trong: {sorted(VALID_DOMAINS)}",
        )

    # Read file bytes eagerly (UploadFile is not safe to read in a background task)
    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File tải lên rỗng.",
        )

    # Enforce admin-configurable upload size cap (read live from settings).
    from app.core.settings_service import SettingsService
    max_mb = SettingsService(db).get("MAX_UPLOAD_SIZE_MB", default=20, cast=int)
    max_bytes = max(1, max_mb) * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File quá lớn ({len(file_bytes) / 1_048_576:.1f} MB). "
                   f"Giới hạn hiện tại: {max_mb} MB. Điều chỉnh MAX_UPLOAD_SIZE_MB trong cài đặt quản trị.",
        )

    # Pre-validate PDF magic bytes before spawning background task
    if file_bytes[:4] != b"%PDF":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chỉ chấp nhận file PDF. File được tải lên không phải PDF hợp lệ.",
        )

    filename = file.filename or "upload.pdf"
    # Store display name (fallback email) so admin UI shows friendly name
    uploaded_by = user.name or user.email

    # Create the DB row now (status=processing) so callers can poll immediately.
    # The actual heavy pipeline runs in a background task.
    svc = get_ingestion_service(db)

    async def _run_ingest() -> None:
        try:
            await svc.ingest(
                file_bytes=file_bytes,
                filename=filename,
                domain=domain,
                uploaded_by=uploaded_by,
                invalidate_cache=invalidate_cache,
            )
        except Exception as exc:
            logger.error("Background ingest failed for %r: %s", filename, exc)

    # Ingest inline for small files to keep the API simple; use BackgroundTasks
    # to avoid blocking the response for larger uploads.
    background_tasks.add_task(_run_ingest)

    # Return a placeholder — actual doc_id assigned inside ingest(); client polls list.
    audit_service.log(
        db,
        actor_email=uploaded_by,
        action="document.upload",
        target=filename,
        meta={"domain": domain, "size_bytes": len(file_bytes), "invalidate_cache": invalidate_cache},
    )

    return {
        "status": "processing",
        "filename": filename,
        "domain": domain,
        "message": "Đã tiếp nhận file. Xem GET /api/admin/documents để theo dõi cập nhật trạng thái.",
    }


# ------------------------------------------------------------------ #
# GET /documents
# ------------------------------------------------------------------ #

@router.get("/documents")
def list_documents(
    domain: str | None = Query(None),
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """List all ingested documents, optionally filtered by domain."""
    svc = DocumentsService(db)
    docs = svc.list_documents(domain=domain)
    return [svc.to_dict(d) for d in docs]


# ------------------------------------------------------------------ #
# GET /documents/{doc_id}/details — chunk-level inspection
# ------------------------------------------------------------------ #

@router.get("/documents/{doc_id}/details")
def document_details(
    doc_id: str,
    preview_limit: int = Query(5, ge=0, le=50, description="How many chunks to include as preview"),
    preview_chars: int = Query(400, ge=50, le=4000, description="Max chars per preview chunk"),
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """Return on-demand chunk-level aggregates + preview for a document.

    Queries ChromaDB for all chunks belonging to doc_id in the document's domain.
    Computes: chunk_count, total_chars, avg_chunk_chars, page_range, sections,
    and returns a small preview slice (first N chunks, truncated text).
    """
    from app.rag.chroma_store import get_chroma_store

    docs_svc = DocumentsService(db)
    doc = docs_svc.get_by_doc_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="không tìm thấy tài liệu")

    store = get_chroma_store()
    try:
        chunks = store.get_chunks_by_doc_id(doc.domain, doc_id)
    except Exception as exc:
        logger.warning("Chroma query failed for doc_id=%s: %s", doc_id, exc)
        chunks = []

    chunk_count = len(chunks)
    total_chars = sum(len(c.text or "") for c in chunks)
    avg_chunk_chars = (total_chars / chunk_count) if chunk_count else 0

    # Page range and unique sections (best-effort from metadata)
    pages: list[int] = []
    sections: set[str] = set()
    for c in chunks:
        ps = c.metadata.get("page_start")
        if isinstance(ps, int):
            pages.append(ps)
        elif isinstance(ps, str) and ps.isdigit():
            pages.append(int(ps))
        sec = c.metadata.get("section")
        if isinstance(sec, str) and sec:
            sections.add(sec)

    page_min = min(pages) if pages else None
    page_max = max(pages) if pages else None

    # Preview slice: first N chunks, truncated
    preview = [
        {
            "chunk_index": int(c.metadata.get("chunk_index", i) or i),
            "section": c.metadata.get("section") or "",
            "page_start": c.metadata.get("page_start"),
            "chars": len(c.text or ""),
            "text": (c.text or "")[:preview_chars]
            + ("…" if len(c.text or "") > preview_chars else ""),
        }
        for i, c in enumerate(chunks[:preview_limit])
    ]

    return {
        "document": docs_svc.to_dict(doc),
        "chunk_count": chunk_count,
        "total_chars": total_chars,
        "avg_chunk_chars": round(avg_chunk_chars, 1),
        "page_start_min": page_min,
        "page_start_max": page_max,
        "unique_sections": sorted(sections),
        "preview": preview,
    }


# ------------------------------------------------------------------ #
# DELETE /documents/{doc_id}
# ------------------------------------------------------------------ #

@router.delete("/documents/{doc_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    doc_id: str,
    invalidate_cache: bool = Query(True),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a document from Chroma, BM25, and the registry."""
    ingest_svc = get_ingestion_service(db)
    try:
        await ingest_svc.delete_doc(doc_id, invalidate_cache=invalidate_cache)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    audit_service.log(
        db,
        actor_email=user.email,
        action="document.delete",
        target=doc_id,
        meta={"invalidate_cache": invalidate_cache},
    )
    return {"deleted": doc_id}
