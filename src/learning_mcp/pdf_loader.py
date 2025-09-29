# /app/src/learning_mcp/pdf_loader.py
"""
PDF Loader utilities.

Purpose:
- Open a PDF and extract text ONLY from specified pages (limit load at source).
- Support include/exclude page specs (single numbers or ranges like "1-20,22,40-50").
- Provide helpers used by routes:
    1) extract_text(...) -> str                 : concatenated text from selected pages
    2) load_pdf(...)     -> list[str]           : simple chunks (backward compatible)
    3) load_pdf_structured(...) -> list[dict]   : rich chunks with metadata for RAG/summarization

Notes:
- This file is backward-compatible: existing callers of load_pdf(...) are unaffected.
- For new retrieval/summarization, prefer load_pdf_structured(...).
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any, Iterable, Tuple
from dataclasses import dataclass, asdict
import re
import unicodedata
import hashlib

try:
    # Prefer the maintained fork if already installed
    from pypdf import PdfReader  # type: ignore
except Exception:  # fall back if project still uses PyPDF2
    from PyPDF2 import PdfReader  # type: ignore

from .page_ranges import compute_pages


# -------------------------------
# Internal heuristics & utilities
# -------------------------------

_CODE_HINTS = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b\s+\/|"
    r"\b(limit|offset|cursor|page(Token)?|per_page|maxResults)\b|"
    r"`{1,3}|^\s{2,}\S|^\t+\S|"
    r"\{[\s\S]*?\}|\[[\s\S]*?\]|"       # JSON-ish brackets (coarse)
    r"HTTP\/1\.[01]|Authorization:|Bearer\s+[A-Za-z0-9\-_\.]+|"
    r"^#+\s|\bExample(s)?\b|\bParameters?\b",
    re.IGNORECASE | re.MULTILINE,
)

_TABLE_HINTS = re.compile(
    r"\|.+\||"         # markdown-like tables
    r"(?:\S+\s+\S+\s+\S+){3,}",  # multiple columns by spacing (very rough)
    re.MULTILINE,
)

_SENTENCE_END = re.compile(r"([\.!?])(\s+)")
_MULTI_SPACE = re.compile(r"\s+")
_DIGIT_ONLY_LINE = re.compile(r"^\s*\d+\s*$", re.MULTILINE)


@dataclass
class Chunk:
    doc_id: str
    chunk_id: str
    text: str
    page_start: int
    page_end: int
    char_start: int
    char_end: int
    heading_path: List[str]
    section_id: str
    has_code: bool
    has_table: bool
    needs_layout: bool
    hash: str


def _looks_like_code(text: str) -> bool:
    return bool(_CODE_HINTS.search(text))


def _looks_like_table(text: str) -> bool:
    return bool(_TABLE_HINTS.search(text))


def _strip_page_numbers_top_bottom(text: str, max_lines: int = 3) -> str:
    """
    Remove digit-only lines but only from the first/last few lines (avoid nuking numbered code).
    """
    if not text:
        return text
    lines = text.splitlines()
    # top slice
    top_n = min(max_lines, len(lines))
    for i in range(top_n):
        if _DIGIT_ONLY_LINE.match(lines[i] or ""):
            lines[i] = ""
    # bottom slice
    bot_n = max(0, len(lines) - max_lines)
    for i in range(bot_n, len(lines)):
        if _DIGIT_ONLY_LINE.match(lines[i] or ""):
            lines[i] = ""
    return "\n".join(lines)


def _clean_text(raw: str, preserve_whitespace: bool = False) -> str:
    """Normalize PDF text before chunking/embedding."""
    if not raw:
        return ""
    text = raw

    # Unicode normalize; keep symbols readable
    text = unicodedata.normalize("NFKC", text)

    # Remove page numbers at top/bottom only
    text = _strip_page_numbers_top_bottom(text)

    if preserve_whitespace:
        # Keep indentation and line breaks (for code/tables)
        # But still tame obviously broken multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text).rstrip()
    else:
        # Collapse whitespace aggressively for narrative text
        text = _MULTI_SPACE.sub(" ", text).strip()

    return text


def _iter_selected_pages(reader: PdfReader, include_pages: Optional[str], exclude_pages: Optional[str]):
    total_pages = len(reader.pages)
    pages_to_process = compute_pages(
        include_spec=include_pages,
        exclude_spec=exclude_pages,
        total_pages=total_pages,
    )
    for page_num in pages_to_process:
        yield page_num, reader.pages[page_num - 1]  # library is 0-based; specs are 1-based


def _sentence_aware_chunks(text: str, target: int, overlap: int, preserve_whitespace: bool) -> List[str]:
    """
    Split text near sentence boundaries; fallback to sliding window.
    Character-based, but tries to end chunks after punctuation.
    """
    if not text:
        return []

    # Fast path: if preserve_whitespace (code/table), avoid smart splitting to not break blocks
    if preserve_whitespace:
        step = max(1, target - max(0, overlap))
        return [text[i:i + target] for i in range(0, len(text), step)]

    chunks: List[str] = []
    buf: List[str] = []
    length = 0

    def flush():
        nonlocal buf, length
        if buf:
            chunks.append("".join(buf).strip())
            buf = []
            length = 0

    # Reinsert sentence boundaries as tokens to help chunking
    tokens = _SENTENCE_END.split(text)
    # tokens like [segment, '.', space, segment, '!', space, ...]

    i = 0
    while i < len(tokens):
        seg = tokens[i]
        i += 1
        if i + 1 < len(tokens) and tokens[i] in (".", "!", "?"):
            seg += tokens[i] + tokens[i + 1]  # include punctuation + following space
            i += 2
        if length + len(seg) > target and length >= max(1, target // 2):
            flush()
            # start new with overlap from previous
            if overlap and chunks:
                # take tail from last chunk as overlap (best-effort)
                tail = chunks[-1][-overlap:]
                if tail:
                    buf.append(tail)
                    length = len(tail)
        buf.append(seg)
        length += len(seg)

    flush()

    # Fallback if something odd happened
    if not chunks:
        step = max(1, target - max(0, overlap))
        chunks = [text[i:i + target] for i in range(0, len(text), step)]
    return [c for c in chunks if c]


def _make_chunk_hash(doc_id: str, page_span: Tuple[int, int], slice_text: str) -> str:
    h = hashlib.sha1()
    h.update(doc_id.encode("utf-8", errors="ignore"))
    h.update(f"{page_span[0]}-{page_span[1]}".encode("utf-8"))
    h.update(slice_text.encode("utf-8", errors="ignore"))
    return h.hexdigest()


# -------------------------------
# Public API (backward compatible)
# -------------------------------

def extract_text(
    file_path: str,
    include_pages: Optional[str] = None,
    exclude_pages: Optional[str] = None,
) -> str:
    """
    Concatenate raw text from the selected PDF pages.

    Returns:
        A single string containing text from the chosen pages in order.
    """
    reader = PdfReader(file_path)
    parts: List[str] = []
    for _, page in _iter_selected_pages(reader, include_pages, exclude_pages):
        cleaned = _clean_text(page.extract_text() or "")
        if cleaned:
            parts.append(cleaned)
    return "\n\n".join(parts)


def load_pdf(
    file_path: str,
    include_pages: Optional[str] = None,
    exclude_pages: Optional[str] = None,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> List[str]:
    """
    Return chunked text from the selected PDF pages, suitable for embedding.

    NOTE: Simple character-based chunking without metadata (legacy behavior).
    Prefer load_pdf_structured(...) for retrieval/summarization pipelines.
    """
    reader = PdfReader(file_path)
    chunks: List[str] = []
    step = max(1, chunk_size - max(0, chunk_overlap))
    for _, page in _iter_selected_pages(reader, include_pages, exclude_pages):
        text = _clean_text(page.extract_text() or "")
        if not text:
            continue
        for i in range(0, len(text), step):
            chunk = text[i:i + chunk_size]
            if chunk:
                chunks.append(chunk)
    return chunks


# -----------------------------------
# New structured API (preferred path)
# -----------------------------------

def load_pdf_structured(
    file_path: str,
    *,
    doc_id: str,
    include_pages: Optional[str] = None,
    exclude_pages: Optional[str] = None,
    chunk_size: int = 1200,
    chunk_overlap: int = 150,
    heading_resolver=None,
    section_resolver=None,
    layout_threshold_chars: int = 60,
) -> List[Dict[str, Any]]:
    """
    Return chunked text with metadata, suitable for RAG and topic-focused summarization.

    Args:
        file_path: path to the PDF.
        doc_id: stable identifier for the document (used in chunk ids & hashing).
        include_pages: e.g., "1-5,10,20-25" (takes precedence if provided).
        exclude_pages: e.g., "2,15-18" (applied after include or over full range).
        chunk_size: target characters per chunk (sentence-aware for prose).
        chunk_overlap: characters to overlap between chunks.
        heading_resolver: optional callable (page_text, page_idx) -> List[str] heading_path
        section_resolver: optional callable (page_text, page_idx) -> str section_id
        layout_threshold_chars: if a page extracts fewer chars than this, mark needs_layout=True.

    Returns:
        List[dict] where each dict has keys of Chunk dataclass.
    """
    reader = PdfReader(file_path)
    results: List[Dict[str, Any]] = []

    for page_num, page in _iter_selected_pages(reader, include_pages, exclude_pages):
        raw = page.extract_text() or ""
        # Heuristics: detect code/table BEFORE cleanup to decide whitespace policy
        pre_has_code = _looks_like_code(raw)
        pre_has_table = _looks_like_table(raw)
        preserve_ws = bool(pre_has_code or pre_has_table)

        cleaned = _clean_text(raw, preserve_whitespace=preserve_ws)
        if not cleaned:
            continue

        # Decide needs_layout: extremely short pages often indicate extraction issues
        needs_layout = len(cleaned) < layout_threshold_chars

        # Resolve headings/sections if caller provided resolvers; fallback to simple guesses
        heading_path = []
        if callable(heading_resolver):
            try:
                heading_path = list(heading_resolver(cleaned, page_num)) or []
            except Exception:
                heading_path = []
        section_id = ""
        if callable(section_resolver):
            try:
                section_id = str(section_resolver(cleaned, page_num) or "")
            except Exception:
                section_id = ""

        # Sentence-aware chunking for prose; sliding window for code/tables
        slices = _sentence_aware_chunks(
            cleaned,
            target=chunk_size,
            overlap=chunk_overlap,
            preserve_whitespace=preserve_ws,
        )

        page_has_code = pre_has_code or any(_looks_like_code(s) for s in slices[:2])
        page_has_table = pre_has_table or any(_looks_like_table(s) for s in slices[:2])

        # Build chunk objects
        char_cursor = 0
        for idx, slice_text in enumerate(slices):
            char_start = char_cursor
            char_end = char_cursor + len(slice_text)
            char_cursor = char_end  # local counter within this page's cleaned text

            c_hash = _make_chunk_hash(doc_id, (page_num, page_num), slice_text)
            chunk_id = f"{doc_id}:{page_num}:{idx}:{c_hash[:8]}"

            ch = Chunk(
                doc_id=doc_id,
                chunk_id=chunk_id,
                text=slice_text,
                page_start=page_num,
                page_end=page_num,
                char_start=char_start,
                char_end=char_end,
                heading_path=heading_path,
                section_id=section_id or f"p{page_num}",
                has_code=page_has_code,
                has_table=page_has_table,
                needs_layout=needs_layout,
                hash=c_hash,
            )
            results.append(asdict(ch))

    return results
