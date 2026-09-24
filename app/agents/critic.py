"""Critic: rule checks (free) + LLM review; the pass/revise verdict is decided in code."""

from collections.abc import Mapping

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.context import format_brief, format_draft
from app.config import get_settings
from app.llm.client import get_llm
from app.llm.prompts import load_prompt
from app.llm.structured import invoke_structured
from app.schemas.post import CriticReview, Critique, Draft
from app.schemas.research import ResearchBrief
from app.tools.post_rules import check_post

ROLE = "critic"


def run(state: Mapping) -> dict:
    """Graph node. Reads `draft` and `research_brief`; writes `critique`."""
    if not state.get("draft") or not state.get("research_brief"):
        raise ValueError("Critic needs a draft and the research brief.")
    critique = review(
        ResearchBrief.model_validate(state["research_brief"]),
        Draft.model_validate(state["draft"]),
    )
    return {"critique": critique.model_dump()}


def review(brief: ResearchBrief, draft: Draft) -> Critique:
    settings = get_settings()
    rules = check_post(
        draft, target_min=settings.post_target_min_chars, target_max=settings.post_target_max_chars
    )
    findings = [f"ERROR: {e}" for e in rules.errors] + [f"warning: {w}" for w in rules.warnings]
    content = "\n\n".join(
        [
            "Research brief (the only allowed source of facts):\n"
            + format_brief(brief, include_content=True),
            "Draft post:\n" + format_draft(draft),
            "Automatic rule check:\n" + ("\n".join(findings) if findings else "all rules passed"),
        ]
    )
    result = invoke_structured(
        get_llm(ROLE),
        CriticReview,
        [SystemMessage(content=load_prompt(ROLE)), HumanMessage(content=content)],
    )
    _, lowest = result.scores.lowest()
    verdict = "revise" if rules.errors or lowest < settings.critic_min_score else "pass"
    return Critique(
        **result.model_dump(),
        verdict=verdict,
        rule_errors=rules.errors,
        rule_warnings=rules.warnings,
    )
