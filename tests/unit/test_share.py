from urllib.parse import parse_qs, urlsplit

from app.db import models
from app.db.repository import PostRepository
from app.tools.linkedin.share import article_share_url, compose_url, share_text

POST = "Hook line.\n\nBody (with parens) & more.\n\n#AI #Agents"


def test_share_text_puts_article_before_hashtags():
    assert share_text(POST, "https://src.dev/a") == (
        "Hook line.\n\nBody (with parens) & more.\n\nhttps://src.dev/a\n\n#AI #Agents"
    )
    assert share_text("No tags here", "https://src.dev/a") == "No tags here\n\nhttps://src.dev/a"
    assert share_text(POST) == POST


def test_compose_url_round_trips_text_exactly():
    url = compose_url(POST)
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://www.linkedin.com/feed/"
    params = parse_qs(parts.query)
    assert params["shareActive"] == ["true"]
    assert params["text"] == [POST]  # newlines, parens, & and # survive encoding
    assert "+" not in parts.query  # spaces as %20 (LinkedIn shows a literal "+" otherwise)


def test_article_share_url():
    assert article_share_url("https://src.dev/a?b=1") == (
        "https://www.linkedin.com/sharing/share-offsite/?url=https%3A%2F%2Fsrc.dev%2Fa%3Fb%3D1"
    )


def test_history_migrates_v1_schema_to_allow_shared(tmp_path, monkeypatch):
    import sqlite3

    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:  # the v1 table: CHECK without 'shared'
        conn.executescript(
            models.SCHEMA.replace(", 'shared'", "")
            + "INSERT INTO posts (status, topic, text, text_hash) VALUES ('published', 'Old', 't', 'h');"
        )
    repo = PostRepository(db)
    repo.add(status="shared", topic="New", text="x")
    assert [p.topic for p in repo.list()] == ["New", "Old"]
    assert repo.recent_topics() == ["New", "Old"]  # shared counts for Scout dedupe
