"""Topic Scout: gathers fresh candidates from RSS + Hacker News and picks the best topic."""

import logging
from collections.abc import Mapping
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from app.llm.client import get_llm
from app.llm.prompts import load_prompt
from app.llm.structured import StructuredOutputError, invoke_structured
from app.schemas.topic import Candidate, TopicChoice, TopicOption, TopicShortlist
from app.tools.sources.candidates import collect_candidates
from app.tools.sources.niches import load_niche

log = logging.getLogger(__name__)

DEFAULT_NICHE = "ai engineering"
ROLE = "topic_scout"


class NoCandidatesError(RuntimeError):
    pass


def run(state: Mapping) -> dict:
    """Graph node. Shortlists topics; with `auto_topic` it also picks the best one.

    Without auto-pick it returns `topic_options` and no topic: the human picks in the
    `topic_pick` step (a separate node, so answering doesn't re-run this LLM call)."""
    niche = state.get("niche") or DEFAULT_NICHE
    candidates = collect_candidates(load_niche(niche))
    if not candidates:
        raise NoCandidatesError(f"No recent candidates found for niche '{niche}'.")
    options = choose_topics(
        candidates,
        niche=niche,
        instructions=state.get("instructions") or "",
        recent_topics=state.get("recent_topics") or _published_topics(),
        excluded=state.get("excluded_topics") or [],
    )
    update = {"niche": niche, "candidates": [c.model_dump() for c in candidates]}
    if state.get("auto_topic"):
        return update | {"topic": options[0].model_dump(), "topic_options": None}
    return update | {"topic": None, "topic_options": [o.model_dump() for o in options]}


def _published_topics() -> list[str]:
    """Topics already posted to LinkedIn, so the Scout doesn't repeat them."""
    from app.db.repository import PostRepository

    try:
        return PostRepository().recent_topics()
    except Exception as exc:  # noqa: BLE001 - dedupe is best-effort
        log.warning("Could not read post history: %s", exc)
        return []


def choose_topic(candidates: list[Candidate], **kwargs) -> TopicChoice:
    """The single best topic (auto-pick)."""
    return choose_topics(candidates, **kwargs)[0]


def choose_topics(
    candidates: list[Candidate],
    *,
    niche: str,
    instructions: str = "",
    recent_topics: list[str] | None = None,
    excluded: list[str] | None = None,
    attempts: int = 2,
) -> list[TopicChoice]:
    """A ranked shortlist of distinct topics. Source URLs come from the candidates,
    never from the LLM."""
    llm = get_llm(ROLE)
    messages = [
        SystemMessage(content=load_prompt(ROLE)),
        HumanMessage(
            content=_brief(candidates, niche, instructions, recent_topics or [], excluded or [])
        ),
    ]
    by_id = {i: c for i, c in enumerate(candidates, start=1)}

    for _ in range(attempts):
        shortlist = invoke_structured(llm, TopicShortlist, messages)
        options: list[tuple[list[int], TopicOption]] = []
        used: set[int] = set()
        for option in shortlist.options:
            ids = [i for i in option.candidate_ids if i in by_id and i not in used]
            if ids:  # unknown ids dropped; a story already covered by an earlier option skipped
                used.update(ids)
                options.append((ids, option))
        if options:
            firsts = [ids[0] for ids, _ in options]
            return [
                TopicChoice(
                    **option.model_dump(exclude={"candidate_ids"}),
                    chosen_ids=ids,
                    runner_up_ids=[f for f in firsts if f != ids[0]][:3],
                    source_urls=[by_id[i].url for i in ids],
                    source_titles=[by_id[i].title for i in ids],
                )
                for ids, option in options
            ]
        log.debug("Scout returned no usable candidate ids, retrying")
        messages.append(
            HumanMessage(content=f"Use only candidate IDs between 1 and {len(candidates)}.")
        )
    raise StructuredOutputError("Topic Scout did not return any valid candidate IDs.")


def _brief(
    candidates: list[Candidate],
    niche: str,
    instructions: str,
    recent_topics: list[str],
    excluded: list[str] | None = None,
) -> str:
    lines = [
        f"Today: {date.today().isoformat()}",
        f"Niche: {niche}",
        f"Extra instructions from the manager: {instructions or 'none'}",
        "Recently posted (avoid repeating): "
        + ("; ".join(recent_topics) if recent_topics else "none"),
        "Already suggested (the author wants different ones): "
        + ("; ".join(excluded) if excluded else "none"),
        "",
        "Candidates:",
    ]
    for i, c in enumerate(candidates, start=1):
        lines.append(f"[{i}] {c.title}")
        meta = [c.source]
        if c.points is not None:
            meta.append(f"{c.points} points, {c.comments or 0} comments")
        if c.published:
            meta.append(c.published[:10])
        lines.append("    " + " | ".join(meta))
        if c.summary and c.source != "Hacker News":
            lines.append(f"    {c.summary[:220]}")
    return "\n".join(lines)
