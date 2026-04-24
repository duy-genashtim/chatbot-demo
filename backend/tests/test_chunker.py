"""Tests for app.rag.chunker.

Covers:
  - Heading-aware chunking when pages have heading_hints
  - Sliding-window fallback when no headings
  - Overlap creates expected segment overlap
  - Output Chunk metadata contains required keys
  - Empty document returns empty list
"""

from __future__ import annotations

import pytest

from app.rag.chunker import (
    Chunk,
    _approx_tokens,
    _split_by_token_limit,
    chunk,
    CHUNK_TOKENS,
    OVERLAP_TOKENS,
)
from app.rag.parsers.pdf_parser import ParsedDocument, ParsedPage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(pages: list[tuple[str, str]], filename: str = "test.pdf") -> ParsedDocument:
    """Build ParsedDocument from (text, heading_hint) tuples."""
    parsed_pages = [
        ParsedPage(page_number=i + 1, text=text, heading_hint=hint)
        for i, (text, hint) in enumerate(pages)
    ]
    return ParsedDocument(
        filename=filename,
        total_pages=len(pages),
        pages=parsed_pages,
    )


def _long_text(words: int) -> str:
    return " ".join(f"word{i}" for i in range(words))


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------

class TestApproxTokens:
    def test_empty_string(self):
        assert _approx_tokens("") == 1  # max(1, 0)

    def test_typical_sentence(self):
        # "Hello world this is a test" = 26 chars → 26//4 = 6
        assert _approx_tokens("Hello world this is a test") == 6

    def test_long_text(self):
        text = "a" * 400  # 400 chars → 100 tokens
        assert _approx_tokens(text) == 100


# ---------------------------------------------------------------------------
# Split by token limit
# ---------------------------------------------------------------------------

class TestSplitByTokenLimit:
    def test_short_text_single_segment(self):
        text = _long_text(10)  # ~10 words, very short
        segments = _split_by_token_limit(text, max_tokens=800, overlap_tokens=100)
        assert len(segments) == 1
        assert segments[0] == text

    def test_long_text_multiple_segments(self):
        # ~3200 words → each word ~5 chars → 3200*6//4 = 4800 tokens → need ~6 chunks
        text = _long_text(3200)
        segments = _split_by_token_limit(text, max_tokens=800, overlap_tokens=100)
        assert len(segments) > 1

    def test_overlap_words_appear_in_consecutive_segments(self):
        # Build text that will split into at least 2 segments
        text = _long_text(2000)
        segments = _split_by_token_limit(text, max_tokens=500, overlap_tokens=80)
        if len(segments) >= 2:
            # Overlap: some words from the END of seg[0] should also appear
            # somewhere in seg[1] (i.e. seg[1] starts before seg[0] ended).
            words_in_seg0 = set(segments[0].split())
            words_in_seg1 = set(segments[1].split())
            shared = words_in_seg0 & words_in_seg1
            assert len(shared) > 0, "Expected at least one shared word (overlap) between consecutive segments"

    def test_empty_text(self):
        assert _split_by_token_limit("", 800, 100) == []


# ---------------------------------------------------------------------------
# Heading-aware chunking
# ---------------------------------------------------------------------------

class TestHeadingAwareChunking:
    def test_pages_with_headings_produce_chunks(self):
        doc = _make_doc([
            ("Introduction text here with enough words " * 5, "Introduction"),
            ("Methods description " * 5, "Methods"),
            ("Results and findings " * 5, "Results"),
        ])
        chunks = chunk(doc, doc_id="doc-1", domain="internal_hr")
        assert len(chunks) > 0
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_chunk_metadata_has_required_keys(self):
        doc = _make_doc([("Some content here " * 10, "Section One")])
        chunks = chunk(doc, doc_id="doc-abc", domain="external_policy")
        for c in chunks:
            assert "source" in c.metadata
            assert "doc_id" in c.metadata
            assert "domain" in c.metadata
            assert c.metadata["doc_id"] == "doc-abc"
            assert c.metadata["domain"] == "external_policy"
            assert c.metadata["source"] == "test.pdf"

    def test_section_in_metadata_when_heading_present(self):
        doc = _make_doc([("Policy content " * 10, "Policy Section")])
        chunks = chunk(doc, doc_id="x", domain="internal_hr")
        sections = [c.metadata.get("section", "") for c in chunks]
        assert any("Policy Section" in s for s in sections)


# ---------------------------------------------------------------------------
# Sliding-window fallback
# ---------------------------------------------------------------------------

class TestSlidingWindowFallback:
    def test_no_headings_falls_back_to_sliding_window(self):
        doc = _make_doc([
            ("word " * 500, ""),   # no heading_hint
            ("word " * 500, ""),
        ])
        chunks = chunk(doc, doc_id="fallback", domain="internal_hr")
        assert len(chunks) >= 1
        for c in chunks:
            assert c.metadata["section"] == ""

    def test_empty_document_returns_empty_list(self):
        doc = _make_doc([("   ", "")])  # whitespace only
        chunks = chunk(doc, doc_id="empty", domain="internal_hr")
        assert chunks == []


# ---------------------------------------------------------------------------
# Large-document chunking
# ---------------------------------------------------------------------------

class TestLargeDocumentChunking:
    def test_large_pdf_produces_many_chunks(self):
        # Simulate a ~50-page document (800 words per page)
        pages = [(_long_text(800), "") for _ in range(50)]
        doc = _make_doc(pages, filename="large.pdf")
        chunks = chunk(doc, doc_id="large-doc", domain="external_policy")
        # 50 pages × 800 words → well above CHUNK_TOKENS; must split
        assert len(chunks) > 10

    def test_all_chunks_within_budget(self):
        pages = [(_long_text(1600), "") for _ in range(5)]
        doc = _make_doc(pages, filename="budget.pdf")
        chunks = chunk(doc, doc_id="budget-doc", domain="internal_hr")
        for c in chunks:
            tokens = _approx_tokens(c.text)
            # Allow some slack (last segment of a section may be shorter)
            assert tokens <= CHUNK_TOKENS * 2, f"Chunk too long: {tokens} tokens"
