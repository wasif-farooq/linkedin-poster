import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.config import DATA_DIR

HISTORY_DB = DATA_DIR / "history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    status      TEXT    NOT NULL CHECK (status IN ('published', 'dry_run')),
    topic       TEXT    NOT NULL,
    text        TEXT    NOT NULL,
    text_hash   TEXT    NOT NULL,
    urn         TEXT,
    url         TEXT,
    source_urls TEXT    NOT NULL DEFAULT '[]'  -- JSON list
);
CREATE INDEX IF NOT EXISTS idx_posts_hash ON posts (text_hash, status);
"""


@contextmanager
def connect(path: Path = HISTORY_DB) -> Iterator[sqlite3.Connection]:
    """Open, ensure the schema, commit on success, always close."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()
