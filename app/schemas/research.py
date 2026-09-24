from typing import Literal

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """One hit from a web/news search provider."""

    title: str
    url: str
    snippet: str = ""
    published: str | None = None
    source: str | None = None  # publisher name, when the provider gives one


class Article(BaseModel):
    """Main text extracted from a web page."""

    url: str
    title: str = ""
    text: str
    published: str | None = None


class Source(BaseModel):
    """Numbered evidence the Researcher hands to the LLM and the Writer."""

    id: int
    title: str
    url: str
    origin: Literal["scout", "search"]
    content: str = Field(description="Article text (truncated) or search snippet")
    published: str | None = None
    full_text: bool = Field(default=False, description="True if content is the page text")


class SearchQuery(BaseModel):
    query: str = Field(description="A focused web search query (3-10 words)")
    kind: Literal["web", "news"] = Field(
        default="web", description="'news' for recent coverage, 'web' for background/docs/data"
    )


class ResearchPlan(BaseModel):
    """What the Researcher LLM returns in step 1."""

    queries: list[SearchQuery] = Field(min_length=1, max_length=4)


class KeyPoint(BaseModel):
    point: str
    source_ids: list[int] = Field(default_factory=list)


class Stat(BaseModel):
    fact: str = Field(description="A concrete number, date, benchmark or quote")
    source_ids: list[int] = Field(default_factory=list)  # uncited stats are dropped in code


class BriefDraft(BaseModel):
    """What the Researcher LLM returns in step 2."""

    summary: str = Field(description="3-5 sentence neutral summary of what happened and why")
    key_points: list[KeyPoint] = Field(min_length=1, max_length=8)
    stats: list[Stat] = Field(default_factory=list, max_length=8)
    counterpoints: list[KeyPoint] = Field(
        default_factory=list, description="Caveats, criticism, or open questions"
    )


class ResearchBrief(BriefDraft):
    """The brief plus the sources it cites (citations validated by code)."""

    topic: str
    angle: str = ""
    sources: list[Source] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
