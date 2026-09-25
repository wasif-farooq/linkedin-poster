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


def test_dry_run_publish_and_flag_is_restored(client, script, monkeypatch):
    monkeypatch.setattr(get_settings(), "publish_mode", "api")
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


# --- deployment: web OAuth callback + serving the built frontend -----------------------

import httpx  # noqa: E402
import respx  # noqa: E402

from app.api import server as server_module  # noqa: E402
from app.tools.linkedin import oauth  # noqa: E402


@pytest.fixture
def web_oauth(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "linkedin_client_id", "cid")
    monkeypatch.setattr(s, "linkedin_client_secret", "csecret")
    monkeypatch.setattr(
        s, "linkedin_redirect_uri", "https://linkedin.example.net/api/linkedin/callback"
    )


def _state_from(url: str) -> str:
    from urllib.parse import parse_qs, urlsplit

    return parse_qs(urlsplit(url).query)["state"][0]


@respx.mock
def test_web_oauth_round_trip(client, web_oauth):
    respx.post(oauth.TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 5184000})
    )
    respx.get("https://api.linkedin.com/v2/userinfo").mock(
        return_value=httpx.Response(200, json={"sub": "m1", "name": "Wasif"})
    )
    started = client.post("/api/linkedin/connect").json()
    assert started["authorize_url"].startswith("https://www.linkedin.com/oauth/v2/authorization?")
    state = _state_from(started["authorize_url"])

    resp = client.get(f"/api/linkedin/callback?code=abc&state={state}", follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/settings?linkedin=connected"
    assert client.get("/api/linkedin").json()["name"] == "Wasif"

    # a state works once
    again = client.get(f"/api/linkedin/callback?code=abc&state={state}", follow_redirects=False)
    assert again.headers["location"].startswith("/settings?linkedin=error")


def test_web_oauth_rejects_forged_state_and_linkedin_errors(client, web_oauth):
    client.post("/api/linkedin/connect")
    forged = client.get("/api/linkedin/callback?code=abc&state=forged", follow_redirects=False)
    assert forged.headers["location"].startswith("/settings?linkedin=error")
    denied = client.get(
        "/api/linkedin/callback?error=user_cancelled_authorize&error_description=The+user+cancelled",
        follow_redirects=False,
    )
    assert denied.headers["location"] == "/settings?linkedin=error&reason=The%20user%20cancelled"


def test_connect_without_app_credentials_explains(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "linkedin_client_id", "")
    resp = client.post("/api/linkedin/connect")
    assert resp.status_code == 400 and "LINKEDIN_CLIENT_ID" in resp.json()["detail"]


def test_serves_built_frontend_with_spa_fallback(monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Poster</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("nope")
    monkeypatch.setattr(get_settings(), "frontend_dist", dist)

    with TestClient(server_module.create_app(InMemorySaver())) as c:
        assert "Poster" in c.get("/").text
        assert "Poster" in c.get("/chat/abc123/review").text  # client-side route
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/favicon.svg").text == "<svg/>"
        assert "nope" not in c.get("/..%2Fsecret.txt").text  # no escaping dist/
        assert c.get("/api/does-not-exist").status_code == 404
        assert c.get("/api/health").json()["ok"] is True


# --- share links (default publish mode) ------------------------------------------------


def _approved_thread(client, script, monkeypatch):
    monkeypatch.setattr(
        topic_scout,
        "run",
        lambda s: {
            "candidates": [],
            "topic": {"topic": "Agents as config", "source_urls": ["https://src.dev/a"]},
        },
    )
    script(decision(plan=FULL_PLAN), decision(reply="Approved."))
    client.post("/api/threads/t1/messages", json={"text": "write a post"})
    client.post("/api/threads/t1/resume", json={"answer": {"action": "approve"}})


def test_mark_shared_records_history_and_status(client, script, monkeypatch):
    _approved_thread(client, script, monkeypatch)
    snap = client.post("/api/threads/t1/shared", json={"article_url": "https://src.dev/a"}).json()
    assert snap["status"] == "shared"
    assert "https%3A%2F%2Fsrc.dev%2Fa" in snap["publish_result"]["url"]
    client.post("/api/threads/t1/shared", json={})  # sharing again doesn't duplicate history
    history = client.get("/api/history").json()
    assert [(p["status"], p["topic"]) for p in history] == [("shared", "Agents as config")]
    assert [t["status"] for t in client.get("/api/threads").json()] == ["shared"]


def test_mark_shared_guards(client, script, monkeypatch):
    assert client.post("/api/threads/t1/shared", json={}).status_code == 409  # nothing approved
    _approved_thread(client, script, monkeypatch)
    bad = client.post("/api/threads/t1/shared", json={"article_url": "https://evil.example/x"})
    assert bad.status_code == 422  # only the post's own sources


def test_settings_reports_publish_mode(client):
    assert client.get("/api/settings").json()["publish_mode"] == "share"


def test_resume_rejects_answers_that_dont_fit_the_question(client, script):
    script(decision(plan=FULL_PLAN), decision(reply="ok"))
    client.post("/api/threads/t1/messages", json={"text": "write a post", "auto_topic": True})
    # pending: the draft review
    assert client.post("/api/threads/t1/resume", json={"answer": {"choice": 1}}).status_code == 422
    assert (
        client.post("/api/threads/t1/resume", json={"answer": {"action": "revise"}}).status_code
        == 422
    )
    assert (
        client.post("/api/threads/t1/resume", json={"answer": {"action": "approve"}}).status_code
        == 200
    )


# --- images -------------------------------------------------------------------------------

from app.agents import illustrator  # noqa: E402
from app.schemas.image import PostImage  # noqa: E402
from app.tools.images.generate import ImageGenerationError  # noqa: E402


@pytest.fixture
def fake_illustrate(monkeypatch):
    from app import config

    calls: list[dict] = []

    def illustrate(draft, *, topic="", direction="", previous=None):
        calls.append({"topic": topic, "direction": direction, "previous": previous})
        name = f"{len(calls):032x}.png"
        config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        (config.IMAGES_DIR / name).write_bytes(b"\x89PNG")
        return PostImage(
            prompt="p", alt_text="alt", file=name, provider="fake", direction=direction
        )

    monkeypatch.setattr(illustrator, "illustrate", illustrate)
    return calls


def test_generate_image_serve_it_and_remove_it(client, script, monkeypatch, fake_illustrate):
    _approved_thread(client, script, monkeypatch)
    snap = client.post("/api/threads/t1/image", json={"direction": "dark"}).json()
    assert snap["image"]["url"] == f"/api/images/{1:032x}.png" and snap["approved"]
    assert fake_illustrate[0]["topic"] == "Agents as config"
    assert fake_illustrate[0]["direction"] == "dark"

    served = client.get(snap["image"]["url"])
    assert served.status_code == 200 and served.content == b"\x89PNG"
    assert served.headers["content-type"] == "image/png"

    again = client.post("/api/threads/t1/image", json={}).json()
    assert again["image"]["file"] != snap["image"]["file"]
    assert fake_illustrate[1]["previous"].file == snap["image"]["file"]  # "make it different"

    assert client.delete("/api/threads/t1/image").json()["image"] is None


def test_generate_image_guards(client, script, fake_illustrate):
    assert client.post("/api/threads/t1/image", json={}).status_code == 409  # no draft
    script(decision(plan=FULL_PLAN), decision(reply="ok"))
    client.post("/api/threads/t1/messages", json={"text": "write a post", "auto_topic": True})
    busy = client.post("/api/threads/t1/image", json={})  # paused on the review question
    assert busy.status_code == 409 and "pending question" in busy.json()["detail"]
    assert client.get("/api/threads/t1").json()["status"] == "needs_review"  # untouched
    assert fake_illustrate == []


def test_generate_image_failure_is_a_readable_502(client, script, monkeypatch):
    _approved_thread(client, script, monkeypatch)

    def fail(*a, **kw):
        raise ImageGenerationError("Pollinations is rate limiting; wait a minute and retry.")

    monkeypatch.setattr(illustrator, "illustrate", fail)
    resp = client.post("/api/threads/t1/image", json={})
    assert resp.status_code == 502 and "rate limiting" in resp.json()["detail"]
    assert client.get("/api/health").json()["busy"] is False  # lock released


@pytest.mark.parametrize("name", ["nope.png", "..%2Fhistory.db", "a" * 32 + ".png"])
def test_images_route_serves_only_generated_files(client, name):
    assert client.get(f"/api/images/{name}").status_code == 404
