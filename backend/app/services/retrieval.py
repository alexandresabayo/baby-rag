import re
import sqlite3
from collections import defaultdict

from app.db import fts as fts_db
from app.db import queries


def build_fts_query(text: str) -> str:
    """Sanitize raw user text into a safe FTS5 MATCH query.

    Extracts Unicode word tokens, wraps each in double quotes, joins with OR.
    Returns "" when no tokens remain (full-text search is then skipped).
    """
    tokens = re.findall(r"\w+", text, re.UNICODE)
    seen: list[str] = []
    for t in tokens:
        if t and t not in seen:
            seen.append(t)
    return " OR ".join(f'"{t}"' for t in seen)


def fuse_rrf(rankings: list[list[int]], rrf_k: int, top_k: int) -> list[dict]:
    """Reciprocal Rank Fusion: score = sum 1/(rrf_k + rank)."""
    scores: dict[int, float] = defaultdict(float)
    found_by: dict[int, set[str]] = defaultdict(set)
    for name, ranking in zip(("vector", "fts"), rankings, strict=False):
        for rank, chunk_id in enumerate(ranking):
            scores[chunk_id] += 1.0 / (rrf_k + rank)
            found_by[chunk_id].add(name)
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [
        {"chunk_id": cid, "score": score, "retrievers": sorted(found_by[cid])}
        for cid, score in ordered[:top_k]
    ]


async def retrieve(settings, conn: sqlite3.Connection, store,
                   embedding_provider, query: str, top_k: int | None = None) -> list[dict]:
    k = top_k or settings.top_k
    candidates = settings.candidate_k

    # 1-2. Vector search.
    embedding = await embedding_provider.embed([query])
    vector_ids = [int(i) for i in store.query(embedding[0], candidates)]

    fts_ids: list[int] = []
    if settings.hybrid:
        match = build_fts_query(query)
        if match:
            fts_ids = fts_db.fts_query(conn, match, candidates)

    fused = fuse_rrf([vector_ids, fts_ids], settings.rrf_k, candidates)
    fused = fused[:k]

    # Drop ids with no SQLite row (interrupted runs must not surface phantoms).
    rows = queries.get_chunks_by_ids(conn, [f["chunk_id"] for f in fused])
    by_id = {r["id"]: r for r in rows}
    results = []
    for f in fused:
        row = by_id.get(f["chunk_id"])
        if row is None:
            continue
        results.append({
            "chunk_id": row["id"],
            "document_id": row["document_id"],
            "path": row["path"],
            "chunk_index": row["chunk_index"],
            "text": row["content"],
            "start_char": row["start_char"],
            "end_char": row["end_char"],
            "score": f["score"],
            "retrievers": f["retrievers"],
        })
    return results
