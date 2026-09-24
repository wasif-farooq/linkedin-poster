from app.db.repository import PostRepository, text_hash


def test_add_find_and_list():
    repo = PostRepository()
    repo.add(status="dry_run", topic="Dry", text="Hello   world")
    assert repo.find_published("Hello world") is None  # dry runs don't count as published

    repo.add(
        status="published",
        topic="Real",
        text="Hello world",
        urn="urn:li:share:1",
        url="https://li/1",
        source_urls=["https://src"],
    )
    found = repo.find_published("Hello\nworld")  # whitespace-insensitive match
    assert found.urn == "urn:li:share:1" and found.source_urls == ["https://src"]

    assert [p.topic for p in repo.list()] == ["Real", "Dry"]
    assert [p.topic for p in repo.list(include_dry_runs=False)] == ["Real"]


def test_recent_topics_only_real_posts_newest_first():
    repo = PostRepository()
    repo.add(status="published", topic="First", text="a")
    repo.add(status="dry_run", topic="Ignored", text="b")
    repo.add(status="published", topic="Second", text="c")
    assert repo.recent_topics() == ["Second", "First"]


def test_text_hash_normalizes_whitespace():
    assert text_hash("a  b\n\nc") == text_hash("a b c")
