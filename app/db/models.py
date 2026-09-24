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
    status      TEXT    NOT NULL CHECK (status IN ('published', 'dry_run', 'shared')),
    topic       TEXT    NOT NULL,
    text        TEXT    NOT NULL,
    text_hash   TEXT    NOT NULL,
    urn         TEXT,
    url         TEXT,
    source_urls TEXT    NOT NULL DEFAULT '[]'  -- JSON list
);
CREATE INDEX IF NOT EXISTS idx_posts_hash ON posts (text_hash, status);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """v1 only allowed published/dry_run. SQLite can't alter a CHECK, so copy the table."""
    row = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'posts'").fetchone()
    if row and "'shared'" not in row[0]:
        conn.executescript(
            "ALTER TABLE posts RENAME TO posts_v1;"
            + SCHEMA.replace(
                "CREATE INDEX IF NOT EXISTS idx_posts_hash",
                "CREATE INDEX IF NOT EXISTS idx_posts_hash_v2",
            )
            + "INSERT INTO posts SELECT * FROM posts_v1; DROP TABLE posts_v1;"
        )


@contextmanager
def connect(path: Path = HISTORY_DB) -> Iterator[sqlite3.Connection]:
    """Open, ensure the schema, commit on success, always close."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        _migrate(conn)
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()
