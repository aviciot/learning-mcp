# /app/src/learning_mcp/page_ranges.py
"""
Parse include/exclude page specs (e.g., "1-20,22,40-50") and compute final pages.

Purpose:
- Let pdf_loader read ONLY selected pages (limit load at source).
- Supports strings like "1-3,5,10-12" or iterables of ints/strings.

Example (user question):
Q: "Given include='1-5,10' and exclude='3-4', total_pages=12, which pages load?"
A: compute_pages("1-5,10", "3-4", 12) -> [1, 2, 5, 10]
"""

from typing import Iterable, List, Optional, Union

Spec = Optional[Union[str, Iterable[Union[int, str]]]]


def parse_page_ranges(spec: Spec) -> List[int]:
    """Expand a page spec into a sorted, unique list of positive ints."""
    if spec is None:
        return []

    parts: List[str]
    if isinstance(spec, str):
        parts = [p.strip() for p in spec.split(",")]
    else:
        parts = []
        for item in spec:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                parts.append(s)

    out = set()
    for part in parts:
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a.strip()), int(b.strip())
            if start <= 0 or end <= 0 or end < start:
                raise ValueError(f"Invalid range '{part}'")
            out.update(range(start, end + 1))
        else:
            n = int(part)
            if n <= 0:
                raise ValueError(f"Invalid page '{part}'")
            out.add(n)
    return sorted(out)


def compute_pages(
    include_spec: Spec,
    exclude_spec: Spec,
    total_pages: Optional[int] = None,
) -> List[int]:
    """
    Compute final pages to process.

    Precedence:
      - If include_spec provided → base = parse(include_spec)
      - Else → base = 1..total_pages (requires total_pages)
      - Then remove any pages in exclude_spec
    """
    include = parse_page_ranges(include_spec)
    exclude = set(parse_page_ranges(exclude_spec))

    if include:
        base = include
    else:
        if total_pages is None:
            raise ValueError("total_pages required when include_spec is not provided")
        base = list(range(1, total_pages + 1))

    return [p for p in base if p not in exclude]
