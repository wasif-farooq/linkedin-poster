"""Manager: the only agent the user talks to. Turns chat into a plan for the workers,
and reports back once they're done. Costs ~2 LLM calls per chat turn."""

from collections.abc import Mapping

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.llm.client import get_llm
from app.llm.prompts import load_prompt
from app.llm.structured import invoke_structured
from app.schemas.manager import ManagerDecision
from app.schemas.post import Critique, Draft
from app.schemas.research import ResearchBrief

ROLE = "manager"
MAX_MANAGER_CALLS_PER_TURN = 2  # plan, then report back
HISTORY_MESSAGES = 12  # recent chat messages sent to the Manager

# Everything downstream of the topic; cleared whenever the topic changes.
TOPIC_RESET = {
    "research_brief": None,
    "draft": None,
    "critique": None,
    "revision_count": 0,
    "human_feedback": None,
    "approved": False,
    "final_post": None,
    "post_urn": None,
    "post_url": None,
    "publish_result": None,
}


def run(state: Mapping) -> dict:
    calls = (state.get("manager_calls") or 0) + 1
    if calls > MAX_MANAGER_CALLS_PER_TURN:  # safety net: answer without another LLM call
        return {"manager_calls": calls, "plan": [], "reply": _fallback_reply(state)}

    # After the workers have run, the Manager only reports back. Enforced in code: models
    # tend to re-plan the user's last request ("make it shorter") and loop.
    report_only = calls > 1
    system = load_prompt(ROLE) + "\n\n# Current state\n" + summarize_state(state)
    if report_only:
        system += (
            "\n\n# MODE: REPORT BACK\nThe agents have finished this turn's work (see activity). "
            "Return an empty plan and a short reply to the user. Any plan will be ignored."
        )
    messages = [SystemMessage(content=system), *_recent_history(state.get("messages") or [])]
    decision = invoke_structured(get_llm(ROLE), ManagerDecision, messages)
    if report_only:
        decision = ManagerDecision(reply=decision.reply or _fallback_reply(state))
    return apply_decision(state, decision) | {"manager_calls": calls}


def apply_decision(state: Mapping, d: ManagerDecision) -> dict:
    """Translate the Manager's decision into a state update (validated in code)."""
    update: dict = {"plan": list(d.plan), "reply": d.reply.strip() or None, "last_error": None}
    if d.plan:
        update["instructions"] = d.instructions.strip()
    if d.niche and d.niche.strip() and d.niche.strip() != state.get("niche"):
        update["niche"] = d.niche.strip()

    if d.use_candidate_id is not None:
        candidates = state.get("candidates") or []
        if 1 <= d.use_candidate_id <= len(candidates):
            c = candidates[d.use_candidate_id - 1]
            update |= TOPIC_RESET | {
                "topic": {
                    "topic": c["title"],
                    "angle": d.instructions.strip(),
                    "why_now": "",
                    "audience": "",
                    "chosen_ids": [d.use_candidate_id],
                    "runner_up_ids": [],
                    "source_urls": [c["url"]],
                    "source_titles": [c["title"]],
                }
            }
        else:
            update |= {"plan": [], "reply": f"I don't have a candidate #{d.use_candidate_id}."}
    elif d.topic_override and d.topic_override.strip():
        update |= TOPIC_RESET | {"topic": d.topic_override.strip()}

    if d.feedback and d.feedback.strip():
        update["human_feedback"] = d.feedback.strip()
        update["revision_count"] = 0  # human edits don't count toward the critic loop cap
    return update


