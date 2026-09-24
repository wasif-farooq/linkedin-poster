import json

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.agents import critic, writer
from app.agents.context import format_feedback
from app.config import get_settings
from app.schemas.post import Critique, Draft
from app.schemas.research import KeyPoint, ResearchBrief, Source

BRIEF = ResearchBrief(
    topic="Claude Code adds AGENTS.md",
    angle="Treat it as config",
    summary="Claude Code reads AGENTS.md.",
    key_points=[KeyPoint(point="Fallback when no CLAUDE.md", source_ids=[1])],
    sources=[Source(id=1, title="InfoWorld", url="https://iw.dev", origin="scout", content="...")],
)
BODY = "\n\n".join(
    [
        "Agent instructions are config now.",
        "Claude Code reads AGENTS.md as a fallback.",
        "Version it. Review it. Test it.",
        "What does your team do?",
    ]
)
DRAFT_JSON = json.dumps(
    {"text": BODY, "hashtags": ["#AI", "#ClaudeCode", "#DevTools"], "source_ids": [1, 9]}
)


def review_json(**scores):
    base = {"hook": 8, "insight": 8, "accuracy": 9, "clarity": 8, "tone": 8}
    return json.dumps(
        {"scores": base | scores, "issues": ["weak close"], "suggestions": ["cut the question"]}
    )


@pytest.fixture
def llm(monkeypatch):
    """Install a fake LLM for both agents; returns the list of prompts it received."""
    seen: list[str] = []

    def install(*responses):
        fake = FakeListChatModel(responses=list(responses))
        original = fake.invoke

        def spy(messages, *a, **kw):
            seen.append("\n".join(m.content for m in messages))
            return original(messages, *a, **kw)

        object.__setattr__(fake, "invoke", spy)
        monkeypatch.setattr(writer, "get_llm", lambda role: fake)
        monkeypatch.setattr(critic, "get_llm", lambda role: fake)
        return seen

    monkeypatch.setattr(get_settings(), "post_target_min_chars", 50)
    return install


def test_write_uses_voice_and_filters_source_ids(llm):
    prompts = llm(DRAFT_JSON)
    draft = writer.write(BRIEF)
    assert draft.source_ids == [1]  # 9 isn't a real source
    assert "Author voice" in prompts[0] and "CTO" in prompts[0]  # config/voice.md loaded
    assert "Fallback when no CLAUDE.md (sources: 1)" in prompts[0]


def test_revision_includes_previous_draft_and_feedback(llm):
    prompts = llm(DRAFT_JSON)
    previous = Draft(text="Old draft", hashtags=["#A"])
    writer.write(BRIEF, previous=previous, feedback=["Make the hook sharper"])
    assert "Old draft" in prompts[0] and "Make the hook sharper" in prompts[0]
    assert "revised post" in prompts[0]


@pytest.mark.parametrize(
    ("scores", "body", "verdict"),
    [
        ({}, BODY, "pass"),
        ({"hook": 6}, BODY, "revise"),  # below CRITIC_MIN_SCORE (7)
        ({}, "**Bold** " + BODY, "revise"),  # rule error overrides good scores
    ],
)
def test_critic_verdict_is_decided_in_code(llm, scores, body, verdict):
    prompts = llm(review_json(**scores))
    draft = Draft(text=body, hashtags=["#A", "#B", "#C"])
    result = critic.review(BRIEF, draft)
    assert result.verdict == verdict
    assert "Automatic rule check" in prompts[0]


def test_format_feedback_orders_human_first():
    c = Critique(
        scores={"hook": 5, "insight": 8, "accuracy": 9, "clarity": 8, "tone": 8},
        issues=["weak hook"],
        suggestions=["open with the number"],
        verdict="revise",
        rule_errors=["markdown"],
        rule_warnings=["too long"],
    )
    items = format_feedback(c, "make it shorter")
    assert items[0].startswith("From the author") and "make it shorter" in items[0]
    assert "Must fix: markdown" in items and "weak hook" in items
    assert "Suggestion: open with the number" in items and "Formatting: too long" in items


def test_writer_node_first_draft_and_revision(llm):
    llm(DRAFT_JSON, DRAFT_JSON)
    state = {"research_brief": BRIEF.model_dump()}
    first = writer.run(state)
    assert first["revision_count"] == 0 and first["critique"] is None

    revise = Critique(
        scores={"hook": 5, "insight": 8, "accuracy": 9, "clarity": 8, "tone": 8},
        verdict="revise",
        issues=["weak hook"],
    )
    second = writer.run(state | first | {"critique": revise.model_dump(), "revision_count": 0})
    assert second["revision_count"] == 1
    json.dumps(second)


def test_writer_node_ignores_passing_critique(llm):
    prompts = llm(DRAFT_JSON)
    passed = Critique(
        scores={"hook": 9, "insight": 9, "accuracy": 9, "clarity": 9, "tone": 9},
        verdict="pass",
        issues=["nitpick"],
    )
    writer.run(
        {
            "research_brief": BRIEF.model_dump(),
            "draft": Draft(text="Old", hashtags=[]).model_dump(),
            "critique": passed.model_dump(),
            "human_feedback": "shorter please",
        }
    )
    assert "shorter please" in prompts[0] and "nitpick" not in prompts[0]


def test_critic_node(llm):
    llm(review_json())
    out = critic.run({"research_brief": BRIEF.model_dump(), "draft": json.loads(DRAFT_JSON)})
    assert out["critique"]["verdict"] == "pass"
    json.dumps(out)


def test_nodes_require_inputs():
    with pytest.raises(ValueError):
        writer.run({})
    with pytest.raises(ValueError):
        critic.run({"draft": {"text": "x", "hashtags": []}})
