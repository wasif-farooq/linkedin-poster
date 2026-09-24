from app.schemas.topic import Candidate
from app.tools.sources.candidates import rank_candidates


def c(title, url, source="Blog", summary="", points=None, published=None):
    return Candidate(
        title=title, url=url, source=source, summary=summary, points=points, published=published
    )


def test_dedupes_by_url_and_title():
    items = [
        c("Post A", "https://www.ex.com/a/?utm_source=x"),
        c("Post A mirror", "https://ex.com/a"),  # same url
        c("post a!", "https://other.com/z"),  # same title
        c("Post B", "https://ex.com/b"),
    ]
    assert [i.title for i in rank_candidates(items, [])] == ["Post A", "Post B"]


def test_hn_self_posts_with_different_ids_are_kept():
    items = [
        c("Ask HN: one", "https://news.ycombinator.com/item?id=1", source="Hacker News"),
        c("Ask HN: two", "https://news.ycombinator.com/item?id=2", source="Hacker News"),
    ]
    assert len(rank_candidates(items, [])) == 2


def test_keyword_hits_rank_first_and_word_boundaries():
    items = [
        c("Gardening tips", "https://ex.com/1", points=900, source="Hacker News"),
        c("New LLM release", "https://ex.com/2", source="Hacker News"),
        c("Building a RAG pipeline with an LLM", "https://ex.com/3"),
        c("Drag and drop", "https://ex.com/4"),  # 'RAG' must not match inside 'Drag'
    ]
    ranked = rank_candidates(items, ["LLM", "RAG"])
    assert [i.url for i in ranked][:2] == ["https://ex.com/3", "https://ex.com/2"]
    hits = {i.url: i.keyword_hits for i in ranked}
    assert hits["https://ex.com/3"] == 2
    assert hits["https://ex.com/4"] == 0


def test_limit():
    items = [c(f"t{i}", f"https://ex.com/{i}") for i in range(10)]
    assert len(rank_candidates(items, [], limit=3)) == 3
