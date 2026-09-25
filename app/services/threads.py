"""Read-side views of conversations (threads), shared by the CLI and the web API."""

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.schemas.post import Draft

THREAD_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


def config_for(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def thread_status(snapshot) -> str:
    """choose_topic | needs_review | confirm_publish | published | shared | approved | draft | new."""
    if snapshot.interrupts:
        kind = (snapshot.interrupts[0].value or {}).get("type")
        return {"publish_confirm": "confirm_publish", "topic_choice": "choose_topic"}.get(
            kind, "needs_review"
        )
    values = snapshot.values or {}
    result_status = (values.get("publish_result") or {}).get("status")
    if result_status in ("published", "shared"):
        return result_status
    if values.get("approved"):
        return "approved"
    if values.get("draft"):
        return "draft"
    return "new"


def thread_title(values: dict) -> str:
    topic = values.get("topic")
    if isinstance(topic, str) and topic:
        return topic
    if isinstance(topic, dict) and topic.get("topic"):
        return topic["topic"]
    if values.get("topic_options"):
        return "Choosing a topic"
    for message in values.get("messages") or []:
        if isinstance(message, HumanMessage):
            return str(message.content)[:80]
    return "New conversation"


def list_threads(graph, checkpointer, limit: int = 20) -> list[dict]:
    """Most recently active threads first (works with any LangGraph checkpointer)."""
    seen: list[str] = []
    for item in checkpointer.list(None):
        thread_id = item.config["configurable"]["thread_id"]
        if thread_id not in seen:
            seen.append(thread_id)
            if len(seen) >= limit:
                break
    out = []
    for thread_id in seen:
        snap = graph.get_state(config_for(thread_id))
        out.append(
            {"id": thread_id, "title": thread_title(snap.values), "status": thread_status(snap)}
        )
    return out


def thread_snapshot(graph, thread_id: str) -> dict[str, Any]:
    """Everything the UI needs to render one conversation (JSON-safe)."""
    snap = graph.get_state(config_for(thread_id))
    values = snap.values or {}
    draft = values.get("draft")
    if draft:
        parsed = Draft.model_validate(draft)
        draft = parsed.model_dump() | {
            "full_text": parsed.full_text(),
            "chars": len(parsed.full_text()),
        }
    topic = values.get("topic")
    image = values.get("image")
    if image:
        image = image | {"url": f"/api/images/{image['file']}"}
    return {
        "id": thread_id,
        "title": thread_title(values),
        "status": thread_status(snap),
        "niche": values.get("niche"),
        "messages": _messages(values.get("messages") or []),
        "topic": {"topic": topic} if isinstance(topic, str) else topic,
        "auto_topic": bool(values.get("auto_topic")),
        "research_brief": values.get("research_brief"),
        "draft": draft,
        "critique": values.get("critique"),
        "image": image,
        "revision_count": values.get("revision_count") or 0,
        "approved": bool(values.get("approved")),
        "final_post": values.get("final_post"),
        "publish_result": values.get("publish_result"),
        "activity": values.get("activity") or [],
        "last_error": values.get("last_error"),
        "pending": snap.interrupts[0].value if snap.interrupts else None,
    }


def _messages(messages) -> list[dict]:
    out = []
    for m in messages:
        if isinstance(m, HumanMessage):
            out.append({"role": "user", "content": str(m.content)})
        elif isinstance(m, AIMessage):
            out.append({"role": "assistant", "content": str(m.content)})
    return out
