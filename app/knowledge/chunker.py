from __future__ import annotations

def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        end = min(n, i + chunk_size)
        chunk = text[i:end].strip()
        if chunk:
            chunks.append(chunk)
        i = end - overlap
        if i < 0:
            i = 0
        if i >= n:
            break
    return chunks
