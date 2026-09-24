"""Post history: what was published (for dedupe, idempotency and the `history` command)."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from app.db import models
from app.db.models import connect


@dataclass
class PostRecord:
    id: int
    created_at: str
    status: str
    topic: str
    text: str
    urn: str | None
    url: str | None
    source_urls: list[str]


def text_hash(text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode()).hexdigest()


class PostRepository:
    def __init__(self, path: Path | None = None):
        self.path = path or models.HISTORY_DB  # resolved at call time (tests redirect it)

    def add(
        self,
        *,
        status: str,
        topic: str,
        text: str,
        urn: str | None = None,
        url: str | None = None,
        source_urls: list[str] | None = None,
    ) -> int:
        with connect(self.path) as db:
            cur = db.execute(
                "INSERT INTO posts (status, topic, text, text_hash, urn, url, source_urls) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (status, topic, text, text_hash(text), urn, url, json.dumps(source_urls or [])),
            )
            return cur.lastrowid

    def find_published(self, text: str) -> PostRecord | None:
        """A real (non-dry-run) post with the same text, if any — prevents double posting."""
        with connect(self.path) as db:
            row = db.execute(
                "SELECT * FROM posts WHERE text_hash = ? AND status = 'published' "
                "ORDER BY id DESC LIMIT 1",
                (text_hash(text),),
            ).fetchone()
        return _record(row) if row else None

    def find_shared(self, text: str) -> PostRecord | None:
        with connect(self.path) as db:
            row = db.execute(
                "SELECT * FROM posts WHERE text_hash = ? AND status = 'shared' "
                "ORDER BY id DESC LIMIT 1",
                (text_hash(text),),
            ).fetchone()
        return _record(row) if row else None

    def recent_topics(self, limit: int = 20) -> list[str]:
        """Topics of recent real posts (published or shared), newest first — Scout dedupe."""
        with connect(self.path) as db:
            rows = db.execute(
                "SELECT topic FROM posts WHERE status IN ('published', 'shared') "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [r["topic"] for r in rows]

    def list(self, limit: int = 20, *, include_dry_runs: bool = True) -> list[PostRecord]:
        query = "SELECT * FROM posts"
        if not include_dry_runs:
            query += " WHERE status != 'dry_run'"
        with connect(self.path) as db:
            rows = db.execute(query + " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [_record(r) for r in rows]


def _record(row) -> PostRecord:
    return PostRecord(
        id=row["id"],
        created_at=row["created_at"],
        status=row["status"],
        topic=row["topic"],
        text=row["text"],
        urn=row["urn"],
        url=row["url"],
        source_urls=json.loads(row["source_urls"]),
    )
