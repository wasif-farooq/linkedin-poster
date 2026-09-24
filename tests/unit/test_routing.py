import pytest

from app.config import get_settings
from app.graph.routing import after_critic, dispatch, route_after_dispatch, route_after_manager

TOPIC = {"topic": "T"}
BRIEF = {"summary": "s"}
DRAFT = {"text": "d", "hashtags": []}
REVISE = {"verdict": "revise"}


@pytest.mark.parametrize(
    ("state", "expected_next", "expected_plan"),
    [
        ({"plan": ["topic_scout", "researcher"]}, "topic_scout", ["researcher"]),
        # missing prerequisites are inserted, recursively
        ({"plan": ["writer", "critic"]}, "topic_scout", ["researcher", "writer", "critic"]),
        ({"plan": ["writer"], "topic": TOPIC}, "researcher", ["writer"]),
        ({"plan": ["critic"], "topic": TOPIC, "research_brief": BRIEF}, "writer", ["critic"]),
        # a prerequisite already in the plan (wrong order) is moved to the front
        ({"plan": ["writer", "researcher"], "topic": TOPIC}, "researcher", ["writer"]),
        # an already-reviewed draft is not re-reviewed
        ({"plan": ["critic"], "draft": DRAFT, "critique": REVISE}, "manager", []),
        ({"plan": []}, "manager", []),
    ],
)
def test_dispatch(state, expected_next, expected_plan):
    out = dispatch(state)
    assert out["next"] == expected_next
    assert out["plan"] == expected_plan


def test_dispatch_step_limit(monkeypatch):
    monkeypatch.setattr(get_settings(), "max_steps_per_turn", 3)
    out = dispatch({"plan": ["topic_scout"], "step_count": 3})
    assert out["next"] == "manager" and out["plan"] == []
    assert "step limit" in out["last_error"]


def test_after_critic_queues_revision_until_cap(monkeypatch):
    monkeypatch.setattr(get_settings(), "max_revisions", 2)
    plan, note = after_critic({"plan": [], "revision_count": 0}, REVISE)
    assert plan == ["writer", "critic"] and "1/2" in note
    plan, note = after_critic({"plan": [], "revision_count": 2}, REVISE)
    assert plan == [] and "cap" in note
    plan, note = after_critic({"plan": ["researcher"]}, {"verdict": "pass"})
    assert plan == ["researcher"] and note is None


def test_after_critic_does_not_double_queue():
    plan, _ = after_critic({"plan": ["writer", "critic"], "revision_count": 0}, REVISE)
    assert plan == ["writer", "critic"]


def test_route_helpers():
    assert route_after_manager({"plan": ["writer"]}) == "dispatch"
    assert route_after_manager({"plan": []}) == "respond"
    assert route_after_dispatch({"next": "critic"}) == "critic"
    assert route_after_dispatch({}) == "manager"


# --- Phase 5 ---------------------------------------------------------------------------

REVIEWED = {"draft": DRAFT, "critique": {"verdict": "pass"}}


def test_publisher_requires_approval():
    out = dispatch({"plan": ["publisher"], **REVIEWED})
    assert out == {"next": "human_review", "plan": ["publisher"]}
    assert dispatch({"plan": ["publisher"], "approved": True, **REVIEWED})["next"] == "publisher"


def test_human_review_needs_a_draft():
    assert (
        dispatch({"plan": ["human_review"], "topic": TOPIC, "research_brief": BRIEF})["next"]
        == "writer"
    )


@pytest.mark.parametrize(
    ("activity", "extra", "expected"),
    [
        (["writer: wrote", "critic: pass"], {}, "human_review"),  # new reviewed draft -> human
        (["writer: wrote", "critic: pass", "human_review: APPROVED"], {}, "manager"),
        (["critic: pass"], {}, "manager"),  # nothing written this turn
        (["writer: wrote", "critic: pass"], {"approved": True}, "manager"),
        (["writer: wrote", "critic: FAILED"], {"critique": None}, "manager"),
    ],
)
def test_auto_review_at_end_of_plan(activity, extra, expected):
    state = {"plan": [], "activity": activity, **REVIEWED, **extra}
    assert dispatch(state)["next"] == expected


@pytest.mark.parametrize("raw", [0, "0", "", "none", None])
def test_manager_decision_treats_zero_candidate_as_unset(raw):
    """Regression: a model sent use_candidate_id=0 for 'none' and the plan was dropped."""
    from app.schemas.manager import ManagerDecision

    d = ManagerDecision(
        plan=["human_review"], use_candidate_id=raw, niche="", topic_override="none"
    )
    assert d.use_candidate_id is None and d.niche is None and d.topic_override is None
