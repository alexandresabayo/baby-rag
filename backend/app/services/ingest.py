import asyncio
import hashlib
import logging
import os
import time
from pathlib import Path

from app.config import Settings
from app.db import queries
from app.db.connection import connect, init_schema
from app.db.fts import ensure_fts_tokenizer
from app.services.chunking import chunk_text

logger = logging.getLogger("babyrag.ingest")


def read_text_file(path: Path) -> str:
    """UTF-8 (BOM tolerated), falling back to cp1252 then latin-1 with a warning."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, ValueError):
            if enc == "latin-1":
                raise
            logger.warning("%s is not valid UTF-8; decoded as %s", path.name, enc)
            continue
    raise UnicodeDecodeError  # unreachable


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def scan_corpus(settings: Settings) -> list[Path]:
    root = Path(settings.corpus_dir)
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".txt")


def rel_posix(settings: Settings, path: Path) -> str:
    return path.relative_to(settings.corpus_dir).as_posix()


class IngestJob:
    def __init__(self):
        self.state = "idle"  # idle | running | done | failed
        self.total = 0
        self.done = 0
        self.failed = 0
        self.chunks_written = 0
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.error: str | None = None

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "total": self.total,
            "done": self.done,
            "failed": self.failed,
            "chunks_written": self.chunks_written,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": (
                round(self.finished_at - self.started_at, 3)
                if self.started_at and self.finished_at else None
            ),
            "error": self.error,
        }


_current_job: IngestJob | None = None


def get_job() -> IngestJob | None:
    return _current_job


def is_running() -> bool:
    return _current_job is not None and _current_job.state == "running"


async def run_ingest(settings: Settings, store, embedding_provider, force: bool = False) -> IngestJob:
    """Full incremental ingest. Embedding happens before the write transaction."""
    global _current_job
    job = IngestJob()
    job.state = "running"
    job.started_at = time.time()
    _current_job = job

    lock_path = Path(settings.database_path).with_suffix(".ingest.lock")
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        try:
            import fcntl
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, OSError):
            lock_fd = None  # non-blocking lock unavailable; proceed single-process

        await asyncio.to_thread(_ingest_sync, settings, store, embedding_provider, force, job)
        job.state = "done"
    except Exception as exc:
        job.state = "failed"
        job.error = str(exc)
        logger.exception("ingest failed")
        raise
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        job.finished_at = time.time()
    return job


def _ingest_sync(settings: Settings, store, embedding_provider, force: bool, job: IngestJob) -> None:
    conn = connect(settings)
    try:
        init_schema(conn)
        ensure_fts_tokenizer(conn, settings)

        files = scan_corpus(settings)
        job.total = len(files)

        existing = {r["path"]: r for r in queries.list_documents(conn)}
        seen = set()

        for path in files:
            rel = rel_posix(settings, path)
            seen.add(rel)
            try:
                _ingest_one(conn, settings, store, embedding_provider, path, rel,
                            existing.get(rel), force, job)
            except Exception as exc:
                job.failed += 1
                logger.exception("failed to index %s", rel)
                conn.execute("BEGIN IMMEDIATE")
                try:
                    queries.insert_document(
                        conn, rel, existing[rel]["content_hash"] if rel in existing else "",
                        existing[rel]["n_chars"] if rel in existing else 0, 0, "failed", str(exc),
                    )
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
            finally:
                job.done += 1

        # Delete documents whose file vanished (SQLite is authoritative; cascade removes chunks).
        removed_ids: list[tuple[int, list[int]]] = []
        conn.execute("BEGIN IMMEDIATE")
        try:
            for rel, row in existing.items():
                if rel not in seen:
                    ids = queries.old_chunk_ids(conn, row["id"])
                    queries.delete_document_by_id(conn, row["id"])
                    removed_ids.append((row["id"], ids))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        for _doc_id, ids in removed_ids:
            store.delete([str(i) for i in ids])

        _check_embedding_meta(conn, settings, store)
    finally:
        conn.close()


def _ingest_one(conn, settings: Settings, store, embedding_provider,
                path: Path, rel: str, row, force: bool, job: IngestJob) -> None:
    raw = path.read_bytes()
    content_hash = sha256_bytes(raw)
    if not force and row is not None and row["content_hash"] == content_hash:
        return  # unchanged, skip

    text = read_text_file(path)
    chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        raise ValueError("file has no non-empty text")

    # Step 1: embed BEFORE opening the write transaction.
    embeddings = embedding_provider.embed_sync([c["content"] for c in chunks]) \
        if hasattr(embedding_provider, "embed_sync") else None
    if embeddings is None:
        embeddings = asyncio.run(embedding_provider.embed([c["content"] for c in chunks]))

    old_ids: list[int] = []
    written_ids: list[str] = []
    conn.execute("BEGIN IMMEDIATE")
    try:
        doc_id = queries.insert_document(
            conn, rel, content_hash, len(text), len(chunks), "indexed", None
        )
        if row is not None:
            old_ids = queries.old_chunk_ids(conn, row["id"])
            queries.delete_chunks(conn, row["id"])
        new_ids = []
        for i, c in enumerate(chunks):
            new_ids.append(queries.insert_chunk(
                conn, doc_id, i, c["content"], c["start_char"], c["end_char"]
            ))
        written_ids = [str(i) for i in new_ids]
        metadatas = [
            {"document_id": doc_id, "path": rel, "chunk_index": i}
            for i in range(len(chunks))
        ]
        store.upsert(written_ids, embeddings, metadatas)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        store.delete([str(i) for i in written_ids])
        raise
    # Step 5: after successful commit, remove old vectors.
    store.delete([str(i) for i in old_ids])
    job.chunks_written += len(chunks)


def _check_embedding_meta(conn, settings: Settings, store) -> None:
    queries.set_meta(conn, "embedding_model", settings.embedding_model)
    queries.set_meta(conn, "embedding_dim", str(settings.embedding_dim))


def check_embedding_guard(conn, settings: Settings) -> tuple[bool, str]:
    """Return (ok, message). Called at startup / retrieval."""
    model = queries.get_meta(conn, "embedding_model")
    dim = queries.get_meta(conn, "embedding_dim")
    if model is None or dim is None:
        return True, ""
    if model != settings.embedding_model or int(dim) != settings.embedding_dim:
        return False, (
            f"Embedding model changed (stored: {model}/{dim}, configured: "
            f"{settings.embedding_model}/{settings.embedding_dim}); "
            "run `make reindex`."
        )
    return True, ""
