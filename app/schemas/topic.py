from pydantic import BaseModel, Field


class Candidate(BaseModel):
    """A potential topic pulled from a source (RSS item or HN story)."""

    title: str
    url: str
    source: str = Field(description="Feed/site name or 'Hacker News'")
    summary: str = ""
    published: str | None = Field(default=None, description="ISO-8601 timestamp")
    points: int | None = Field(default=None, description="HN points, if from HN")
    comments: int | None = Field(default=None, description="HN comment count, if from HN")
    keyword_hits: int = Field(default=0, description="How many niche keywords matched")


class TopicSelection(BaseModel):
    """What the Topic Scout LLM returns."""

    chosen_ids: list[int] = Field(
        min_length=1, description="IDs of the candidate(s) this topic is based on, best first"
    )
    topic: str = Field(description="Short topic title for the post")
    angle: str = Field(description="The specific, opinionated angle the post should take")
    why_now: str = Field(description="Why this is timely for the audience right now")
    audience: str = Field(description="Who on LinkedIn will care about this")
    runner_up_ids: list[int] = Field(
        default_factory=list, description="Up to 3 other strong candidate IDs, best first"
    )


class TopicOption(BaseModel):
    """One story on the Scout's shortlist."""

    candidate_ids: list[int] = Field(
        min_length=1, description="IDs of the candidate(s) covering this story, best first"
    )
    topic: str = Field(description="Short topic title for the post")
    angle: str = Field(description="The specific, opinionated angle the post should take")
    why_now: str = Field(description="Why this is timely for the audience right now")
    audience: str = Field(description="Who on LinkedIn will care about this")


class TopicShortlist(BaseModel):
    """What the Topic Scout LLM returns: distinct stories, best first."""

    options: list[TopicOption] = Field(min_length=1, max_length=5)


class TopicChoice(TopicSelection):
    """The selection enriched with the real source URLs (never trusted from the LLM)."""

    source_urls: list[str] = Field(default_factory=list)
    source_titles: list[str] = Field(default_factory=list)
