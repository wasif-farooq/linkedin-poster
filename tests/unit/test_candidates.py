from app.schemas.topic import Candidate
from app.tools.sources.candidates import collect_candidates, rank_candidates


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


# --- freshness and heat -------------------------------------------------------------------

from datetime import UTC, datetime, timedelta  # noqa: E402

import httpx  # noqa: E402
import respx  # noqa: E402

from app.tools.sources import candidates, news  # noqa: E402
from app.tools.sources.niches import NicheConfig, SourceSettings  # noqa: E402


def ago(hours):
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def test_old_reposts_are_dropped():
    year = datetime.now(UTC).year
    items = [
        c("Why I stopped using ORMs (2019)", "https://ex.com/1"),
        c(f"A fresh take ({year})", "https://ex.com/2"),
    ]
    assert [i.url for i in rank_candidates(items, [])] == ["https://ex.com/2"]


def test_same_story_from_several_sources_is_merged_and_counted():
    items = [
        c("White House tells OpenAI and Anthropic to let US review new models", "https://a.com/1"),
        c(
            "OpenAI, Anthropic reportedly asked by White House to delay UK access",
            "https://b.com/2",
            source="Hacker News",
            points=250,
        ),
        c("Something else entirely about compilers today", "https://c.com/3"),
    ]
    ranked = rank_candidates(items, [])
    story = next(i for i in ranked if i.url == "https://a.com/1")
    assert story.also_in == ["Hacker News"] and story.points == 250  # HN heat carried over
    assert len(ranked) == 2


def test_news_hits_need_a_second_source():
    lone = c("Unknown blog covers a model launch in detail", "https://blog.example/x")
    covered = c("Gemini can now phone businesses for you", "https://verge.com/g")
    echo = c("Gemini can now phone businesses for you, Google says", "https://techspot.com/g")
    for item in (lone, echo):
        item.kind = "news"
    echo.source = "techspot.com"
    ranked = rank_candidates([covered, lone, echo], [])
    assert [i.url for i in ranked] == ["https://verge.com/g"]
    assert ranked[0].also_in == ["techspot.com"]  # the echo counts as coverage


def test_fresher_and_hotter_rank_higher_at_equal_relevance():
    items = [
        c("An LLM story from three days ago", "https://ex.com/old", published=ago(70)),
        c("An LLM story from this morning", "https://ex.com/new", published=ago(3)),
        c(
            "An LLM story everyone is discussing",
            "https://ex.com/hot",
            source="Hacker News",
            points=600,
            published=ago(20),
        ),
    ]
    assert [i.url for i in rank_candidates(items, ["LLM"])] == [
        "https://ex.com/hot",
        "https://ex.com/new",
        "https://ex.com/old",
    ]


def _niche(**settings):
    return NicheConfig("n", [], ["https://f"], ["q"], SourceSettings(**settings))


def test_window_is_widened_only_when_too_few_fresh_stories(monkeypatch):
    titles = [
        "Rust compiler speeds",
        "Postgres vacuum tuning",
        "Kafka outage lessons",
        "Deno funding",
    ]
    ages = [5, 30, 100, 150]
    pool = [
        c(t, f"https://ex.com/{i}", published=ago(h))
        for i, (t, h) in enumerate(zip(titles, ages, strict=True))
    ]
    monkeypatch.setattr(candidates.feeds, "fetch_feeds", lambda *a, **k: pool)
    monkeypatch.setattr(candidates.hackernews, "collect", lambda *a, **k: [])
    monkeypatch.setattr(candidates.news, "collect", lambda *a, **k: [])

    fresh = collect_candidates(_niche(max_age_days=3, min_candidates=2))
    assert sorted(i.url[-1] for i in fresh) == ["0", "1"]
    widened = collect_candidates(_niche(max_age_days=3, min_candidates=3))
    assert len(widened) == 4


def test_bing_links_are_decoded_to_the_article():
    link = (
        "http://www.bing.com/news/apiclick.aspx?ref=FexRss&aid=&tid=x"
        "&url=https%3a%2f%2fwww.techspot.com%2fnews%2f1.html&c=1"
    )
    assert news.article_url(link) == "https://www.techspot.com/news/1.html"
    assert news.article_url("http://www.bing.com/news/apiclick.aspx?url=javascript:x") is None
    assert news.article_url("https://ex.com/a") == "https://ex.com/a"


@respx.mock
def test_search_news_maps_items_to_real_urls_and_outlets():
    item = (
        "<item><title>Gemini phones businesses</title>"
        "<link>http://www.bing.com/news/apiclick.aspx?url=https%3a%2f%2fwww.techspot.com%2fa</link>"
        f"<pubDate>{datetime.now(UTC).strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate></item>"
    )
    route = respx.get(news.API).mock(
        return_value=httpx.Response(
            200, text=f"<rss><channel><title>Bing</title>{item}</channel></rss>"
        )
    )
    [hit] = news.search_news("Gemini")
    assert (hit.url, hit.source, hit.kind) == ("https://www.techspot.com/a", "techspot.com", "news")
    assert route.calls.last.request.url.params["qft"] == 'sortbydate="1" interval="8"'
