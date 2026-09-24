"""Full graph runs with a scripted Manager LLM and fake workers (no network)."""

import json

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agents import critic, manager, researcher, topic_scout, writer
from app.config import get_settings
from app.graph.builder import build_graph
from app.graph.state import new_turn

CONFIG = {"configurable": {"thread_id": "t1"}}


def decision(**kw):
    return json.dumps({"plan": [], "reply": ""} | kw)


def critique(verdict):
    score = 9 if verdict == "pass" else 5
    return {
        "scores": dict.fromkeys(["hook", "insight", "accuracy", "clarity", "tone"], score),
        "issues": [],
        "suggestions": [],
        "verdict": verdict,
        "rule_errors": [],
        "rule_warnings": [],
    }


@pytest.fixture
def world(monkeypatch):
    """Fake workers that record calls; the Manager gets scripted decisions."""
    calls: list[str] = []
    verdicts: list[str] = []

    def scout(state):
        calls.append("topic_scout")
        return {
            "candidates": [{"title": "Alt topic", "url": "https://alt.dev"}],
            "topic": {"topic": "Agents as config", "source_urls": []},
        }

    def research(state):
        calls.append("researcher")
        return {
            "research_brief": {
                "topic": "x",
                "summary": "s",
                "key_points": [{"point": "p"}],
                "sources": [],
            }
        }

    def write(state):
        calls.append(f"writer(feedback={state.get('human_feedback')})")
        n = (state.get("revision_count") or 0) + 1 if state.get("draft") else 0
        return {
            "draft": {"text": f"draft v{len(calls)}", "hashtags": []},
            "critique": None,
            "human_feedback": None,
            "revision_count": n,
        }

    def review(state):
        calls.append("critic")
        return {"critique": critique(verdicts.pop(0) if verdicts else "pass")}

    monkeypatch.setattr(topic_scout, "run", scout)
    monkeypatch.setattr(researcher, "run", research)
    monkeypatch.setattr(writer, "run", write)
    monkeypatch.setattr(critic, "run", review)
    monkeypatch.setattr(get_settings(), "max_revisions", 1)

    def script(*decisions):
        llm = FakeListChatModel(responses=list(decisions))  # one instance: responses advance
        monkeypatch.setattr(manager, "get_llm", lambda role: llm)

    graph = build_graph(InMemorySaver())

    def say(text, *reviews):
        """Send a chat message; answer each review pause with the next of `reviews`."""
        graph.invoke(new_turn(HumanMessage(content=text)), CONFIG)
        answers = list(reviews)
        while graph.get_state(CONFIG).interrupts and answers:
            graph.invoke(Command(resume=answers.pop(0)), CONFIG)
        return graph.get_state(CONFIG).values

    def pending():
        interrupts = graph.get_state(CONFIG).interrupts
        return interrupts[0].value if interrupts else None

    def resume(answer):
        graph.invoke(Command(resume=answer), CONFIG)
        return graph.get_state(CONFIG).values

    return {
        "calls": calls,
        "verdicts": verdicts,
        "script": script,
        "say": say,
        "pending": pending,
        "resume": resume,
    }


APPROVE = {"action": "approve"}


def test_full_post_then_edit(world):
    world["script"](
        decision(plan=["topic_scout", "researcher", "writer", "critic"], reply="On it"),
        decision(reply="Draft ready: 'Agents as config'. Want changes?"),
    )
    state = world["say"]("find a topic and write a post", APPROVE)
    assert world["calls"] == ["topic_scout", "researcher", "writer(feedback=None)", "critic"]
    assert state["messages"][-1].content == "Draft ready: 'Agents as config'. Want changes?"
    assert state["critique"]["verdict"] == "pass"
    assert state["manager_calls"] == 2
    assert any("critic: pass" in a for a in state["activity"])

    # Turn 2: an edit only re-runs writer + critic, with the user's feedback.
    world["calls"].clear()
    world["script"](
        decision(plan=["writer", "critic"], feedback="make it shorter"),
        decision(reply="Shorter now."),
    )
    state = world["say"]("make it shorter", APPROVE)
    assert world["calls"] == ["writer(feedback=make it shorter)", "critic"]
    assert state["human_feedback"] is None
    assert [m.content for m in state["messages"]][-2:] == ["make it shorter", "Shorter now."]


