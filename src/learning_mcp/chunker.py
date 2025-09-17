from typing import List

def chunk_text(text: str, size: int = 1200, overlap: int = 200) -> List[str]:
    if size <= 0:
        return [text]
    tokens = text.split()
    chunks = []
    i = 0
    while i < len(tokens):
        chunk = tokens[i:i+size]
        chunks.append(" ".join(chunk))
        i += max(1, size - overlap)
    return [c for c in chunks if c.strip()]
