"""Illustrator: makes an image for the current draft, on request.

One LLM call turns the post into an image prompt; then the configured image backend
(app.tools.images) renders it and the file is kept in data/images.
"""

import random
from collections.abc import Mapping

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.context import format_draft
from app.llm.client import get_llm
from app.llm.prompts import load_prompt
from app.llm.structured import invoke_structured
from app.schemas.image import ImagePrompt, PostImage
from app.schemas.post import Draft
from app.tools.images import generate

ROLE = "illustrator"


def run(state: Mapping) -> dict:
    """Graph node. Reads `draft`, `topic`, `instructions` (style direction) and the current
    `image` (so a regeneration is a different picture); writes `image`."""
    if not state.get("draft"):
        raise ValueError("Illustrator needs a draft (write the post first).")
    image = illustrate(
        Draft.model_validate(state["draft"]),
        topic=_topic_title(state.get("topic")),
        direction=state.get("instructions") or "",
        previous=PostImage.model_validate(state["image"]) if state.get("image") else None,
    )
    return {"image": image.model_dump()}


def illustrate(
    draft: Draft,
    *,
    topic: str = "",
    direction: str = "",
    previous: PostImage | None = None,
) -> PostImage:
    parts = []
    if topic:
        parts.append(f"Topic: {topic}")
    parts.append("The post:\n" + format_draft(draft))
    if direction.strip():
        parts.append(f"Style direction from the author (follow it): {direction.strip()}")
    if previous:
        parts.append(
            "The author wants a new image instead of this one, so make it clearly different:\n"
            f"{previous.prompt}"
        )
    parts.append("Write the image prompt.")
    spec = invoke_structured(
        get_llm(ROLE),
        ImagePrompt,
        [SystemMessage(content=load_prompt(ROLE)), HumanMessage(content="\n\n".join(parts))],
    )
    rendered = generate.generate(spec.prompt, seed=random.randint(1, 2**31 - 1))
    return PostImage(
        prompt=spec.prompt,
        alt_text=spec.alt_text,
        file=generate.save(rendered),
        provider=rendered.provider,
        direction=direction.strip(),
    )


def _topic_title(topic) -> str:
    if isinstance(topic, str):
        return topic
    return (topic or {}).get("topic", "")
