import json

import httpx2
import openai
import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.config import get_settings
from app.llm import structured
from app.llm.client import get_llm
from app.llm.usage import LLMBudgetExceededError, tracker

URL = "https://zen.test/v1/chat/completions"


def completion(text="pong"):
    return {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}
        ],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    }


class FakeZen:
    """Mock transport for the OpenAI SDK (it uses httpx2, which respx can't intercept)."""

    def __init__(self):
        self.responses: list[httpx2.Response] = []
        self.default: httpx2.Response | None = None
        self.call_count = 0

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == URL
        self.call_count += 1
        return self.responses.pop(0) if self.responses else self.default


RATE_LIMITED = httpx2.Response(429, json={"error": "slow down"})
OK = httpx2.Response(200, json=completion())


@pytest.fixture
def zen():
    return FakeZen()


@pytest.fixture
def llm(monkeypatch, zen):
    settings = get_settings()
    monkeypatch.setattr(settings, "open_code_key", "test-key")
    monkeypatch.setattr(settings, "opencode_base_url", "https://zen.test/v1")
    monkeypatch.setattr(settings, "llm_rate_limit_backoff", 0)
    tracker.reset(max_calls=None)
    client = httpx2.Client(transport=httpx2.MockTransport(zen))
    return get_llm(model="m", max_retries=0, rate_limiter=None, http_client=client)


def test_retries_on_429_then_succeeds(llm, zen):
    zen.responses = [RATE_LIMITED, OK]
    assert llm.invoke("hi").content == "pong"
    assert zen.call_count == 2
    snap = tracker.snapshot()
    assert snap.rate_limit_retries == 1
    assert (snap.input_tokens, snap.output_tokens) == (7, 3)


def test_gives_up_after_rate_limit_retries(llm, zen):
    zen.default = RATE_LIMITED
    with pytest.raises(openai.RateLimitError):
        llm.invoke("hi")
    assert tracker.snapshot().rate_limit_retries == get_settings().llm_rate_limit_retries


def test_budget_stops_extra_calls(llm, zen):
    zen.default = OK
    tracker.reset(max_calls=2)
    llm.invoke("1")
    llm.invoke("2")
    with pytest.raises(LLMBudgetExceededError):
        llm.invoke("3")
    assert tracker.snapshot().calls == 2


class Item(BaseModel):
    name: str


def test_structured_does_not_fall_back_on_rate_limit(llm, zen):
    zen.default = RATE_LIMITED
    llm.rate_limit_retries = 0
    with pytest.raises(openai.RateLimitError):
        structured.invoke_structured(llm, Item, [HumanMessage(content="go")], mode="auto")
    assert zen.call_count == 1  # no wasted JSON-fallback call


def test_native_failure_is_remembered(monkeypatch):
    monkeypatch.setattr(structured, "_native_unsupported", set())
    llm = FakeListChatModel(responses=['{"name": "a"}', '{"name": "b"}'])
    calls = []
    original = FakeListChatModel.with_structured_output

    def spy(self, *a, **kw):
        calls.append(1)
        return original(self, *a, **kw)

    monkeypatch.setattr(FakeListChatModel, "with_structured_output", spy)
    structured.invoke_structured(llm, Item, [HumanMessage(content="go")], mode="auto")
    structured.invoke_structured(llm, Item, [HumanMessage(content="go")], mode="auto")
    assert len(calls) == 1  # second call skipped native mode


def test_falls_back_when_model_is_blocked(llm, zen, monkeypatch):
    from app.llm import client

    monkeypatch.setattr(client, "_unavailable", set())
    blocked = httpx2.Response(403, json={"error": {"type": "FreeTierError", "message": "no"}})
    seen_models = []

    def handler(request):
        seen_models.append(json.loads(request.content)["model"])
        return blocked if len(seen_models) == 1 else httpx2.Response(200, json=completion())

    fallback_llm = get_llm(
        model="m",
        max_retries=0,
        rate_limiter=None,
        fallback_models=["backup"],
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    assert fallback_llm.invoke("hi").content == "pong"
    assert seen_models == ["m", "backup"]
    # later agents configured with the blocked model start on the fallback directly
    monkeypatch.setattr(get_settings(), "default_model", "m")
    monkeypatch.setattr(get_settings(), "llm_fallback_models", "backup")
    assert get_llm("writer", rate_limiter=None).model_name == "backup"


def test_no_fallback_configured_raises(llm, zen):
    zen.default = httpx2.Response(404, json={"error": "model not found"})
    with pytest.raises(openai.NotFoundError):
        llm.invoke("hi")
