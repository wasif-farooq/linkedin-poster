import json

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.agents import illustrator
from app.schemas.image import PostImage
from app.schemas.post import Draft
from app.tools.images.generate import GeneratedImage

DRAFT = Draft(text="Agent instructions are config now.", hashtags=["#AI"])
SPEC = json.dumps({"prompt": "Isometric config files, teal, no text", "alt_text": "Stacked files."})


def install(monkeypatch, *responses):
    seen: list[str] = []
    fake = FakeListChatModel(responses=list(responses))
    original = fake.invoke

    def spy(messages, *a, **kw):
        seen.append("\n".join(m.content for m in messages))
        return original(messages, *a, **kw)

    object.__setattr__(fake, "invoke", spy)
    monkeypatch.setattr(illustrator, "get_llm", lambda role: fake)
    rendered: list[str] = []

    def fake_generate(prompt, seed=None):
        rendered.append(prompt)
        return GeneratedImage(b"PNG", "image/png", "pollinations")

    monkeypatch.setattr(illustrator.generate, "generate", fake_generate)
    return seen, rendered


def test_illustrate_writes_a_prompt_renders_and_saves(monkeypatch):
    seen, rendered = install(monkeypatch, SPEC)
    image = illustrator.illustrate(DRAFT, topic="Agents as config", direction="photo style")
    assert rendered == ["Isometric config files, teal, no text"]
    assert image.alt_text == "Stacked files." and image.provider == "pollinations"
    assert image.file.endswith(".png") and image.direction == "photo style"
    assert "Agent instructions are config now." in seen[0] and "photo style" in seen[0]


def test_regenerating_asks_for_a_different_image(monkeypatch):
    seen, _ = install(monkeypatch, SPEC)
    previous = PostImage(prompt="Old lake scene", alt_text="a lake", file="x.png", provider="p")
    illustrator.run({"draft": DRAFT.model_dump(), "image": previous.model_dump()})
    assert "clearly different" in seen[0] and "Old lake scene" in seen[0]
