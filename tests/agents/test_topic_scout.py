import json

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.agents import topic_scout
from app.llm.structured import StructuredOutputError
from app.schemas.topic import Candidate

CANDIDATES = [
    Candidate(title="LangGraph 1.0 released", url="https://lg.dev/1", source="Blog"),
    Candidate(title="HN on LangGraph 1.0", url="https://hn/1", source="Hacker News", points=300),
    Candidate(title="Unrelated", url="https://x/2", source="Blog"),
]


def selection(**overrides):
    data = {
        "chosen_ids": [1, 2],
        "topic": "LangGraph hits 1.0",
        "angle": "Stable APIs change the build-vs-buy math for agents.",
        "why_now": "Released this week.",
        "audience": "AI engineers",
        "runner_up_ids": [3, 99, 1],
    }
    return json.dumps(data | overrides)


@pytest.fixture
def fake_llm(monkeypatch):
    def install(*responses):
        llm = FakeListChatModel(responses=list(responses))
        monkeypatch.setattr(topic_scout, "get_llm", lambda role: llm)
        return llm

    return install


def test_choose_topic_uses_real_urls_and_filters_ids(fake_llm):
    fake_llm(selection())
    choice = topic_scout.choose_topic(CANDIDATES, niche="ai")
    assert choice.chosen_ids == [1, 2]
    assert choice.source_urls == ["https://lg.dev/1", "https://hn/1"]
    assert choice.runner_up_ids == [3]  # 99 unknown, 1 already chosen


def test_choose_topic_retries_on_unknown_ids(fake_llm):
    fake_llm(selection(chosen_ids=[42]), selection(chosen_ids=[3]))
    choice = topic_scout.choose_topic(CANDIDATES, niche="ai")
    assert choice.chosen_ids == [3]


def test_choose_topic_gives_up(fake_llm):
    fake_llm(selection(chosen_ids=[42]), selection(chosen_ids=[43]))
    with pytest.raises(StructuredOutputError):
        topic_scout.choose_topic(CANDIDATES, niche="ai")


def test_brief_contains_context():
    text = topic_scout._brief(CANDIDATES, "ai", "focus on OSS", ["Old topic"])
    assert "Niche: ai" in text
    assert "focus on OSS" in text
    assert "Old topic" in text
    assert "[2] HN on LangGraph 1.0" in text and "300 points" in text


def test_run_node_returns_serializable_state(fake_llm, monkeypatch):
    fake_llm(selection())
    monkeypatch.setattr(topic_scout, "collect_candidates", lambda cfg: CANDIDATES)
    out = topic_scout.run({"niche": "ai engineering", "recent_topics": ["x"]})
    json.dumps(out)  # plain dicts only
    assert out["niche"] == "ai engineering"
    assert len(out["candidates"]) == 3
    assert out["topic"]["topic"] == "LangGraph hits 1.0"


def test_run_node_without_candidates(monkeypatch):
    monkeypatch.setattr(topic_scout, "collect_candidates", lambda cfg: [])
    with pytest.raises(topic_scout.NoCandidatesError):
        topic_scout.run({"niche": "ai"})
