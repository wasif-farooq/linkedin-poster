from typing import Literal

from pydantic import BaseModel, Field, field_validator

Worker = Literal[
    "topic_scout", "researcher", "writer", "critic", "illustrator", "human_review", "publisher"
]


class ManagerDecision(BaseModel):
    """What the Manager LLM returns every time it's consulted."""

    plan: list[Worker] = Field(
        default_factory=list,
        description="Agents to run now, in order. Empty = just reply to the user.",
    )
    instructions: str = Field(
        default="", description="Guidance passed to the agents (e.g. 'focus on open-source')"
    )
    niche: str | None = Field(default=None, description="Set only if the user changes the niche")
    topic_override: str | None = Field(
        default=None, description="A topic the user explicitly gave; skips the Topic Scout"
    )
    use_candidate_id: int | None = Field(
        default=None, description="Switch to this candidate/runner-up ID from the scout's list"
    )
    feedback: str | None = Field(
        default=None,
        description="The user's requested changes to the current draft, in their words",
    )
    reply: str = Field(
        default="",
        description="Message to the user. Required when plan is empty; otherwise a short "
        "note of what you're about to do.",
    )

    @field_validator("use_candidate_id", mode="before")
    @classmethod
    def _zero_means_none(cls, v):
        # Models often fill 0 / "" / "none" for "not set" instead of null.
        if v in (0, "0", "", "none", "null", None):
            return None
        return v

    @field_validator("niche", "topic_override", "feedback", mode="before")
    @classmethod
    def _blank_means_none(cls, v):
        if isinstance(v, str) and v.strip().lower() in ("", "none", "null", "n/a"):
            return None
        return v
