"""Web API tests: real graph + checkpointer, fake agents and a scripted Manager."""

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.checkpoint.memory import InMemorySaver

from app.agents import critic, manager, researcher, topic_scout, writer
from app.api.server import create_app
from app.config import get_settings
from app.db.repository import PostRepository
from app.llm.usage import LLMBudgetExceededError

FULL_PLAN = ["topic_scout", "researcher", "writer", "critic"]


def decision(**kw):
    return json.dumps({"plan": [], "reply": ""} | kw)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        topic_scout,
        "run",
        lambda s: {"candidates": [], "topic": {"topic": "Agents as config", "source_urls": []}},
    )
    monkeypatch.setattr(
        researcher,
        "run",
        lambda s: {
            "research_brief": {
                "topic": "t",
                "summary": "s",
                "key_points": [{"point": "p"}],
                "sources": [],
            }
        },
    )
    monkeypatch.setattr(
        writer,
        "run",
        lambda s: {
            "draft": {"text": "Draft body", "hashtags": ["#AI"]},
            "critique": None,
            "human_feedback": None,
            "revision_count": 0,
        },
    )
    scores = dict.fromkeys(["hook", "insight", "accuracy", "clarity", "tone"], 9)
    monkeypatch.setattr(
        critic,
        "run",
        lambda s: {
            "critique": {
                "scores": scores,
                "issues": [],
                "suggestions": [],
                "verdict": "pass",
                "rule_errors": [],
                "rule_warnings": [],
            }
        },
    )
    with TestClient(create_app(InMemorySaver())) as c:
        yield c


@pytest.fixture
def script(monkeypatch):
    def install(*decisions):
        llm = FakeListChatModel(responses=list(decisions))
        monkeypatch.setattr(manager, "get_llm", lambda role: llm)

    return install


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True, "busy": False}


def test_create_thread_with_niche(client):
    thread_id = client.post("/api/threads", json={"niche": "software engineering"}).json()["id"]
    snap = client.get(f"/api/threads/{thread_id}").json()
    assert snap["niche"] == "software engineering" and snap["status"] == "new"


def test_message_streams_progress_then_pauses_for_review(client, script):
    script(decision(plan=FULL_PLAN, reply="On it"), decision(reply="Ready for review."))
    resp = client.post("/api/threads/t1/messages", json={"text": "write a post"})
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(resp.text)

    kinds = [e for e, _ in events]
    assert kinds[0] == "start" and kinds[-1] == "done" and "interrupt" in kinds
    plan = next(d for e, d in events if e == "step" and d["node"] == "manager")
    assert plan["plan"] == FULL_PLAN and plan["reply"] == "On it"
    lines = [line for e, d in events if e == "step" for line in d.get("activity", [])]
    assert lines == [
        "topic_scout: picked 'Agents as config'",
        "researcher: brief with 1 key points from 0 sources",
        "writer: wrote the draft (~10 chars)",
        "critic: pass (lowest: hook 9)",
    ]  # each line exactly once
    review = next(d for e, d in events if e == "interrupt")
    assert review["type"] == "review" and review["post"] == "Draft body\n\n#AI"

    done = events[-1][1]
    assert done["thread"]["status"] == "needs_review"
    assert done["thread"]["draft"]["chars"] == len("Draft body\n\n#AI")
    assert done["thread"]["pending"]["type"] == "review"
    assert {"calls", "input_tokens", "output_tokens", "searches"} <= done["usage"].keys()


def test_resume_approve_and_report(client, script):
    script(decision(plan=FULL_PLAN), decision(reply="Approved."))
    client.post("/api/threads/t1/messages", json={"text": "write a post"})
    events = parse_sse(
        client.post("/api/threads/t1/resume", json={"answer": {"action": "approve"}}).text
    )
    lines = [line for e, d in events if e == "step" for line in d.get("activity", [])]
    assert lines == ["human_review: APPROVED"]  # earlier lines are not re-sent on resume
    thread = events[-1][1]["thread"]
    assert thread["status"] == "approved" and thread["approved"] is True
    assert thread["messages"][-1] == {"role": "assistant", "content": "Approved."}

    assert (
        client.post("/api/threads/t1/resume", json={"answer": {"action": "approve"}}).status_code
        == 409
    )


def test_threads_list_shows_status(client, script):
    script(decision(plan=FULL_PLAN), decision(reply="ok"))
    client.post("/api/threads/t1/messages", json={"text": "write a post"})
    threads = client.get("/api/threads").json()
    assert threads == [{"id": "t1", "title": "Agents as config", "status": "needs_review"}]


def test_dry_run_publish_and_flag_is_restored(client, script):
    script(decision(plan=["publisher"]), decision(reply="Dry run recorded."))
    client.post("/api/threads/t1/messages", json={"text": "post something", "dry_run": True})
    events = parse_sse(
        client.post(
            "/api/threads/t1/resume", json={"answer": {"action": "approve"}, "dry_run": True}
        ).text
    )
    assert events[-1][1]["thread"]["publish_result"]["status"] == "dry_run"
    assert get_settings().publish_dry_run is False
    assert [p["status"] for p in client.get("/api/history").json()] == ["dry_run"]


def test_run_errors_become_error_events(client, monkeypatch):
    def broke(state):
        raise LLMBudgetExceededError("LLM call budget of 30 per run reached")

    monkeypatch.setattr(manager, "run", broke)
    events = parse_sse(client.post("/api/threads/t1/messages", json={"text": "hi"}).text)
    assert ("error", {"message": "LLM call budget of 30 per run reached"}) in events
    assert events[-1][0] == "done"
    assert client.get("/api/health").json()["busy"] is False  # lock released


def test_busy_runner_rejects_new_runs(client):
    lock = client.app.state.runner.lock
    lock.acquire()
    try:
        resp = client.post("/api/threads/t1/messages", json={"text": "hi"})
        assert resp.status_code == 409
    finally:
        lock.release()


def test_validation(client):
    assert client.get("/api/threads/bad id!").status_code in (404, 422)
    assert client.post("/api/threads/t1/messages", json={"text": ""}).status_code == 422


def test_voice_roundtrip(client, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "voice_path", tmp_path / "voice.md")
    assert client.get("/api/voice").json() == {"text": ""}
    assert client.put("/api/voice", json={"text": "Direct. No hype."}).status_code == 200
    assert client.get("/api/voice").json() == {"text": "Direct. No hype."}
    assert client.put("/api/voice", json={"text": "x" * 20_000}).status_code == 422


def test_settings_and_linkedin_status(client):
    settings = client.get("/api/settings").json()
    assert settings["default_model"] and "max_llm_calls_per_run" in settings["limits"]
    li = client.get("/api/linkedin").json()
    assert li["connected"] is False and "auth" in li["error"]


def test_history_lists_posts(client):
    PostRepository().add(
        status="published", topic="T", text="x", urn="urn:li:share:1", url="https://li/1"
    )
    assert client.get("/api/history?include_dry_runs=false").json()[0]["url"] == "https://li/1"
