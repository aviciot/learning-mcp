# src/learning_mcp/json_loader.py
"""
Flat JSON Loader (schema-agnostic)

Purpose
-------
Load ANY JSON file and emit chunk dicts consumable by the ingest worker:
    { "text": str, "metadata": { section, title, source, source_id, path } }

Behavior
--------
- Recursively walks the JSON.
- For leaf values:
  - strings -> chunk by size/overlap
  - numbers/bools -> stringify as one small chunk
  - nulls -> skipped
- Arrays:
  - of primitives -> joined with ", " then chunked
  - of objects    -> recurse into each element (/arr/0/key)
- No assumptions about domain or keys.

Deterministic IDs
-----------------
Upstream, derive point IDs from (profile | metadata.path | chunk_idx).
"""

from __future__ import annotations
from typing import Any, Dict, Iterable, List, Tuple
from pathlib import Path
import json
import re

# ------------- text utils -------------
_MULTI_WS = re.compile(r"\s+")

def _normalize_text(s: str) -> str:
    s = s or ""
    s = s.strip()
    s = _MULTI_WS.sub(" ", s)
    return s

_SENTENCE_END = re.compile(r"([\.!?])(\s+)")

def _sentence_aware_chunks(text: str, target: int, overlap: int) -> List[str]:
    if not text:
        return []
    if target <= 0:
        return [text]

    chunks: List[str] = []
    buf: List[str] = []
    length = 0

    def flush():
        nonlocal buf, length
        if buf:
            chunk = "".join(buf).strip()
            if chunk:
                chunks.append(chunk)
            buf, length = [], 0

    tokens = _SENTENCE_END.split(text)
    i = 0
    while i < len(tokens):
        seg = tokens[i]; i += 1
        if i + 1 < len(tokens) and tokens[i] in (".", "!", "?"):
            seg += tokens[i] + tokens[i + 1]; i += 2
        if length + len(seg) > target and length >= max(1, target // 2):
            flush()
            if overlap and chunks:
                tail = chunks[-1][-overlap:]
                if tail:
                    buf.append(tail)
                    length = len(tail)
        buf.append(seg)
        length += len(seg)
    flush()

    if not chunks:
        step = max(1, target - max(0, overlap))
        chunks = [text[i:i + target] for i in range(0, len(text), step)]
    return [c for c in chunks if c]

# ------------- JSON walkers -------------

def _is_primitive(x: Any) -> bool:
    return isinstance(x, (str, int, float, bool)) or x is None

def _flatten(root: Any, base: str = "") -> Iterable[Tuple[str, Any]]:
    """
    Yield (json_pointer_path, value) for leaf-like nodes.

    - dict  -> recurse by key
    - list  -> if primitives: join into a single value; if objects: recurse into elements
    - other -> yield as leaf
    """
    if isinstance(root, dict):
        for k, v in root.items():
            yield from _flatten(v, f"{base}/{k}")
        return

    if isinstance(root, list):
        if not root:
            return
        # if all primitives, join into a single leaf
        if all(_is_primitive(v) for v in root):
            # Join with ", " (preserves order)
            joined = ", ".join("" if v is None else str(v) for v in root)
            yield base or "/", joined
            return
        # otherwise recurse element-by-element
        for i, v in enumerate(root):
            yield from _flatten(v, f"{base}/{i}")
        return

    # primitives or others -> leaf
    yield base or "/", root

# ------------- public API -------------

def load_json(
    file_path: str,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> List[Dict[str, Any]]:
    """
    Load JSON and return flat chunks with generic metadata.

    Returns a list of dicts:
        {
          "text": "...",
          "metadata": {
            "section": "json",
            "title": "<last path segment or '/'>",
            "source": "<filename.json>",
            "source_id": "<json pointer path>",
            "path": "<same as source_id>"
          }
        }
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"JSON not found: {file_path}")

    with p.open("r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as e:
            raise ValueError(f"Failed to parse JSON {file_path}: {e}") from e

    source = p.name
    out: List[Dict[str, Any]] = []

    for path, val in _flatten(data):
        title = (path.split("/")[-1] or "/")
        section = "json"
        source_id = path
        
        # Build readable key context from path (e.g., "/education" -> "Education")
        # For nested paths like "/experience/0/company" -> "Experience > Company"
        key_parts = [p for p in path.split("/") if p and not p.isdigit()]
        if key_parts:
            key_context = " > ".join(p.replace("_", " ").title() for p in key_parts)
            key_prefix = f"{key_context}: "
        else:
            key_prefix = ""

        if isinstance(val, str):
            text = _normalize_text(val)
            if not text:
                continue
            # Prepend key context to make chunks searchable by key names
            text_with_context = f"{key_prefix}{text}"
            slices = _sentence_aware_chunks(text_with_context, chunk_size, chunk_overlap)
            for s in slices:
                out.append({
                    "text": s,
                    "metadata": {
                        "section": section,
                        "title": title,
                        "source": source,
                        "source_id": source_id,
                        "path": path,
                    },
                })
        elif isinstance(val, (int, float, bool)):
            # Include key context for primitive values too
            text_with_context = f"{key_prefix}{val}"
            out.append({
                "text": text_with_context,
                "metadata": {
                    "section": section,
                    "title": title,
                    "source": source,
                    "source_id": source_id,
                    "path": path,
                },
            })
        else:
            # null or unexpected leaf -> skip nulls, stringify others defensively
            if val is None:
                continue
            s = _normalize_text(json.dumps(val, ensure_ascii=False))
            if not s:
                continue
            text_with_context = f"{key_prefix}{s}"
            slices = _sentence_aware_chunks(text_with_context, chunk_size, chunk_overlap)
            for c in slices:
                out.append({
                    "text": c,
                    "metadata": {
                        "section": section,
                        "title": title,
                        "source": source,
                        "source_id": source_id,
                        "path": path,
                    },
                })

    return out