def summarize_state(state: Mapping) -> str:
    lines = [f"Niche: {state.get('niche') or 'ai engineering (default)'}"]

    topic = state.get("topic")
    if isinstance(topic, str):
        lines.append(f"Topic (given by user): {topic}")
    elif topic:
        lines.append(f"Topic: {topic['topic']}\n  Angle: {topic.get('angle') or '-'}")
        if topic.get("why_now"):
            lines.append(f"  Why now: {topic['why_now']}")
        candidates = state.get("candidates") or []
        runners = [i for i in topic.get("runner_up_ids", []) if 1 <= i <= len(candidates)]
        if runners:
            lines.append(
                "  Runner-ups: " + "; ".join(f"#{i} {candidates[i - 1]['title']}" for i in runners)
            )
    else:
        lines.append("Topic: none yet")

    if state.get("research_brief"):
        brief = ResearchBrief.model_validate(state["research_brief"])
        lines.append(
            f"Research brief: {len(brief.key_points)} key points. Summary: {brief.summary}"
        )
        lines += [f"  [{s.id}] {s.title} — {s.url}" for s in brief.sources]
    else:
        lines.append("Research brief: none yet")

    if state.get("draft"):
        draft = Draft.model_validate(state["draft"])
        text = draft.full_text()
        lines.append(f'Current draft ({len(text)} chars):\n"""\n{text}\n"""')
    else:
        lines.append("Draft: none yet")

    if state.get("critique"):
        c = Critique.model_validate(state["critique"])
        scores = ", ".join(f"{k} {v}" for k, v in c.scores.model_dump().items())
        lines.append(f"Critic verdict on current draft: {c.verdict} ({scores})")
        lines += [f"  - {i}" for i in (c.rule_errors + c.issues)[:3]]
    elif state.get("draft"):
        lines.append("Critic: current draft not reviewed yet")
    lines.append(f"Revisions so far: {state.get('revision_count') or 0}")
    if state.get("approved"):
        lines.append("Approval: the user APPROVED the current draft (final post locked in)")
    elif state.get("draft"):
        lines.append("Approval: not approved yet")
    result = state.get("publish_result")
    if result:
        where = f" at {result['url']}" if result.get("url") else ""
        lines.append(f"Publishing: {result['status']}{where}")

    activity = state.get("activity") or []
    lines.append("This turn's activity: " + ("; ".join(activity) if activity else "nothing yet"))
    if state.get("last_error"):
        lines.append(f"Last error: {state['last_error']}")
    return "\n".join(lines)


def _recent_history(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Only user/manager chat turns; tool noise stays out of the Manager's context."""
    chat = [m for m in messages if isinstance(m, (HumanMessage, AIMessage))]
    return [
        HumanMessage(content=m.content)
        if isinstance(m, HumanMessage)
        else AIMessage(content=m.content)
        for m in chat[-HISTORY_MESSAGES:]
    ]


def _fallback_reply(state: Mapping) -> str:
    """Readable summary built from state, used when the LLM gives no reply (or the cap hit)."""
    if state.get("last_error"):
        return (
            f"Something went wrong: {state['last_error']}. Want me to try again or change course?"
        )
    activity = state.get("activity") or []
    if any(a.startswith("human_review: REJECTED") for a in activity):
        return "Draft rejected. Want a fresh take on the same topic, or a new topic?"
    result = state.get("publish_result") or {}
    if result.get("status") == "published":
        return f"Published to LinkedIn: {result['url']}"
    if result.get("status") == "dry_run":
        return "Dry run: the post was recorded locally, not published. What would you like next?"
    if state.get("approved") and state.get("final_post"):
        return (
            f"Your post is approved ({len(state['final_post'])} characters) and ready to go. "
            "What would you like next?"
        )
    if state.get("critique"):
        c = Critique.model_validate(state["critique"])
        low_name, low = c.scores.lowest()
        return (
            f"The draft is ready. The critic says {c.verdict} (lowest score: {low_name} {low}). "
            "Approve it, or tell me what to change."
        )
    topic = state.get("topic")
    if topic:
        title = topic if isinstance(topic, str) else topic.get("topic")
        return f"Current topic: {title}. Want me to research it and draft a post?"
    return "What would you like to do next? I can find a topic and draft a post."
