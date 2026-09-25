from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

# Wrapped agents
WORKERS = ("topic_scout", "researcher", "writer", "critic", "illustrator", "publisher")
HUMAN_STEPS = ("topic_pick", "human_review")  # pause for the user via interrupt()
STEPS = (*WORKERS, *HUMAN_STEPS)  # everything the dispatcher can route to


class PostState(TypedDict, total=False):
    # Conversation (persisted across turns by the checkpointer)
    messages: Annotated[list[AnyMessage], add_messages]

    # Work products (plain dicts so checkpoints stay JSON-friendly)
    niche: str
    candidates: list[dict[str, Any]]
    auto_topic: bool  # True: the Scout picks; False: the user picks from topic_options
    topic_options: list[dict[str, Any]] | None
    excluded_topics: list[str]  # shortlisted and passed over ("find more")
    topic: dict[str, Any] | str | None
    research_brief: dict[str, Any] | None
    draft: dict[str, Any] | None
    critique: dict[str, Any] | None
    image: dict[str, Any] | None  # PostImage; the file is in data/images
    revision_count: int
    human_feedback: str | None
    recent_topics: list[str]

    # Manager -> workers
    instructions: str
    plan: list[str]  # remaining worker steps for this turn
    next: str  # set by the dispatcher

    # Per-turn bookkeeping (reset with every user message)
    step_count: int
    manager_calls: int
    activity: list[str]  # what the workers did this turn, shown to the Manager
    last_error: str | None
    reply: str | None

    # Approval + publishing
    approved: bool
    final_post: str | None
    post_urn: str | None
    post_url: str | None
    publish_result: dict[str, Any] | None  # {"status": published|dry_run|cancelled|..., ...}


TURN_RESET = {
    "plan": [],
    "step_count": 0,
    "manager_calls": 0,
    "activity": [],
    "last_error": None,
    "reply": None,
}


def new_turn(user_message) -> dict:
    """Input for one chat turn. Per-turn counters are reset inside the graph (begin_turn),
    so any client -- CLI, LangGraph Studio, API -- only needs to send the message."""
    return {"messages": [user_message]}
