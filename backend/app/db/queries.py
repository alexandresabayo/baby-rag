import json
import sqlite3
from datetime import UTC, datetime


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---- meta ----

def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


# ---- documents ----

def list_documents(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, path, content_hash, n_chars, n_chunks, status, error, indexed_at "
        "FROM documents ORDER BY path"
    ).fetchall()


def get_document_by_path(conn: sqlite3.Connection, path: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, path, content_hash, n_chars, n_chunks, status, error, indexed_at "
        "FROM documents WHERE path = ?", (path,)
    ).fetchone()


def get_document(conn: sqlite3.Connection, doc_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, path, content_hash, n_chars, n_chunks, status, error, indexed_at "
        "FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()


# ---- chunks ----

def insert_document(conn: sqlite3.Connection, path: str, content_hash: str,
                    n_chars: int, n_chunks: int, status: str, error: str | None) -> int:
    conn.execute(
        "INSERT INTO documents(path, content_hash, n_chars, n_chunks, status, error, indexed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET content_hash=excluded.content_hash, "
        "n_chars=excluded.n_chars, n_chunks=excluded.n_chunks, status=excluded.status, "
        "error=excluded.error, indexed_at=excluded.indexed_at",
        (path, content_hash, n_chars, n_chunks, status, error, _now()),
    )
    row = conn.execute("SELECT id FROM documents WHERE path = ?", (path,)).fetchone()
    return row[0]


def old_chunk_ids(conn: sqlite3.Connection, document_id: int) -> list[int]:
    return [r[0] for r in conn.execute(
        "SELECT id FROM chunks WHERE document_id = ?", (document_id,)
    ).fetchall()]


def delete_chunks(conn: sqlite3.Connection, document_id: int) -> None:
    conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))


def insert_chunk(conn: sqlite3.Connection, document_id: int, chunk_index: int,
                 content: str, start_char: int, end_char: int) -> int:
    cur = conn.execute(
        "INSERT INTO chunks(document_id, chunk_index, content, start_char, end_char) "
        "VALUES (?, ?, ?, ?, ?)",
        (document_id, chunk_index, content, start_char, end_char),
    )
    return cur.lastrowid


def get_chunk(conn: sqlite3.Connection, chunk_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT c.id, c.document_id, c.chunk_index, c.content, c.start_char, c.end_char, "
        "d.path FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.id = ?",
        (chunk_id,),
    ).fetchone()


def get_chunks_by_ids(conn: sqlite3.Connection, ids: list[int]) -> list[sqlite3.Row]:
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    return conn.execute(
        "SELECT c.id, c.document_id, c.chunk_index, c.content, c.start_char, c.end_char, "
        "d.path FROM chunks c JOIN documents d ON d.id = c.document_id "
        f"WHERE c.id IN ({marks})",
        ids,
    ).fetchall()


def count_chunks(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]


def all_chunk_ids(conn: sqlite3.Connection) -> list[int]:
    return [r[0] for r in conn.execute("SELECT id FROM chunks").fetchall()]


def delete_document_by_id(conn: sqlite3.Connection, document_id: int) -> None:
    conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))


def chunks_for_document(conn: sqlite3.Connection, document_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, chunk_index, content, start_char, end_char FROM chunks "
        "WHERE document_id = ? ORDER BY chunk_index",
        (document_id,),
    ).fetchall()


# ---- conversations ----

def create_conversation(conn: sqlite3.Connection, conv_id: str, title: str) -> None:
    conn.execute(
        "INSERT INTO conversations(id, title, created_at) VALUES (?, ?, ?)",
        (conv_id, title, _now()),
    )


def list_conversations(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, title, created_at FROM conversations ORDER BY created_at DESC"
    ).fetchall()


def get_conversation(conn: sqlite3.Connection, conv_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, title, created_at FROM conversations WHERE id = ?", (conv_id,)
    ).fetchone()


def delete_conversation(conn: sqlite3.Connection, conv_id: str) -> None:
    conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))


def add_message(conn: sqlite3.Connection, conversation_id: str, role: str,
                content: str, sources: list | None) -> int:
    cur = conn.execute(
        "INSERT INTO messages(conversation_id, role, content, sources, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (conversation_id, role, content, json.dumps(sources) if sources else None, _now()),
    )
    return cur.lastrowid


def list_messages(conn: sqlite3.Connection, conversation_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, conversation_id, role, content, sources, created_at FROM messages "
        "WHERE conversation_id = ? ORDER BY id",
        (conversation_id,),
    ).fetchall()


def last_messages(conn: sqlite3.Connection, conversation_id: str, n: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, role, content FROM messages WHERE conversation_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (conversation_id, n),
    ).fetchall()[::-1]


def count_messages(conn: sqlite3.Connection, conversation_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (conversation_id,)
    ).fetchone()[0]
