"""Operational SQLite store (`data/app.db`) for data that isn't documents or audit events.

The vector store holds passages, `audit.db` holds the tamper-evident trail and
`analytics.db` holds usage history. This database holds the operational records
the application needs to look up quickly: the document registry today, and
matters, feedback and throttling later.

Connections are opened per call (as elsewhere in the codebase) and the database
runs in WAL mode so readers never block the writer. Schema changes go in
MIGRATIONS; `init_db()` applies any that are outstanding and is safe to call
repeatedly.
"""

import logging
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("APP_DB_PATH", "data/app.db")
BUSY_TIMEOUT_MS = 5000

# Applied in order; the index of the last applied statement is kept in
# PRAGMA user_version, so each entry must be append-only and never edited.
MIGRATIONS: List[str] = [
    """
    CREATE TABLE IF NOT EXISTS documents (
        document_id    TEXT PRIMARY KEY,
        filename       TEXT,
        source         TEXT,
        category       TEXT,
        document_type  TEXT,
        uploaded_by    TEXT,
        upload_date    TEXT,
        content_type   TEXT,
        file_size      INTEGER DEFAULT 0,
        page_count     INTEGER,
        word_count     INTEGER,
        chunk_count    INTEGER NOT NULL DEFAULT 0,
        ingest_channel TEXT,
        matter_id      TEXT,
        -- How this document's chunks are found in the vector store: "document_id"
        -- for anything ingested since that field existed, "source" for older chunks.
        lookup_field   TEXT NOT NULL DEFAULT 'document_id',
        created_at     TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_documents_upload_date ON documents(upload_date)",
    "CREATE INDEX IF NOT EXISTS idx_documents_matter ON documents(matter_id)",
    "CREATE INDEX IF NOT EXISTS idx_documents_uploader ON documents(uploaded_by)",
]

_init_lock = threading.Lock()
_initialised_for: Optional[str] = None


def db_path() -> str:
    """Resolved at call time: the tests chdir into a throwaway tree."""
    return DB_PATH


def connect() -> sqlite3.Connection:
    """Open a connection with WAL and row access by column name."""
    directory = os.path.dirname(db_path())
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(db_path(), timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return conn


def init_db(force: bool = False) -> int:
    """Apply outstanding migrations. Returns the resulting schema version."""
    global _initialised_for
    with _init_lock:
        path = db_path()
        if not force and _initialised_for == path:
            return len(MIGRATIONS)
        with connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            for index in range(version, len(MIGRATIONS)):
                conn.execute(MIGRATIONS[index])
                # PRAGMA doesn't accept bound parameters.
                conn.execute(f"PRAGMA user_version={index + 1}")
            if version < len(MIGRATIONS):
                logger.info(f"Applied {len(MIGRATIONS) - version} migration(s) to {path}")
        _initialised_for = path
        return len(MIGRATIONS)


def execute(sql: str, params: Sequence[Any] = ()) -> None:
    init_db()
    with connect() as conn:
        conn.execute(sql, params)


def executemany(sql: str, rows: Sequence[Sequence[Any]]) -> None:
    if not rows:
        return
    init_db()
    with connect() as conn:
        conn.executemany(sql, rows)


def query(sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def query_one(sql: str, params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
    rows = query(sql, params)
    return rows[0] if rows else None
