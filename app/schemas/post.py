from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Draft(BaseModel):
    """What the Writer returns."""

    text: str = Field(description="The post body in plain text (no hashtags, no markdown)")
    hashtags: list[str] = Field(description="3-5 relevant hashtags, e.g. '#AIEngineering'")
    source_ids: list[int] = Field(
        default_factory=list, description="IDs of the brief's sources the post relies on"
    )

    @field_validator("hashtags")
    @classmethod
    def _normalize_hashtags(cls, tags: list[str]) -> list[str]:
        out: list[str] = []
        for tag in tags:
            # alphanumeric only: '_' is reserved in LinkedIn's post format and splits the tag
            word = "".join(ch for ch in tag.strip().lstrip("#") if ch.isalnum())
            if word and f"#{word}".lower() not in {t.lower() for t in out}:
                out.append(f"#{word}")
        return out

    @classmethod
    def from_full_text(cls, text: str, source_ids: list[int] | None = None) -> "Draft":
        """Parse a human-edited post: a trailing line made only of hashtags becomes `hashtags`."""
        lines = text.strip().splitlines()
        tags: list[str] = []
        if lines and all(w.startswith("#") and len(w) > 1 for w in lines[-1].split()):
            tags = lines.pop().split()
        return cls(text="\n".join(lines).strip(), hashtags=tags, source_ids=source_ids or [])

    def full_text(self) -> str:
        """Exactly what gets published."""
        tags = " ".join(self.hashtags)
        return f"{self.text.strip()}\n\n{tags}" if tags else self.text.strip()


class Scores(BaseModel):
    hook: int = Field(
        ge=1, le=10, description="Do the first 1-2 lines make people click 'see more'?"
    )
    insight: int = Field(ge=1, le=10, description="Is there a clear, non-obvious point of view?")
    accuracy: int = Field(ge=1, le=10, description="Is every claim supported by the brief?")
    clarity: int = Field(ge=1, le=10, description="Easy to read, skimmable, no jargon soup?")
    tone: int = Field(ge=1, le=10, description="Human, credible, not hype or clickbait?")

    def lowest(self) -> tuple[str, int]:
        name, value = min(self.model_dump().items(), key=lambda kv: kv[1])
        return name, value


class CriticReview(BaseModel):
    """What the Critic LLM returns."""

    scores: Scores
    issues: list[str] = Field(default_factory=list, description="Concrete problems, worst first")
    suggestions: list[str] = Field(
        default_factory=list, description="Specific edits that would fix the issues"
    )


class Critique(CriticReview):
    """Review plus the code-decided verdict and the rule-check findings."""

    verdict: Literal["pass", "revise"]
    rule_errors: list[str] = Field(default_factory=list)
    rule_warnings: list[str] = Field(default_factory=list)
