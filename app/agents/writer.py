"""Writer: turns a ResearchBrief into a LinkedIn post, and revises it from feedback."""

from collections.abc import Mapping

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.context import format_brief, format_draft, format_feedback
from app.config import get_settings
from app.llm.client import get_llm
from app.llm.prompts import render_prompt
from app.llm.structured import invoke_structured
from app.schemas.post import Critique, Draft
from app.schemas.research import ResearchBrief

ROLE = "writer"


def run(state: Mapping) -> dict:
    """Graph node. Reads `research_brief`, `instructions`, and for revisions `draft`,
    `critique` (used only if it asked for a revision) and `human_feedback`."""
    if not state.get("research_brief"):
        raise ValueError("Writer needs a research brief (run the Researcher first).")
    brief = ResearchBrief.model_validate(state["research_brief"])
    previous = Draft.model_validate(state["draft"]) if state.get("draft") else None
    critique = Critique.model_validate(state["critique"]) if state.get("critique") else None
    if critique and critique.verdict == "pass":
        critique = None

    draft = write(
        brief,
        instructions=state.get("instructions") or "",
        previous=previous,
        feedback=format_feedback(critique, state.get("human_feedback")),
    )
    revision_count = state.get("revision_count") or 0
    return {
        "draft": draft.model_dump(),
        "critique": None,  # a new draft needs a new review
        "human_feedback": None,  # consumed
        "revision_count": revision_count + 1 if previous else 0,
    }


def write(
    brief: ResearchBrief,
    *,
    instructions: str = "",
    previous: Draft | None = None,
    feedback: list[str] | None = None,
) -> Draft:
    settings = get_settings()
    system = render_prompt(
        ROLE,
        target_min=settings.post_target_min_chars,
        target_max=settings.post_target_max_chars,
        voice=_load_voice(),
    )
    parts = [format_brief(brief)]
    if instructions:
        parts.append(f"Extra instructions: {instructions}")
    if previous:
        parts.append("Your previous draft:\n" + format_draft(previous))
        if feedback:
            parts.append("Feedback to address:\n" + "\n".join(f"- {f}" for f in feedback))
        parts.append("Write the complete revised post.")
    else:
        parts.append("Write the post.")

    draft = invoke_structured(
        get_llm(ROLE),
        Draft,
        [SystemMessage(content=system), HumanMessage(content="\n\n".join(parts))],
    )
    valid = {s.id for s in brief.sources}
    draft.source_ids = [i for i in draft.source_ids if i in valid]
    return draft


def _load_voice() -> str:
    path = get_settings().voice_path
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return "Direct, practical, credible. No hype."
