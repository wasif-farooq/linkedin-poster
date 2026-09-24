"""Human review: pauses the graph with interrupt() until the user approves, edits,
asks for a revision, or rejects the draft. Nothing can be published without approval."""

from collections.abc import Mapping

from langgraph.types import interrupt

from app.config import get_settings
from app.schemas.post import Critique, Draft
from app.schemas.review import ReviewAction
from app.tools.post_rules import check_post


def run(state: Mapping) -> dict:
    """Graph node. Re-runs from the top on resume, so everything before interrupt() is pure."""
    if not state.get("draft"):
        raise ValueError("Nothing to review yet (no draft).")
    draft = Draft.model_validate(state["draft"])
    critique = Critique.model_validate(state["critique"]) if state.get("critique") else None
    settings = get_settings()
    rules = check_post(
        draft, target_min=settings.post_target_min_chars, target_max=settings.post_target_max_chars
    )

    raw = interrupt(
        {
            "type": "review",
            "post": draft.full_text(),
            "chars": len(draft.full_text()),
            "critic_verdict": critique.verdict if critique else None,
            "critic_scores": critique.scores.model_dump() if critique else None,
            "critic_issues": (critique.issues[:3] if critique else []),
            "rule_errors": rules.errors,
            "can_approve": rules.ok,
        }
    )
    decision = ReviewAction.model_validate(raw)
    return apply_review(state, draft, decision)


def apply_review(state: Mapping, draft: Draft, decision: ReviewAction) -> dict:
    plan = list(state.get("plan") or [])
    activity = list(state.get("activity") or [])
    settings = get_settings()

    if decision.action == "approve":
        rules = check_post(draft)
        if not rules.ok:  # e.g. over LinkedIn's limit: can't be approved as is
            return {
                "plan": ["human_review", *plan],
                "activity": [
                    *activity,
                    "human_review: approval blocked — " + "; ".join(rules.errors),
                ],
            }
        return {
            "approved": True,
            "final_post": draft.full_text(),
            "activity": [*activity, "human_review: APPROVED"],
        }

    if decision.action == "edit":
        edited = Draft.from_full_text(decision.text, source_ids=draft.source_ids)
        rules = check_post(
            edited,
            target_min=settings.post_target_min_chars,
            target_max=settings.post_target_max_chars,
        )
        base = {"draft": edited.model_dump(), "critique": None}
        if not rules.ok:
            return base | {
                "approved": False,
                "plan": ["human_review", *plan],
                "activity": [*activity, "human_review: edited, but " + "; ".join(rules.errors)],
            }
        return base | {
            "approved": True,
            "final_post": edited.full_text(),
            "activity": [*activity, "human_review: edited by user and APPROVED"],
        }

    if decision.action == "revise":
        return {
            "approved": False,
            "human_feedback": decision.text.strip(),
            "revision_count": 0,
            "plan": ["writer", "critic", "human_review", *plan],
            "activity": [
                *activity,
                f"human_review: revision requested ({decision.text.strip()[:80]})",
            ],
        }

    # reject: drop the draft (topic and research are kept) and whatever was planned after it
    return {
        "approved": False,
        "final_post": None,
        "draft": None,
        "critique": None,
        "plan": [],
        "activity": [*activity, "human_review: REJECTED the draft"],
    }
