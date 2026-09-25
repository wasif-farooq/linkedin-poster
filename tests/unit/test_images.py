import base64

import httpx
import pytest
import respx

from app import config
from app.config import get_settings
from app.llm.usage import ImageBudgetExceededError, tracker
from app.tools.images import generate

JPEG = b"\xff\xd8\xff fake jpeg"


@pytest.fixture(autouse=True)
def fresh_budget(monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    monkeypatch.setattr(get_settings(), "image_provider", "auto")
    tracker.reset()


@respx.mock
def test_pollinations_renders_the_prompt_landscape_and_saves_it():
    route = respx.get(url__startswith="https://image.pollinations.ai/prompt/").mock(
        return_value=httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
    )
    image = generate.generate("a calm lake, no text", seed=7)
    assert image.provider == "pollinations" and image.data == JPEG
    request = route.calls.last.request
    assert request.url.raw_path.startswith(b"/prompt/a%20calm%20lake%2C%20no%20text?")
    assert request.url.params["width"] == "1200" and request.url.params["height"] == "627"
    assert request.url.params["seed"] == "7"

    name = generate.save(image)
    assert name.endswith(".jpg") and generate.image_path(name).read_bytes() == JPEG
    assert generate.image_path(name).parent == config.IMAGES_DIR


@respx.mock
def test_pollinations_errors_are_readable():
    respx.get(url__startswith="https://image.pollinations.ai/").mock(
        return_value=httpx.Response(
            200, text="<html>busy</html>", headers={"content-type": "text/html"}
        )
    )
    with pytest.raises(generate.ImageGenerationError, match="text/html"):
        generate.generate("x")


@respx.mock
def test_openai_is_used_when_a_key_is_set(monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test")
    route = respx.post("https://api.openai.com/v1/images/generations").mock(
        return_value=httpx.Response(
            200, json={"data": [{"b64_json": base64.b64encode(b"PNG").decode()}]}
        )
    )
    image = generate.generate("a lake")
    assert (image.provider, image.media_type, image.data) == ("openai", "image/png", b"PNG")
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer sk-test"
    assert b'"size":"1536x1024"' in sent.content.replace(b" ", b"")


def test_openai_provider_without_key_explains(monkeypatch):
    monkeypatch.setattr(get_settings(), "image_provider", "openai")
    with pytest.raises(generate.ImageGenerationError, match="OPENAI_API_KEY"):
        generate.generate("x")


@respx.mock
def test_images_per_run_are_capped(monkeypatch):
    monkeypatch.setattr(get_settings(), "max_images_per_run", 1)
    respx.get(url__startswith="https://image.pollinations.ai/").mock(
        return_value=httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
    )
    generate.generate("one")
    with pytest.raises(ImageBudgetExceededError):
        generate.generate("two")
    assert tracker.snapshot().images == 1


@pytest.mark.parametrize("name", ["../secret.png", "abc.png", "a" * 32 + ".exe", "", "x/y.png"])
def test_image_path_only_accepts_generated_names(name):
    assert generate.image_path(name) is None


def test_image_path_is_none_for_a_missing_file():
    assert generate.image_path("a" * 32 + ".png") is None


@respx.mock
def test_pollinations_busy_is_retried_then_explained(monkeypatch):
    monkeypatch.setattr(generate.time, "sleep", lambda s: None)
    route = respx.get(url__startswith="https://image.pollinations.ai/").mock(
        side_effect=[
            httpx.Response(500, json={"message": "upstream 429"}),
            httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"}),
        ]
    )
    assert generate.generate("x").data == JPEG and route.call_count == 2

    route.side_effect = None
    route.return_value = httpx.Response(429, json={"message": "slow down"})
    with pytest.raises(generate.ImageGenerationError, match="busy.*slow down"):
        generate.generate("x")
