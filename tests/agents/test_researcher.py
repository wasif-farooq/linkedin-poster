import json

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.agents import researcher
from app.llm.usage import tracker
from app.schemas.research import Article, SearchResult
from app.tools.sources import web_search

SEED = Article(url="https://seed.dev/a", title="Seed article", text="Seed body " * 30)
PLAN = json.dumps(
    {
        "queries": [
            {"query": "q one", "kind": "news"},
            {"query": "Q One ", "kind": "web"},
            {"query": "q two", "kind": "web"},
        ]
    }
)
BRIEF = json.dumps(
    {
        "summary": "Something happened.",
        "key_points": [
            {"point": "Seed says X [1][2]", "source_ids": [1, 99]},
            {"point": "Search says Y", "source_ids": [2]},
        ],
        "stats": [
            {"fact": "42% faster [3]", "source_ids": [3]},
            {"fact": "Uncited claim", "source_ids": []},
            {"fact": "Bad cite", "source_ids": [77]},
        ],
        "counterpoints": [{"point": "But Z", "source_ids": [4]}],
    }
)


@pytest.fixture
def wired(monkeypatch):
    """Fake LLM, articles and search; records which queries ran."""
    state = {"queries": [], "fetched": []}

    def install(*llm_responses, search_results=None, fail_queries=()):
        monkeypatch.setattr(
            researcher, "get_llm", lambda role: FakeListChatModel(responses=list(llm_responses))
        )

        def fake_fetch(urls, max_chars=3000):
            state["fetched"].append(list(urls))
            return {
                u: Article(url=u, title=f"Page {u}", text="Page body " * 30)
                for u in urls
                if u == SEED.url or u.endswith("/full")
            }

        def fake_search(query, *, kind, timelimit):
            state["queries"].append((query, kind, timelimit))
            if query in fail_queries:
                raise web_search.SearchError("down")
            return (search_results or {}).get(query, [])

        monkeypatch.setattr(researcher, "fetch_articles", fake_fetch)
        monkeypatch.setattr(researcher.web_search, "search", fake_search)
        return state

    tracker.reset(max_searches=None)
    return install


RESULTS = {
    "q one": [
        SearchResult(title="Full page", url="https://news.dev/full", snippet="s1"),
        SearchResult(title="Dup of seed", url="https://seed.dev/a", snippet="dup"),
    ],
    "q two": [
        SearchResult(title="Snippet only", url="https://docs.dev/snip", snippet="s2"),
        SearchResult(title="Critic", url="https://critic.dev/full", snippet="s3"),
    ],
}


def test_research_end_to_end_validates_citations(wired):
    state = wired(PLAN, BRIEF, search_results=RESULTS)
    brief = researcher.research("Topic", angle="An angle", seed_urls=[SEED.url, SEED.url])

    # duplicate queries collapsed; news queries limited to the last month
    assert state["queries"] == [("q one", "news", "m"), ("q two", "web", None)]
    # sources: seed first, then interleaved search hits, seed duplicate skipped
    assert brief.queries == ["q one", "q two"]
    kp1, kp2 = brief.key_points
    assert kp1.point == "Seed says X" and kp1.source_ids == [1]  # inline cites stripped, 99 dropped
    assert [s.fact for s in brief.stats] == ["42% faster"]  # uncited / bad-cite stats dropped
    assert brief.counterpoints[0].source_ids == [4]
    assert [s.id for s in brief.sources] == [1, 2, 3, 4]
    by_id = {s.id: s for s in brief.sources}
    assert by_id[1].origin == "scout" and by_id[1].full_text
    assert by_id[2].url == "https://news.dev/full" and by_id[2].full_text
    assert by_id[3].url == "https://docs.dev/snip" and not by_id[3].full_text
    assert by_id[4].url == "https://critic.dev/full"


def test_failed_query_is_skipped(wired):
    state = wired(PLAN, BRIEF, search_results=RESULTS, fail_queries={"q one"})
    brief = researcher.research("Topic", seed_urls=[SEED.url])
    assert len(state["queries"]) == 2
    assert all("news.dev" not in s.url for s in brief.sources)


def test_no_search_budget_skips_planning(wired):
    wired(BRIEF)  # only one LLM response: the brief
    tracker.reset(max_searches=0)
    try:
        brief = researcher.research("Topic", seed_urls=[SEED.url])
    finally:
        tracker.reset(max_searches=None)
    assert brief.queries == []
    assert [s.origin for s in brief.sources] == ["scout"]


def test_no_sources_raises(wired):
    wired(PLAN, search_results={})
    with pytest.raises(researcher.NoSourcesError):
        researcher.research("Topic")


def test_run_node_accepts_topic_dict(wired):
    wired(PLAN, BRIEF, search_results=RESULTS)
    out = researcher.run(
        {"topic": {"topic": "T", "angle": "A", "source_urls": [SEED.url]}, "instructions": "x"}
    )
    json.dumps(out)
    assert out["research_brief"]["topic"] == "T"
    assert out["research_brief"]["angle"] == "A"


def test_run_node_requires_topic():
    with pytest.raises(ValueError):
        researcher.run({})
