import json

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.agents import topic_scout
from app.llm.structured import StructuredOutputError
from app.schemas.topic import Candidate

CANDIDATES = [
    Candidate(title="LangGraph 1.0 released", url="https://lg.dev/1", source="Blog"),
    Candidate(title="HN on LangGraph 1.0", url="https://hn/1", source="Hacker News", points=300),
    Candidate(title="Rust in the kernel", url="https://x/2", source="Blog"),
    Candidate(title="AGENTS.md support", url="https://x/3", source="Blog"),
]


def option(ids, topic, angle="An angle."):
    return {
        "candidate_ids": ids,
        "topic": topic,
        "angle": angle,
        "why_now": "This week.",
        "audience": "Engineers",
    }


def shortlist(*options):
    return json.dumps({"options": list(options)})


@pytest.fixture
def fake_llm(monkeypatch):
    prompts: list[str] = []

    def install(*responses):
        llm = FakeListChatModel(responses=list(responses))
        original = llm.invoke

        def spy(messages, *a, **kw):
            prompts.append("\n".join(m.content for m in messages))
            return original(messages, *a, **kw)

        object.__setattr__(llm, "invoke", spy)
        monkeypatch.setattr(topic_scout, "get_llm", lambda role: llm)
        return prompts

    return install


def test_choose_topics_ranks_and_uses_real_urls(fake_llm):
    fake_llm(
        shortlist(
            option([1, 2], "LangGraph hits 1.0"),
            option([3, 99], "Rust in the kernel"),
            option([4], "AGENTS.md"),
        )
    )
    options = topic_scout.choose_topics(CANDIDATES, niche="ai")
    assert [o.topic for o in options] == ["LangGraph hits 1.0", "Rust in the kernel", "AGENTS.md"]
    assert options[0].source_urls == ["https://lg.dev/1", "https://hn/1"]
    assert options[1].chosen_ids == [3]  # unknown id 99 dropped
    assert options[0].runner_up_ids == [3, 4]


def test_duplicate_story_and_unknown_only_options_are_dropped(fake_llm):
    fake_llm(
        shortlist(
            option([1], "LangGraph"), option([1, 2], "Same story again"), option([42], "Invented")
        )
    )
    assert [o.topic for o in topic_scout.choose_topics(CANDIDATES, niche="ai")] == [
        "LangGraph",
        "Same story again",
    ]
    # (option 2 keeps only its new id 2 — a different source for the same story is allowed once)


def test_retries_when_no_ids_are_valid(fake_llm):
    fake_llm(shortlist(option([42], "Invented")), shortlist(option([3], "Rust in the kernel")))
    assert topic_scout.choose_topic(CANDIDATES, niche="ai").topic == "Rust in the kernel"


def test_gives_up(fake_llm):
    fake_llm(shortlist(option([42], "x")), shortlist(option([43], "y")))
    with pytest.raises(StructuredOutputError):
        topic_scout.choose_topics(CANDIDATES, niche="ai")


def test_brief_contains_context():
    text = topic_scout._brief(CANDIDATES, "ai", "focus on OSS", ["Old topic"], ["Shown before"])
    assert "Niche: ai" in text and "focus on OSS" in text
    assert (
        "Old topic" in text
        and "Already suggested (the author wants different ones): Shown before" in text
    )
    assert "[2] HN on LangGraph 1.0" in text and "300 points" in text


def test_run_shortlists_by_default(fake_llm, monkeypatch):
    prompts = fake_llm(shortlist(option([1], "LangGraph"), option([3], "Rust")))
    monkeypatch.setattr(topic_scout, "collect_candidates", lambda cfg: CANDIDATES)
    out = topic_scout.run(
        {"niche": "ai engineering", "recent_topics": ["x"], "excluded_topics": ["Shown"]}
    )
    json.dumps(out)
    assert out["topic"] is None
    assert [o["topic"] for o in out["topic_options"]] == ["LangGraph", "Rust"]
    assert "Shown" in prompts[0]


def test_run_auto_topic_picks_the_best(fake_llm, monkeypatch):
    fake_llm(shortlist(option([1], "LangGraph"), option([3], "Rust")))
    monkeypatch.setattr(topic_scout, "collect_candidates", lambda cfg: CANDIDATES)
    out = topic_scout.run({"niche": "ai", "recent_topics": ["x"], "auto_topic": True})
    assert out["topic"]["topic"] == "LangGraph" and out["topic_options"] is None


def test_run_node_without_candidates(monkeypatch):
    monkeypatch.setattr(topic_scout, "collect_candidates", lambda cfg: [])
    with pytest.raises(topic_scout.NoCandidatesError):
        topic_scout.run({"niche": "ai"})
