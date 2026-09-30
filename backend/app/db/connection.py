import sqlite3
from pathlib import Path

from app.config import Settings

SCHEMA_VERSION = 1
SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")


def connect(settings: Settings) -> sqlite3.Connection:
    """Open a short-lived connection with the pragmas required by the spec."""
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None  # autocommit; transactions are explicit
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {version} is newer than the code "
            f"(supports {SCHEMA_VERSION}). Delete the database file and re-ingest, "
            "or upgrade the application."
        )
    conn.executescript(SCHEMA_SQL)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def fts5_available(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)")
        conn.execute("DROP TABLE _fts_probe")
        return True
    except sqlite3.OperationalError:
        return False