def test_critic_revise_loop_is_capped(world):
    world["verdicts"].extend(["revise", "revise"])
    world["script"](
        decision(plan=["topic_scout", "researcher", "writer", "critic"]), decision(reply="ok")
    )
    state = world["say"]("write a post", APPROVE)
    assert world["calls"] == [
        "topic_scout",
        "researcher",
        "writer(feedback=None)",
        "critic",
        "writer(feedback=None)",
        "critic",  # one auto-revision (MAX_REVISIONS=1), then stop
    ]
    assert any("cap" in a for a in state["activity"])


def test_question_needs_no_workers(world):
    world["script"](decision(reply="No topic yet — want me to find one?"))
    state = world["say"]("what's the topic?")
    assert world["calls"] == []
    assert state["manager_calls"] == 1


def test_worker_failure_is_reported_not_raised(world, monkeypatch):
    def broken(state):
        raise RuntimeError("feeds are down")

    monkeypatch.setattr(topic_scout, "run", broken)
    seen = {}
    original = manager.summarize_state

    def spy(state):
        seen["summary"] = original(state)
        return seen["summary"]

    monkeypatch.setattr(manager, "summarize_state", spy)
    world["script"](
        decision(plan=["topic_scout", "researcher"]), decision(reply="Sources are down.")
    )
    state = world["say"]("find a topic")
    assert "topic_scout failed: feeds are down" in seen["summary"]
    assert world["calls"] == []  # researcher never ran
    assert state["messages"][-1].content == "Sources are down."


def test_use_candidate_and_topic_override(world):
    world["script"](decision(plan=["topic_scout"]), decision(reply="found"))
    world["say"]("find a topic")
    world["script"](decision(plan=["researcher"], use_candidate_id=1), decision(reply="switched"))
    state = world["say"]("use #1")
    assert state["topic"]["topic"] == "Alt topic"
    assert state["topic"]["source_urls"] == ["https://alt.dev"]

    world["script"](decision(topic_override="Rust in the kernel"), decision(reply="ok"))
    state = world["say"]("write about Rust in the kernel instead")
    assert state["topic"] == "Rust in the kernel"
    assert state["research_brief"] is None  # downstream cleared on topic change


def test_report_back_cannot_replan(world):
    """Regression: the model re-planned "make it shorter" after it was done, looping."""
    world["script"](decision(plan=["writer", "critic"]), decision(reply="Draft ready."))
    world["say"]("write a post", APPROVE)
    world["calls"].clear()

    world["script"](
        decision(plan=["writer", "critic"], feedback="make it shorter"),
        decision(plan=["writer", "critic"], feedback="make it shorter", reply="Done, shorter."),
    )
    state = world["say"]("make it shorter", APPROVE)
    assert world["calls"] == ["writer(feedback=make it shorter)", "critic"]  # exactly one pass
    assert state["manager_calls"] == 2
    assert state["messages"][-1].content == "Done, shorter."


def test_report_back_without_reply_uses_fallback(world):
    world["script"](decision(plan=["topic_scout"]), decision(plan=["topic_scout"]))
    state = world["say"]("find a topic")
    assert world["calls"] == ["topic_scout"]
    assert state["messages"][-1].content.startswith("Current topic: Agents as config")


def test_manager_call_cap(world, monkeypatch):
    monkeypatch.setattr(manager, "MAX_MANAGER_CALLS_PER_TURN", 1)
    world["script"](decision(plan=["topic_scout"]))
    state = world["say"]("find a topic")
    assert state["manager_calls"] == 2  # second consult answered without the LLM
    assert state["messages"][-1].content.startswith("Current topic: Agents as config")


# --- Phase 5: human review ------------------------------------------------------------

FULL_PLAN = ["topic_scout", "researcher", "writer", "critic"]


def test_new_draft_pauses_for_review_before_manager_reports(world):
    world["script"](decision(plan=FULL_PLAN), decision(reply="Approved and ready."))
    state = world["say"]("write a post")  # no answer given: graph stays paused
    payload = world["pending"]()
    assert payload["type"] == "review" and payload["post"].startswith("draft v")
    assert payload["critic_verdict"] == "pass" and payload["can_approve"]
    assert state["manager_calls"] == 1  # the Manager hasn't reported yet
    assert not state.get("approved")

    state = world["resume"](APPROVE)  # e.g. after `linkedin-poster resume --thread ...`
    assert state["approved"] is True
    assert state["messages"][-1].content == "Approved and ready."


