# src/learning_mcp/document_loaders.py
"""
Document loader registry (type-agnostic ingest)

Goal
----
Hide file-type branching from the worker. A single function
`collect_chunks(profile, chunk_size, chunk_overlap)` returns a uniform
list of chunk dicts:
    { "text": str, "metadata": { section?, title?, source, source_id?, path, doc_id, doc_path } }

Supported types
---------------
- pdf  : via pdf_loader.load_pdf_structured (rich metadata)
- json : via json_loader.load_json (flat, schema-agnostic)

Stats
-----
Also returns (files_total, pages_total) for preflight/progress.

Usage (in worker)
-----------------
from learning_mcp.document_loaders import collect_chunks, known_document_count, estimate_pages_total
chunks, stats = collect_chunks(profile, chunk_size, chunk_overlap)
# embed -> upsert using chunks (no need to know pdf/json in the worker)
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple, Iterable, Callable, Optional
import os

from .pdf_loader import load_pdf_structured
from .json_loader import load_json

# prefer pypdf if available (faster), fallback to PyPDF2
try:
    from pypdf import PdfReader  # type: ignore
except Exception:
    from PyPDF2 import PdfReader  # type: ignore

from .page_ranges import compute_pages


Chunk = Dict[str, Any]  # {"text": str, "metadata": {...}}


# -------- registry --------

def _load_pdf(doc_spec: Dict[str, Any], *, profile_name: str, chunk_size: int, chunk_overlap: int) -> List[Chunk]:
    """
    Use structured PDF loader and normalize to Chunk shape.
    """
    path = (doc_spec.get("path") or "").strip()
    if not path or not os.path.exists(path):
        return []

    # Allow per-doc include/exclude override; fallback to profile-level
    include_pages = doc_spec.get("include_pages")
    exclude_pages = doc_spec.get("exclude_pages")

    items = load_pdf_structured(
        path,
        doc_id=profile_name,
        include_pages=include_pages,
        exclude_pages=exclude_pages,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    out: List[Chunk] = []
    for it in items:
        # it already has: text, chunk_id, page_start/end, section_id, hash, etc.
        text = it.get("text", "")
        if not text:
            continue
        meta = {
            "section": it.get("section_id") or "pdf",
            "title": (it.get("heading_path") or ["pdf"])[-1] if isinstance(it.get("heading_path"), list) else "pdf",
            "source": os.path.basename(path),
            "source_id": it.get("chunk_id"),
            "path": f"{path}#p{it.get('page_start', '')}",
            "doc_id": profile_name,
            "doc_path": path,
            # keep useful pdf fields too
            "page_start": it.get("page_start"),
            "page_end": it.get("page_end"),
            "hash": it.get("hash"),
        }
        out.append({"text": text, "metadata": meta})
    return out


def _load_json(doc_spec: Dict[str, Any], *, profile_name: str, chunk_size: int, chunk_overlap: int) -> List[Chunk]:
    """
    Use flat JSON loader and normalize to Chunk shape.
    """
    path = (doc_spec.get("path") or "").strip()
    if not path or not os.path.exists(path):
        return []
    items = load_json(path, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    out: List[Chunk] = []
    for it in items:
        text = it.get("text", "")
        if not text:
            continue
        meta_in = it.get("metadata") or {}
        meta = {
            "section": meta_in.get("section") or "json",
            "title": meta_in.get("title"),
            "source": meta_in.get("source"),
            "source_id": meta_in.get("source_id") or meta_in.get("path"),
            "path": meta_in.get("path"),
            "doc_id": profile_name,
            "doc_path": path,
        }
        out.append({"text": text, "metadata": meta})
    return out


_LOADER_BY_TYPE: Dict[str, Callable[..., List[Chunk]]] = {
    "pdf": _load_pdf,
    "json": _load_json,
}


# -------- public API --------

def known_document_count(profile: Dict[str, Any]) -> int:
    """
    Count documents that have a known loader.
    """
    docs = profile.get("documents") or []
    return sum(1 for d in docs if _LOADER_BY_TYPE.get(str(d.get("type") or "").lower()))


def estimate_pages_total(profile: Dict[str, Any]) -> int:
    """
    Sum selected pages across all PDF docs for preflight UI. JSON contributes 0.
    """
    total = 0
    docs = profile.get("documents") or []
    for d in docs:
        if str(d.get("type") or "").lower() != "pdf":
            continue
        path = (d.get("path") or "").strip()
        if not path or not os.path.exists(path):
            continue
        try:
            reader = PdfReader(path)
            pages = compute_pages(
                include_spec=d.get("include_pages") or profile.get("include_pages"),
                exclude_spec=d.get("exclude_pages") or profile.get("exclude_pages"),
                total_pages=len(reader.pages),
            )
            total += len(pages)
        except Exception:
            # don't fail preflight on a single bad pdf
            continue
    return total


def collect_chunks(
    profile: Dict[str, Any],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> Tuple[List[Chunk], Dict[str, int]]:
    """
    Collect chunks from all known document types in the given profile.

    Returns:
        (chunks, stats)
        where stats = {"files_total": int, "pages_total": int}

    Behavior:
        - Ignores unknown doc types (logs can be added by caller).
        - Skips missing files.
    """
    profile_name = str(profile.get("name") or "profile").strip()
    docs = profile.get("documents") or []

    chunks: List[Chunk] = []
    files_total = 0

    for d in docs:
        dtype = str(d.get("type") or "").lower()
        loader = _LOADER_BY_TYPE.get(dtype)
        if not loader:
            # unknown type → skip; caller may log a warning
            continue

        pieces = loader(d, profile_name=profile_name, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        files_total += 1  # counted only for known types
        if pieces:
            chunks.extend(pieces)

    pages_total = estimate_pages_total(profile)  # JSON contributes 0
    return chunks, {"files_total": files_total, "pages_total": pages_total}
