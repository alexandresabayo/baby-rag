import re

PARA_SEP = re.compile(r"\n\s*\n")
SENT_SEP = re.compile(r"(?<=[.!?…])\s+")


def _windows(n: int, size: int, overlap: int) -> list[tuple[int, int]]:
    spans = []
    start = 0
    while start < n:
        end = min(start + size, n)
        spans.append((start, end))
        if end >= n:
            break
        start = end - overlap
    return spans


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[dict]:
    """Split on paragraphs, then sentences, then hard windows.

    Deterministic; never emits empty chunks; offsets index into the
    newline-normalized input (\\r\\n and \\r are normalized to \\n first).
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must satisfy 0 <= overlap < chunk_size")

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks: list[dict] = []

    def emit(unit: str, base: int) -> None:
        """Emit one paragraph-like unit starting at absolute offset `base`."""
        stripped = unit.strip("\n")
        if not stripped.strip():
            return
        lead = len(unit) - len(unit.lstrip("\n"))
        s = base + lead
        if len(stripped) <= chunk_size:
            chunks.append({
                "content": stripped,
                "start_char": s,
                "end_char": s + len(stripped),
            })
            return
        # Sentence-level packing within the unit.
        pieces: list[tuple[int, str]] = []  # (relative offset, sentence)
        last = 0
        for m in SENT_SEP.finditer(stripped):
            pieces.append((last, stripped[last:m.end()]))
            last = m.end()
        pieces.append((last, stripped[last:]))
        pieces = [(o, p) for o, p in pieces if p.strip()]

        buf_off = buf_len = 0
        cur_start = -1
        for off, piece in pieces:
            candidate = (cur_start, buf_len + (off - buf_off) + len(piece)) if cur_start >= 0 else None
            if cur_start >= 0 and candidate and candidate[1] > chunk_size:
                chunks.append({
                    "content": stripped[cur_start:cur_start + buf_len],
                    "start_char": s + cur_start,
                    "end_char": s + cur_start + buf_len,
                })
                cur_start = -1
            if cur_start < 0:
                if len(piece) <= chunk_size:
                    cur_start, buf_off, buf_len = off, off, len(piece)
                else:
                    for ws, we in _windows(len(piece), chunk_size, overlap):
                        chunks.append({
                            "content": piece[ws:we],
                            "start_char": s + off + ws,
                            "end_char": s + off + we,
                        })
            else:
                buf_len = off - buf_off + len(piece)
        if cur_start >= 0:
            content = stripped[cur_start:cur_start + buf_len]
            if len(content) <= chunk_size:
                chunks.append({
                    "content": content,
                    "start_char": s + cur_start,
                    "end_char": s + cur_start + buf_len,
                })
            else:
                for ws, we in _windows(buf_len, chunk_size, overlap):
                    chunks.append({
                        "content": stripped[cur_start + ws:cur_start + we],
                        "start_char": s + cur_start + ws,
                        "end_char": s + cur_start + we,
                    })

    last = 0
    for m in PARA_SEP.finditer(text):
        emit(text[last:m.start()], last)
        last = m.end()
    emit(text[last:], last)
    return chunks