def test_approve(world):
    world["script"](decision(plan=FULL_PLAN), decision(reply="Approved and ready."))
    state = world["say"]("write a post", APPROVE)
    assert state["approved"] is True
    assert state["final_post"].startswith("draft v")
    assert "human_review: APPROVED" in state["activity"]
    assert state["messages"][-1].content == "Approved and ready."
    assert world["pending"]() is None


def test_edit_replaces_draft_and_approves(world):
    world["script"](decision(plan=FULL_PLAN), decision(reply="ok"))
    edited = "My own version of the post.\n\n#AI #Agents #Config"
    state = world["say"]("write a post", {"action": "edit", "text": edited})
    assert state["approved"] is True
    assert state["draft"]["text"] == "My own version of the post."
    assert state["draft"]["hashtags"] == ["#AI", "#Agents", "#Config"]
    assert state["final_post"] == edited


def test_edit_over_limit_goes_back_to_review(world):
    world["script"](decision(plan=FULL_PLAN), decision(reply="ok"))
    too_long = "word " * 700
    world["say"]("write a post", {"action": "edit", "text": too_long})
    payload = world["pending"]()  # asked again, and approve is disabled
    assert payload is not None and not payload["can_approve"]
    assert any("3000" in e for e in payload["rule_errors"])

    state = world["resume"](APPROVE)  # approving the over-limit version is refused...
    assert not state.get("approved")
    assert "approval blocked" in state["activity"][-1]
    assert world["pending"]() is not None  # ...and it's still waiting for a fix

    state = world["resume"]({"action": "edit", "text": "Short fix.\n\n#A #B #C"})
    assert state["approved"] is True


def test_revise_runs_writer_critic_then_reviews_again(world):
    world["script"](decision(plan=FULL_PLAN), decision(reply="ok"))
    state = world["say"]("write a post", {"action": "revise", "text": "less formal"}, APPROVE)
    assert world["calls"] == [
        "topic_scout",
        "researcher",
        "writer(feedback=None)",
        "critic",
        "writer(feedback=less formal)",
        "critic",
    ]
    assert state["approved"] is True


def test_reject_drops_draft_but_keeps_research(world):
    world["script"](decision(plan=FULL_PLAN), decision(reply="Rejected. New angle?"))
    state = world["say"]("write a post", {"action": "reject"})
    assert state["draft"] is None and not state["approved"]
    assert state["research_brief"] is not None
    assert state["messages"][-1].content == "Rejected. New angle?"


def test_new_draft_clears_previous_approval(world):
    world["script"](decision(plan=FULL_PLAN), decision(reply="ok"))
    world["say"]("write a post", APPROVE)
    world["script"](decision(plan=["writer", "critic"], feedback="shorter"), decision(reply="ok"))
    state = world["say"]("shorter")  # paused at review of the new draft
    assert world["pending"]() is not None
    assert state["approved"] is False and state["final_post"] is None


def test_message_during_pending_review_starts_fresh_turn(world):
    world["script"](decision(plan=FULL_PLAN), decision(reply="unused"))
    world["say"]("write a post")
    assert world["pending"]() is not None
    world["script"](decision(reply="The topic is 'Agents as config'."))
    state = world["say"]("wait, what's the topic?")
    assert state["messages"][-1].content == "The topic is 'Agents as config'."
    assert state["draft"] is not None and not state.get("approved")  # draft kept, not approved


def test_fallback_reply_after_approval_is_readable(world):
    """Regression: an empty report-back reply showed a raw activity dump."""
    world["script"](decision(plan=FULL_PLAN), decision(reply=""))
    state = world["say"]("write a post", APPROVE)
    assert state["messages"][-1].content.startswith("Your post is approved (")


# --- Phase 6: publishing ----------------------------------------------------------------

import time as _time  # noqa: E402

from app.agents import publisher  # noqa: E402
from app.db.repository import PostRepository  # noqa: E402
from app.tools.linkedin.client import LinkedInAuthError  # noqa: E402
from app.tools.linkedin.oauth import LinkedInToken  # noqa: E402


@pytest.fixture
def linkedin(monkeypatch):
    """Fake LinkedIn: records posts instead of calling the API."""
    posted: list[tuple[str, str]] = []

    class FakeClient:
        def __init__(self, token, *, version):
            assert token == "tok"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def create_post(self, author, text):
            posted.append((author, text))
            return f"urn:li:share:{len(posted)}"

    monkeypatch.setattr(publisher, "LinkedInClient", FakeClient)
    monkeypatch.setattr(
        publisher,
        "load_token",
        lambda: LinkedInToken("tok", _time.time() + 30 * 86400, "m1", "Wasif"),
    )
    return posted


