"""Topic Scout: gathers fresh candidates from RSS + Hacker News and picks the best topic."""

import logging
from collections.abc import Mapping
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from app.llm.client import get_llm
from app.llm.prompts import load_prompt
from app.llm.structured import StructuredOutputError, invoke_structured
from app.schemas.topic import Candidate, TopicChoice, TopicSelection
from app.tools.sources.candidates import collect_candidates
from app.tools.sources.niches import load_niche

log = logging.getLogger(__name__)

DEFAULT_NICHE = "ai engineering"
ROLE = "topic_scout"


class NoCandidatesError(RuntimeError):
    pass


def run(state: Mapping) -> dict:
    """Graph node. Reads `niche`, `instructions`, `recent_topics`; writes `candidates`, `topic`."""
    niche = state.get("niche") or DEFAULT_NICHE
    candidates = collect_candidates(load_niche(niche))
    if not candidates:
        raise NoCandidatesError(f"No recent candidates found for niche '{niche}'.")
    choice = choose_topic(
        candidates,
        niche=niche,
        instructions=state.get("instructions") or "",
        recent_topics=state.get("recent_topics") or _published_topics(),
    )
    return {
        "niche": niche,
        "candidates": [c.model_dump() for c in candidates],
        "topic": choice.model_dump(),
    }


def _published_topics() -> list[str]:
    """Topics already posted to LinkedIn, so the Scout doesn't repeat them."""
    from app.db.repository import PostRepository

    try:
        return PostRepository().recent_topics()
    except Exception as exc:  # noqa: BLE001 - dedupe is best-effort
        log.warning("Could not read post history: %s", exc)
        return []


def choose_topic(
    candidates: list[Candidate],
    *,
    niche: str,
    instructions: str = "",
    recent_topics: list[str] | None = None,
    attempts: int = 2,
) -> TopicChoice:
    llm = get_llm(ROLE)
    messages = [
        SystemMessage(content=load_prompt(ROLE)),
        HumanMessage(content=_brief(candidates, niche, instructions, recent_topics or [])),
    ]
    by_id = {i: c for i, c in enumerate(candidates, start=1)}

    for _ in range(attempts):
        selection = invoke_structured(llm, TopicSelection, messages)
        chosen = [i for i in selection.chosen_ids if i in by_id]
        if chosen:
            runners = [i for i in selection.runner_up_ids if i in by_id and i not in chosen][:3]
            return TopicChoice(
                **selection.model_dump(exclude={"chosen_ids", "runner_up_ids"}),
                chosen_ids=chosen,
                runner_up_ids=runners,
                source_urls=[by_id[i].url for i in chosen],
                source_titles=[by_id[i].title for i in chosen],
            )
        log.debug("Scout returned unknown ids %s, retrying", selection.chosen_ids)
        messages.append(
            HumanMessage(
                content=f"IDs {selection.chosen_ids} are not in the list. "
                f"Use only IDs between 1 and {len(candidates)}."
            )
        )
    raise StructuredOutputError("Topic Scout did not return any valid candidate IDs.")


def _brief(
    candidates: list[Candidate], niche: str, instructions: str, recent_topics: list[str]
) -> str:
    lines = [
        f"Today: {date.today().isoformat()}",
        f"Niche: {niche}",
        f"Extra instructions from the manager: {instructions or 'none'}",
        "Recently posted (avoid repeating): "
        + ("; ".join(recent_topics) if recent_topics else "none"),
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
