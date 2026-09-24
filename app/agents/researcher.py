"""Researcher: reads the Scout's source articles, runs a few free web searches,
and turns the evidence into a cited ResearchBrief.

LLM calls: 2 (plan queries, write brief). Searches: <= MAX_SEARCHES_PER_RUN.
"""

import logging
import re
from collections.abc import Mapping
from datetime import date
from itertools import chain, zip_longest

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.llm.client import get_llm
from app.llm.prompts import load_prompt
from app.llm.structured import invoke_structured
from app.llm.usage import SearchBudgetExceededError, tracker
from app.schemas.research import (
    Article,
    BriefDraft,
    ResearchBrief,
    ResearchPlan,
    SearchQuery,
    SearchResult,
    Source,
)
from app.tools.sources import web_search
from app.tools.sources.articles import fetch_articles

log = logging.getLogger(__name__)

ROLE = "researcher"
MAX_QUERIES = 4
MAX_SOURCES = 12
_INLINE_CITES = re.compile(r"\s*(\[\d+\])+")  # "[1][4]" typed into prose by the model


class NoSourcesError(RuntimeError):
    pass


def run(state: Mapping) -> dict:
    """Graph node. Reads `topic` (TopicChoice dict or plain string) and `instructions`."""
    topic = state.get("topic")
    if not topic:
        raise ValueError("Researcher needs a topic (run the Topic Scout first).")
    if isinstance(topic, str):
        title, angle, seed_urls = topic, "", []
    else:
        title, angle, seed_urls = (
            topic["topic"],
            topic.get("angle", ""),
            topic.get("source_urls", []),
        )
    brief = research(
        title, angle=angle, seed_urls=seed_urls, instructions=state.get("instructions") or ""
    )
    return {"research_brief": brief.model_dump()}


def research(
    topic: str, *, angle: str = "", seed_urls: list[str] | None = None, instructions: str = ""
) -> ResearchBrief:
    settings = get_settings()
    llm = get_llm(ROLE)
    seed_urls = list(dict.fromkeys(seed_urls or []))[: settings.max_articles_per_run]
    seeds = fetch_articles(seed_urls, max_chars=settings.article_max_chars)

    queries = _plan_queries(llm, topic, angle, instructions, list(seeds.values()))
    results = _run_searches(queries)

    # Read the top search hits in full with whatever article slots the seeds left over.
    seen = set(seed_urls)
    fresh: list[SearchResult] = []
    for r in results:
        if r.url not in seen:
            seen.add(r.url)
            fresh.append(r)
    slots = max(settings.max_articles_per_run - len(seed_urls), 0)
    pages = fetch_articles([r.url for r in fresh[:slots]], max_chars=settings.article_max_chars)

    sources = _build_sources(seeds, fresh, pages)
    if not sources:
        raise NoSourcesError(f"No usable sources found for '{topic}'.")

    draft = invoke_structured(
        llm,
        BriefDraft,
        [
            SystemMessage(content=load_prompt(ROLE)),
            HumanMessage(content=_synthesis_brief(topic, angle, instructions, sources)),
        ],
    )
    return _finalize(draft, topic, angle, sources, [q.query for q in queries])


def _plan_queries(
    llm, topic: str, angle: str, instructions: str, seeds: list[Article]
) -> list[SearchQuery]:
    left = tracker.searches_left()
    budget = MAX_QUERIES if left is None else min(MAX_QUERIES, left)
    if budget <= 0:
        log.info("No search budget left; researching from seed articles only")
        return []
    covered = "\n".join(f"- {a.title or a.url}" for a in seeds) or "none"
    plan = invoke_structured(
        llm,
        ResearchPlan,
        [
            SystemMessage(content=load_prompt("researcher_queries")),
            HumanMessage(
                content=(
                    f"Today: {date.today().isoformat()}\n"
                    f"Topic: {topic}\nAngle: {angle or 'not set'}\n"
                    f"Extra instructions: {instructions or 'none'}\n"
                    f"Articles already provided:\n{covered}\n\n"
                    f"You may use at most {budget} queries."
                )
            ),
        ],
    )
    unique: dict[str, SearchQuery] = {}
    for q in plan.queries:
        q.query = q.query.strip()
        if q.query:
            unique.setdefault(q.query.lower(), q)  # keep the first of any duplicates
    return list(unique.values())[:budget]


def _run_searches(queries: list[SearchQuery]) -> list[SearchResult]:
    """Run queries one by one (the search tool paces them); a failing query is skipped."""
    per_query: list[list[SearchResult]] = []
    for q in queries:
        try:
            per_query.append(
                web_search.search(q.query, kind=q.kind, timelimit="m" if q.kind == "news" else None)
            )
        except SearchBudgetExceededError:
            log.info("Search budget reached; stopping searches")
            break
        except web_search.SearchError as exc:
            log.warning("Search failed for %r: %s", q.query, exc)
    # Interleave so the best hit of every query comes before the 2nd hit of any query.
    return [r for r in chain.from_iterable(zip_longest(*per_query)) if r]


def _build_sources(
    seeds: dict[str, Article], results: list[SearchResult], pages: dict[str, Article]
) -> list[Source]:
    sources: list[Source] = []
    for article in seeds.values():
        sources.append(
            Source(
                id=len(sources) + 1,
                title=article.title or article.url,
                url=article.url,
                origin="scout",
                content=article.text,
                published=article.published,
                full_text=True,
            )
        )
    for r in results:
        if len(sources) >= MAX_SOURCES:
            break
        page = pages.get(r.url)
        if not page and not r.snippet:
            continue
        sources.append(
            Source(
                id=len(sources) + 1,
                title=r.title,
                url=r.url,
                origin="search",
                content=page.text if page else r.snippet,
                published=r.published or (page.published if page else None),
                full_text=bool(page),
            )
        )
    return sources


def _synthesis_brief(topic: str, angle: str, instructions: str, sources: list[Source]) -> str:
    parts = [
        f"Today: {date.today().isoformat()}",
        f"Topic: {topic}",
        f"Angle: {angle or 'not set'}",
        f"Extra instructions: {instructions or 'none'}",
        "",
        "Sources:",
    ]
    for s in sources:
        header = f"[{s.id}] {s.title} — {s.url}"
        if s.published:
            header += f" ({s.published[:10]})"
        kind = "article text" if s.full_text else "search snippet"
        parts += [header, f"({kind})", s.content, ""]
    return "\n".join(parts)


def _finalize(
    draft: BriefDraft, topic: str, angle: str, sources: list[Source], queries: list[str]
) -> ResearchBrief:
    """Drop citations to unknown sources, drop uncited stats, keep only cited sources."""
    valid = {s.id for s in sources}
    for kp in (*draft.key_points, *draft.counterpoints):
        kp.source_ids = [i for i in kp.source_ids if i in valid]
        kp.point = _INLINE_CITES.sub("", kp.point).strip()
    for st in draft.stats:
        st.source_ids = [i for i in st.source_ids if i in valid]
        st.fact = _INLINE_CITES.sub("", st.fact).strip()
    stats = [st for st in draft.stats if st.source_ids]

    cited = {
        i for item in (*draft.key_points, *draft.counterpoints, *stats) for i in item.source_ids
    }
    kept = [s for s in sources if s.id in cited] or sources
    return ResearchBrief(
        summary=draft.summary,
        key_points=draft.key_points,
        stats=stats,
        counterpoints=draft.counterpoints,
        topic=topic,
        angle=angle,
        sources=kept,
        queries=queries,
    )
