"""Topic pick: the human chooses from the Topic Scout's shortlist (when auto-pick is off).

A separate node from the Scout on purpose: a resumed node re-runs from its top, so an
interrupt inside the Scout would redo its LLM call on every answer."""

from collections.abc import Mapping

from langgraph.types import interrupt
from pydantic import ValidationError

from app.agents.manager import TOPIC_RESET
from app.schemas.review import TopicPickAnswer


def run(state: Mapping) -> dict:
    options = state.get("topic_options") or []
    if not options:
        raise ValueError("No topic shortlist to choose from (run the Topic Scout first).")
    raw = interrupt(
        {
            "type": "topic_choice",
            "options": [
                {
                    "id": i,
                    "topic": o["topic"],
                    "angle": o.get("angle", ""),
                    "why_now": o.get("why_now", ""),
                    "audience": o.get("audience", ""),
                    "sources": [
                        {"title": t, "url": u}
                        for t, u in zip(
                            o.get("source_titles", []), o.get("source_urls", []), strict=False
                        )
                    ],
                }
                for i, o in enumerate(options)
            ],
            "round": len(state.get("excluded_topics") or []) // max(len(options), 1) + 1,
        }
    )
    plan = list(state.get("plan") or [])
    activity = list(state.get("activity") or [])
    try:
        answer = TopicPickAnswer.model_validate(raw)
    except ValidationError:
        return {"plan": ["topic_pick", *plan], "activity": activity}  # malformed: ask again

    if answer.cancel:
        return {"plan": [], "activity": [*activity, "topic_pick: cancelled"]}

    if answer.more:
        shown = [o["topic"] for o in options]
        update = {
            "excluded_topics": [*(state.get("excluded_topics") or []), *shown],
            "plan": ["topic_scout", *plan],  # the Scout re-shortlists; the pick follows it again
            "activity": [*activity, "topic_pick: asked for different topics"],
        }
        if answer.hint and answer.hint.strip():
            update["instructions"] = answer.hint.strip()
        return update

    if answer.topic:
        topic = answer.topic.strip()
        return TOPIC_RESET | {
            "topic": topic,
            "excluded_topics": [],
            "activity": [*activity, f"topic_pick: you chose your own topic '{topic}'"],
        }

    if not 0 <= answer.choice < len(options):
        return {"plan": ["topic_pick", *plan], "activity": activity}  # out of range: ask again
    chosen = options[answer.choice]
    return TOPIC_RESET | {
        "topic": chosen,
        "excluded_topics": [],
        "activity": [*activity, f"topic_pick: you chose '{chosen['topic']}'"],
    }
