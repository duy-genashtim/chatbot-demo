"""Heading-aware text chunker for RAG pipeline.

Strategy:
1. If parsed pages carry heading_hints, group consecutive pages under the
   same section heading. Split within a section when it exceeds CHUNK_TOKENS.
2. Fallback: sliding-window split at CHUNK_TOKENS with OVERLAP_TOKENS overlap.

Token counting uses the ``len(text) // 4`` proxy (avoids tiktoken dependency).
Target: 800 tokens per chunk, 100-token overlap.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from app.rag.parsers.pdf_parser import ParsedDocument, ParsedPage

logger = logging.getLogger(__name__)

CHUNK_TOKENS: int = 800   # target max tokens per chunk
OVERLAP_TOKENS: int = 100  # sliding-window overlap in tokens


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """A text chunk ready for embedding and upsert into ChromaDB."""

    text: str
    metadata: dict = field(default_factory=dict)
    # metadata keys expected downstream:
    #   source (filename), section (heading or ""), doc_id, domain, page_start


# ---------------------------------------------------------------------------
# Token counting proxy
# ---------------------------------------------------------------------------

def _approx_tokens(text: str) -> int:
    """Approximate token count: len(text) // 4 (standard 4-chars-per-token rule)."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk(
    parsed: ParsedDocument,
    doc_id: str,
    domain: str,
) -> list[Chunk]:
    """Chunk a ParsedDocument into Chunk objects with metadata.

    Tries heading-aware grouping first; falls back to sliding window.

    Args:
        parsed: Output of pdf_parser.parse_pdf().
        doc_id: UUID string assigned by IngestionService for Chroma metadata.
        domain: Collection name, e.g. 'internal_hr' or 'external_policy'.

    Returns:
        List of Chunk objects (never empty for non-empty documents).
    """
    base_meta = {"source": parsed.filename, "doc_id": doc_id, "domain": domain}

    if _has_heading_hints(parsed.pages):
        chunks = _heading_aware_chunks(parsed.pages, base_meta)
        if chunks:
            logger.debug(
                "Heading-aware chunking: %s → %d chunks", parsed.filename, len(chunks)
            )
            return chunks

    # Fallback: sliding window over full text
    chunks = _sliding_window_chunks(parsed.full_text, base_meta)
    logger.debug(
        "Sliding-window chunking: %s → %d chunks", parsed.filename, len(chunks)
    )
    return chunks


# ---------------------------------------------------------------------------
# Heading-aware chunking
# ---------------------------------------------------------------------------

def _has_heading_hints(pages: list[ParsedPage]) -> bool:
    return any(p.heading_hint for p in pages)


def _heading_aware_chunks(
    pages: list[ParsedPage], base_meta: dict
) -> list[Chunk]:
    """Group pages by outline section; split oversized sections via sliding window."""
    chunks: list[Chunk] = []

    # Assign a section to each page: carry forward last non-empty heading
    current_section = ""
    section_pages: list[ParsedPage] = []

    def _flush(section: str, ps: list[ParsedPage]) -> None:
        text = "\n".join(p.text for p in ps if p.text.strip())
        if not text.strip():
            return
        page_start = ps[0].page_number if ps else 1
        meta = {**base_meta, "section": section, "page_start": page_start}
        sub = _split_by_token_limit(text, CHUNK_TOKENS, OVERLAP_TOKENS)
        for i, segment in enumerate(sub):
            chunks.append(
                Chunk(text=segment, metadata={**meta, "chunk_index": i})
            )

    for page in pages:
        if page.heading_hint and page.heading_hint != current_section:
            if section_pages:
                _flush(current_section, section_pages)
            current_section = page.heading_hint
            section_pages = [page]
        else:
            section_pages.append(page)

    if section_pages:
        _flush(current_section, section_pages)

    return chunks


# ---------------------------------------------------------------------------
# Sliding-window chunking
# ---------------------------------------------------------------------------

def _sliding_window_chunks(text: str, base_meta: dict) -> list[Chunk]:
    """Split flat text into overlapping windows of ~CHUNK_TOKENS tokens."""
    segments = _split_by_token_limit(text, CHUNK_TOKENS, OVERLAP_TOKENS)
    return [
        Chunk(
            text=seg,
            metadata={**base_meta, "section": "", "page_start": 1, "chunk_index": i},
        )
        for i, seg in enumerate(segments)
        if seg.strip()
    ]


# ---------------------------------------------------------------------------
# Core split helper
# ---------------------------------------------------------------------------

def _split_by_token_limit(
    text: str, max_tokens: int, overlap_tokens: int
) -> list[str]:
    """Split text into segments of at most max_tokens, with overlap.

    Works at word boundaries to avoid mid-word cuts.
    """
    words = text.split()
    if not words:
        return []

    # Approximate: 1 word ≈ 1.3 tokens on average; use chars/4 for consistency
    # We track cumulative character count and use //4 as token proxy.
    segments: list[str] = []
    start = 0
    total = len(words)

    while start < total:
        # Greedily accumulate words until we hit the token budget
        end = start
        char_count = 0
        while end < total and (char_count + len(words[end]) + 1) // 4 < max_tokens:
            char_count += len(words[end]) + 1  # +1 for space
            end += 1

        if end == start:
            # Single word is already over budget — include it anyway
            end = start + 1

        segment = " ".join(words[start:end])
        segments.append(segment)

        if end >= total:
            break

        # Compute overlap: step back overlap_tokens worth of words
        overlap_chars = overlap_tokens * 4  # reverse proxy
        back = end
        acc = 0
        while back > start and acc < overlap_chars:
            back -= 1
            acc += len(words[back]) + 1

        # next start = back (or end if no overlap possible)
        next_start = max(start + 1, back)
        start = next_start

    return segments
