"""PDF parser using pypdf — validates PDF header magic bytes before parsing.

Only PDFs accepted. Non-PDF input raises ValueError so ingestion_service
can return 400 to the caller without touching the database.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

from pypdf import PdfReader

logger = logging.getLogger(__name__)

# PDF magic-byte header (first 4 bytes of every valid PDF file)
_PDF_MAGIC = b"%PDF"


@dataclass
class ParsedPage:
    """Text extracted from a single PDF page with positional metadata."""

    page_number: int  # 1-based
    text: str
    heading_hint: str = ""  # outline/bookmark title if available for this page


@dataclass
class ParsedDocument:
    """Full parsed result from a PDF file."""

    filename: str
    total_pages: int
    pages: list[ParsedPage] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Concatenate all page texts (used for heading-unaware chunking)."""
        return "\n".join(p.text for p in self.pages if p.text.strip())


def parse_pdf(file_bytes: bytes, filename: str) -> ParsedDocument:
    """Parse PDF bytes into structured pages with heading hints.

    Args:
        file_bytes: Raw bytes of the uploaded file.
        filename:   Original filename (stored in metadata only).

    Returns:
        ParsedDocument with one ParsedPage per PDF page.

    Raises:
        ValueError: If the file is not a valid PDF (magic-byte check fails).
    """
    # --- 1. Magic-byte validation (header check, not extension) ---
    if not file_bytes[:4] == _PDF_MAGIC:
        raise ValueError(
            "Only PDF files are supported. Convert to PDF first."
        )

    # --- 2. Read with pypdf ---
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:
        raise ValueError(f"Failed to open PDF '{filename}': {exc}") from exc

    total_pages = len(reader.pages)
    logger.debug("Parsing PDF '%s': %d pages", filename, total_pages)

    # --- 3. Build page-number → outline-title mapping (heading hints) ---
    heading_map = _build_heading_map(reader, total_pages)

    # --- 4. Extract text per page ---
    pages: list[ParsedPage] = []
    for idx, page in enumerate(reader.pages):
        page_number = idx + 1
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            logger.warning("Page %d text extraction failed: %s", page_number, exc)
            text = ""

        pages.append(
            ParsedPage(
                page_number=page_number,
                text=text.strip(),
                heading_hint=heading_map.get(page_number, ""),
            )
        )

    return ParsedDocument(filename=filename, total_pages=total_pages, pages=pages)


def _build_heading_map(reader: PdfReader, total_pages: int) -> dict[int, str]:
    """Map 1-based page numbers to the nearest outline/bookmark title.

    Iterates the PDF outline (table of contents) entries. Each bookmark
    references a page; we assign its title to that page number so the
    chunker can use it as a section heading.

    Returns an empty dict when the PDF has no outline.
    """
    heading_map: dict[int, str] = {}
    try:
        outlines = reader.outline
        if not outlines:
            return heading_map
        _recurse_outline(reader, outlines, heading_map)
    except Exception as exc:
        logger.debug("Outline extraction skipped: %s", exc)
    return heading_map


def _recurse_outline(reader: PdfReader, outlines, heading_map: dict[int, str]) -> None:
    """Recursively walk nested outline entries."""
    for item in outlines:
        if isinstance(item, list):
            _recurse_outline(reader, item, heading_map)
        else:
            try:
                page_idx = reader.get_destination_page_number(item)
                page_number = page_idx + 1  # convert 0-based to 1-based
                title = getattr(item, "title", "") or ""
                if title and page_number not in heading_map:
                    heading_map[page_number] = title.strip()
            except Exception:
                pass  # skip malformed outline entries silently
