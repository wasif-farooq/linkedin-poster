"""Deterministic control flow: the Manager proposes a plan, code enforces the rules.

- missing prerequisites are inserted (writer needs a brief, critic needs a draft, ...)
- an already-reviewed draft isn't sent to the critic again
- the critic->writer revision loop is driven here, capped at MAX_REVISIONS
- a turn can run at most MAX_STEPS_PER_TURN worker steps
"""

from collections.abc import Mapping

from app.config import get_settings

# step -> (state field it needs, steps that produce it)
PREREQUISITES = {
    "researcher": ("topic", ["topic_scout"]),
    "writer": ("research_brief", ["researcher"]),
    "critic": ("draft", ["writer"]),
    # A brand-new draft is scored by the critic before a human sees it. (A draft the user
    # edited themselves has no critique on purpose: the critic must not rewrite it.)
    "human_review": ("draft", ["writer", "critic"]),
}
APPROVAL_REQUIRED = {"publisher"}  # never reachable without state["approved"]


def dispatch(state: Mapping) -> dict:
    """Graph node: pick the next worker from the plan (or hand back to the Manager)."""
    plan = list(state.get("plan") or [])
    steps = state.get("step_count") or 0

    while plan:
        if steps >= get_settings().max_steps_per_turn:
            return {
                "next": "manager",
                "plan": [],
                "last_error": f"Stopped: step limit of {steps} per turn reached.",
            }
        step = plan[0]
        need = PREREQUISITES.get(step)
        if need and not state.get(need[0]):
            for producer in need[1]:
                if producer in plan:
                    plan.remove(producer)
            plan[0:0] = need[1]  # e.g. writer without a brief -> research first
            continue
        if step == "critic" and state.get("critique") and state.get("draft"):
            plan.pop(0)  # current draft already reviewed
            continue
        if step in APPROVAL_REQUIRED and not state.get("approved"):
            if "human_review" in plan:
                plan.remove("human_review")
            plan.insert(0, "human_review")  # the approval gate
            continue
        return {"next": step, "plan": plan[1:]}
    if needs_human_review(state):
        return {"next": "human_review", "plan": []}
    return {"next": "manager", "plan": []}


def needs_human_review(state: Mapping) -> bool:
    """A draft written and reviewed this turn goes to the human before the Manager reports."""
    if not state.get("draft") or not state.get("critique") or state.get("approved"):
        return False
    activity = state.get("activity") or []
    last_write = max((i for i, a in enumerate(activity) if a.startswith("writer:")), default=-1)
    last_review = max(
        (i for i, a in enumerate(activity) if a.startswith("human_review:")), default=-1
    )
    return last_write > last_review


def after_critic(state: Mapping, critique: dict) -> tuple[list[str], str | None]:
    """Queue another writer->critic round if the critic asked for it and the cap allows.
    Returns (new plan, note for the activity log)."""
    plan = list(state.get("plan") or [])
    revisions = state.get("revision_count") or 0
    if critique["verdict"] != "revise":
        return plan, None
    if revisions < get_settings().max_revisions:
        if plan[:2] != ["writer", "critic"]:
            plan = ["writer", "critic", *plan]
        return plan, f"auto-revision {revisions + 1}/{get_settings().max_revisions} queued"
    return plan, f"revision cap ({revisions}) reached; the user decides"


def route_after_manager(state: Mapping) -> str:
    return "dispatch" if state.get("plan") else "respond"


def route_after_dispatch(state: Mapping) -> str:
    return state.get("next") or "manager"
