import httpx
import respx

from app.tools.sources import hackernews

HITS = {
    "hits": [
        {
            "objectID": "1",
            "title": "Show HN: A thing",
            "url": "https://thing.dev",
            "points": 120,
            "num_comments": 40,
            "created_at": "2026-09-23T10:00:00Z",
        },
        {"objectID": "2", "title": "Ask HN: No url?", "url": None, "points": 50, "num_comments": 9},
        {"objectID": "3", "title": None},
    ]
}


@respx.mock
def test_front_page_maps_hits():
    route = respx.get(hackernews.API).mock(return_value=httpx.Response(200, json=HITS))
    items = hackernews.front_page()
    assert route.calls.last.request.url.params["tags"] == "front_page"
    assert [i.title for i in items] == ["Show HN: A thing", "Ask HN: No url?"]
    assert items[0].points == 120 and items[0].comments == 40
    assert items[1].url == "https://news.ycombinator.com/item?id=2"


@respx.mock
def test_search_stories_builds_filters():
    route = respx.get(hackernews.API).mock(return_value=httpx.Response(200, json={"hits": []}))
    hackernews.search_stories("LangGraph", max_age_days=3, min_points=10)
    params = route.calls.last.request.url.params
    assert params["query"] == "LangGraph"
    assert params["tags"] == "story"
    assert "points>10" in params["numericFilters"]


@respx.mock
def test_errors_return_empty():
    respx.get(hackernews.API).mock(return_value=httpx.Response(503))
    assert hackernews.front_page() == []


@respx.mock
def test_collect_runs_front_page_and_keywords():
    route = respx.get(hackernews.API).mock(return_value=httpx.Response(200, json=HITS))
    items = hackernews.collect(["a", "b"])
    assert route.call_count == 3
    assert len(items) == 6
