# /src/learning_mcp/chunker.py
"""
Token-based chunker with overlap (word-splitting).
Purpose: Split long text into overlapping word chunks for embedding.

User question: "How do I chunk extracted PDF text with overlap?"

Example (PowerShell):
  docker compose exec api python /app/src/tools/run_snippet.py `
    --module learning_mcp.chunker `
    --call chunk_text `
    --kwargs '{"text":"one two three four five six seven eight nine ten", "size":4, "overlap":1}'
"""

from typing import List


def chunk_text(text: str, size: int = 1200, overlap: int = 200) -> List[str]:
    if size <= 0:
        return [text]
    tokens = text.split()
    if overlap >= size:
        overlap = max(0, size - 1)

    chunks: List[str] = []
    i = 0
    n = len(tokens)

    while i < n:
        j = min(i + size, n)
        chunks.append(" ".join(tokens[i:j]))
        if j == n:
            break
        i += max(1, size - overlap)

    return [c for c in chunks if c.strip()]