CONFIRM = {"confirm": True}


def test_post_it_after_approval(world, linkedin):
    world["script"](decision(plan=FULL_PLAN), decision(reply="Approved."))
    world["say"]("write a post", APPROVE)
    world["script"](decision(plan=["publisher"]), decision(reply="Posted!"))
    world["say"]("post it")
    payload = world["pending"]()
    assert payload["type"] == "publish_confirm" and payload["account"] == "Wasif"
    assert linkedin == []  # nothing posted before the yes

    state = world["resume"](CONFIRM)
    assert linkedin == [("urn:li:person:m1", state["final_post"])]
    assert state["publish_result"]["status"] == "published"
    assert state["post_url"] == "https://www.linkedin.com/feed/update/urn:li:share:1/"
    assert PostRepository().recent_topics() == ["Agents as config"]  # feeds Scout dedupe


def test_post_it_before_approval_forces_review_first(world, linkedin):
    world["script"](decision(plan=["publisher"]), decision(reply="ok"))
    world["say"]("write and post something", APPROVE, CONFIRM)
    assert world["calls"][:4] == ["topic_scout", "researcher", "writer(feedback=None)", "critic"]
    assert len(linkedin) == 1


def test_rejecting_in_review_never_posts(world, linkedin):
    world["script"](decision(plan=["publisher"]), decision(reply="ok"))
    state = world["say"]("post something", {"action": "reject"})
    assert linkedin == [] and state["draft"] is None


def test_saying_no_cancels(world, linkedin):
    world["script"](decision(plan=["publisher"]), decision(reply="Cancelled."))
    state = world["say"]("post something", APPROVE, {"confirm": False})
    assert linkedin == []
    assert state["publish_result"]["status"] == "cancelled"


def test_same_text_is_never_posted_twice(world, linkedin):
    world["script"](decision(plan=["publisher"]), decision(reply="ok"))
    world["say"]("post something", APPROVE, CONFIRM)
    world["script"](decision(plan=["publisher"]), decision(reply="ok"))
    state = world["say"]("post it again")  # same approved text
    assert len(linkedin) == 1
    assert state["publish_result"]["status"] == "already_published"
    assert world["pending"]() is None  # no confirmation needed: nothing will be posted


def test_dry_run_records_without_posting(world, linkedin, monkeypatch):
    monkeypatch.setattr(get_settings(), "publish_dry_run", True)
    world["script"](decision(plan=["publisher"]), decision(reply=""))
    state = world["say"]("post something", APPROVE)
    assert linkedin == []
    assert state["publish_result"]["status"] == "dry_run"
    assert [p.status for p in PostRepository().list()] == ["dry_run"]
    assert state["messages"][-1].content.startswith("Dry run")


def test_not_connected_is_explained(world, monkeypatch):
    def no_token():
        raise LinkedInAuthError("Not connected to LinkedIn yet. Run `linkedin-poster auth`.")

    monkeypatch.setattr(publisher, "load_token", no_token)
    world["script"](decision(plan=["publisher"]), decision(reply=""))
    state = world["say"]("post something", APPROVE)
    assert "linkedin-poster auth" in state["messages"][-1].content  # readable fallback


def test_new_draft_after_publishing_resets_publish_state(world, linkedin):
    world["script"](decision(plan=["publisher"]), decision(reply="ok"))
    world["say"]("post something", APPROVE, CONFIRM)
    world["script"](
        decision(plan=["writer", "critic"], feedback="new version"), decision(reply="ok")
    )
    state = world["say"]("write a new version")
    assert state["post_urn"] is None and state["publish_result"] is None and not state["approved"]


def test_publisher_node_refuses_unapproved_state():
    with pytest.raises(publisher.NotApprovedError):
        publisher.run({"final_post": "x", "approved": False})


def test_counters_reset_even_when_client_sends_only_messages(world):
    """Regression: Studio/API clients send just the message; counters must reset in-graph."""
    from app.graph.builder import build_graph

    graph = build_graph(InMemorySaver())
    cfg = {"configurable": {"thread_id": "studio"}}
    for i in range(3):
        world["script"](decision(reply=f"answer {i}"))
        graph.invoke({"messages": [HumanMessage(content=f"question {i}")]}, cfg)
        state = graph.get_state(cfg).values
        assert state["manager_calls"] == 1  # would be 2, 3 without the in-graph reset
        assert state["messages"][-1].content == f"answer {i}"
