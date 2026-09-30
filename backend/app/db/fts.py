import sqlite3

from app.config import Settings


def create_fts(conn: sqlite3.Connection, tokenizer: str) -> None:
    conn.executescript(f"""
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
      content, content='chunks', content_rowid='id', tokenize='{tokenizer}'
    );
    CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
      INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
    END;
    CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
      INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.id, old.content);
    END;
    """)


def drop_fts(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    DROP TRIGGER IF EXISTS chunks_ai;
    DROP TRIGGER IF EXISTS chunks_ad;
    DROP TABLE IF EXISTS chunks_fts;
    """)


def rebuild_fts(conn: sqlite3.Connection, tokenizer: str) -> None:
    drop_fts(conn)
    create_fts(conn, tokenizer)
    rows = conn.execute("SELECT id, content FROM chunks").fetchall()
    conn.executemany(
        "INSERT INTO chunks_fts(rowid, content) VALUES (?, ?)",
        [(r["id"], r["content"]) for r in rows],
    )


def fts_integrity_ok(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "INSERT INTO chunks_fts(chunks_fts, rank) VALUES ('integrity-check', 1); "
    )
    return row is not None


def fts_query(conn: sqlite3.Connection, match: str, limit: int) -> list[int]:
    sql = (
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? "
        "ORDER BY bm25(chunks_fts) LIMIT ?"
    )
    return [r[0] for r in conn.execute(sql, (match, limit)).fetchall()]


def ensure_fts_tokenizer(conn: sqlite3.Connection, settings: Settings) -> None:
    """Store the tokenizer in meta; rebuild the FTS index if it changed."""
    from app.db.queries import get_meta, set_meta

    stored = get_meta(conn, "fts_tokenizer")
    if stored is None:
        set_meta(conn, "fts_tokenizer", settings.fts_tokenizer)
        create_fts(conn, settings.fts_tokenizer)
    elif stored != settings.fts_tokenizer:
        rebuild_fts(conn, settings.fts_tokenizer)
        set_meta(conn, "fts_tokenizer", settings.fts_tokenizer)
