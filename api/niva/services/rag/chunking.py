"""Small chunks (~200–400 tokens) for free-text RAG."""

from __future__ import annotations

import re


def approx_tokens(text: str) -> int:
    # Rough English/Manglish estimate
    return max(1, len((text or "").split()))


def chunk_text(
    text: str,
    *,
    target_tokens: int = 280,
    max_tokens: int = 400,
    overlap_tokens: int = 40,
) -> list[str]:
    """
    Split into overlapping chunks in the 200–400 token band.
    Prefer paragraph / sentence boundaries.
    """
    raw = (text or "").strip()
    if not raw:
        return []
    if approx_tokens(raw) <= max_tokens:
        return [raw]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    if len(paragraphs) <= 1:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", raw) if s.strip()]
        units = sentences or [raw]
    else:
        units = paragraphs

    chunks: list[str] = []
    buf: list[str] = []
    buf_tokens = 0

    def flush():
        nonlocal buf, buf_tokens
        if buf:
            chunks.append(" ".join(buf).strip())
            # overlap
            if overlap_tokens > 0 and buf:
                keep: list[str] = []
                kept = 0
                for part in reversed(buf):
                    t = approx_tokens(part)
                    if kept + t > overlap_tokens and keep:
                        break
                    keep.insert(0, part)
                    kept += t
                buf = keep
                buf_tokens = sum(approx_tokens(p) for p in buf)
            else:
                buf = []
                buf_tokens = 0

    for unit in units:
        t = approx_tokens(unit)
        if t > max_tokens:
            # hard-split long unit by words
            words = unit.split()
            step = max(50, target_tokens - overlap_tokens)
            for i in range(0, len(words), step):
                piece = " ".join(words[i : i + target_tokens])
                if piece.strip():
                    chunks.append(piece.strip())
            continue
        if buf_tokens + t > max_tokens and buf:
            flush()
        buf.append(unit)
        buf_tokens += t
        if buf_tokens >= target_tokens:
            flush()
    if buf:
        chunks.append(" ".join(buf).strip())
    return [c for c in chunks if c]
