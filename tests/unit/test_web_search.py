import pytest

from app.config import get_settings
from app.llm.usage import SearchBudgetExceededError, tracker
from app.schemas.research import SearchResult
from app.tools.sources import web_search


class FakeProvider:
    name = "fake"

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def search(self, query, *, kind, max_results, timelimit):
        self.calls.append((query, kind, max_results, timelimit))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


HITS = [SearchResult(title="A", url="https://a.dev", snippet="about a")]


@pytest.fixture(autouse=True)
def fast_and_isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(web_search, "CACHE_DIR", tmp_path / "cache")
    settings = get_settings()
    monkeypatch.setattr(settings, "search_min_interval", 0)
    monkeypatch.setattr(settings, "search_backoff", 0)
    monkeypatch.setattr(settings, "search_retries", 2)
    tracker.reset(max_searches=10)
    yield
    tracker.reset(max_searches=None)


def test_search_passes_params_and_counts():
    provider = FakeProvider(HITS)
    assert (
        web_search.search("q", kind="news", max_results=3, timelimit="w", provider=provider) == HITS
    )
    assert provider.calls == [("q", "news", 3, "w")]
    assert tracker.snapshot().searches == 1


def test_repeat_query_is_served_from_cache():
    provider = FakeProvider(HITS)
    web_search.search("q", provider=provider)
    assert web_search.search("q", provider=provider) == HITS
    assert len(provider.calls) == 1
    snap = tracker.snapshot()
    assert (snap.searches, snap.search_cache_hits) == (1, 1)


def test_cache_expires(monkeypatch):
    provider = FakeProvider(HITS, HITS)
    web_search.search("q", provider=provider)
    monkeypatch.setattr(get_settings(), "search_cache_hours", 0)
    web_search.search("q", provider=provider)
    assert len(provider.calls) == 2


def test_retries_then_succeeds():
    provider = FakeProvider(RuntimeError("throttled"), HITS)
    assert web_search.search("q", provider=provider) == HITS
    assert len(provider.calls) == 2


def test_gives_up_with_search_error():
    provider = FakeProvider(*[RuntimeError("down")] * 3)
    with pytest.raises(web_search.SearchError):
        web_search.search("q", provider=provider)


def test_budget_blocks_live_search_but_not_cache():
    provider = FakeProvider(HITS)
    tracker.reset(max_searches=1)
    web_search.search("q1", provider=provider)
    web_search.search("q1", provider=provider)  # cached: free
    with pytest.raises(SearchBudgetExceededError):
        web_search.search("q2", provider=provider)
