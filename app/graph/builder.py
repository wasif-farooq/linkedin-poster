"""Wires the Manager, dispatcher and workers into a LangGraph StateGraph.

START -> begin_turn -> manager -> (plan?) -> dispatch -> worker -> dispatch -> ...
      -> manager -> respond -> END
"""

import logging
from collections.abc import Callable, Mapping
from importlib import import_module

import openai
from langchain_core.messages import AIMessage
from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph

from app.agents.manager import TOPIC_RESET
from app.graph.routing import after_critic, dispatch, route_after_dispatch, route_after_manager
from app.graph.state import HUMAN_STEPS, STEPS, TURN_RESET, WORKERS, PostState
from app.llm.client import MissingAPIKeyError
from app.llm.usage import LLMBudgetExceededError

log = logging.getLogger(__name__)

# Must propagate: GraphBubbleUp is LangGraph's interrupt/control-flow signal (it subclasses
# Exception!), the rest end the turn because another LLM call can't fix them.
FATAL = (
    GraphBubbleUp,
    LLMBudgetExceededError,
    openai.RateLimitError,
    openai.AuthenticationError,
    openai.PermissionDeniedError,
    MissingAPIKeyError,
)


def build_graph(checkpointer=None):
    graph = StateGraph(PostState)
    graph.add_node("begin_turn", begin_turn)
    graph.add_node("manager", _call("manager"))
    graph.add_node("dispatch", dispatch)
    graph.add_node("respond", respond)
    for name in WORKERS:
        graph.add_node(name, _worker(name))
        graph.add_edge(name, "dispatch")
    for name in HUMAN_STEPS:
        graph.add_node(name, _human_node(name))
        graph.add_edge(name, "dispatch")

    graph.add_edge(START, "begin_turn")
    graph.add_edge("begin_turn", "manager")
    graph.add_conditional_edges("manager", route_after_manager, ["dispatch", "respond"])
    graph.add_conditional_edges("dispatch", route_after_dispatch, [*STEPS, "manager"])
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=checkpointer)


def begin_turn(state: Mapping) -> dict:
    """Every new user message starts here (resuming a paused review does not)."""
    return dict(TURN_RESET)


def respond(state: Mapping) -> dict:
    reply = state.get("reply") or "Done. What would you like next?"
    return {"messages": [AIMessage(content=reply, name="manager")], "plan": [], "reply": None}


def _call(agent: str) -> Callable[[Mapping], dict]:
    """Resolve `app.agents.<agent>.run` at call time (keeps agents patchable in tests)."""

    def node(state: Mapping) -> dict:
        return import_module(f"app.agents.{agent}").run(state)

    node.__name__ = agent
    return node


def _worker(name: str) -> Callable[[Mapping], dict]:
    run = _call(name)

    def node(state: Mapping) -> dict:
        steps = (state.get("step_count") or 0) + 1
        activity = list(state.get("activity") or [])
        try:
            update = run(state)
        except FATAL:
            raise
        except Exception as exc:  # noqa: BLE001 - reported to the Manager, who tells the user
            log.warning("%s failed: %s", name, exc, exc_info=True)
            return {
                "step_count": steps,
                "plan": [],
                "last_error": f"{name} failed: {exc}",
                "activity": [*activity, f"{name}: FAILED"],
            }

        update = dict(update)
        if name == "topic_scout":
            update = TOPIC_RESET | update  # new topic: old brief/draft no longer apply
            if update.get("topic") is None and update.get("topic_options"):
                # Shortlisted rather than picked: the user chooses before anything else runs.
                update["plan"] = ["topic_pick", *(state.get("plan") or [])]
        elif name == "researcher":
            update.setdefault("critique", None)
        elif name == "writer":
            # Safety invariant, enforced here rather than trusted to the agent:
            # a new draft always needs a fresh human approval.
            update |= {
                "approved": False,
                "final_post": None,
                "post_urn": None,
                "post_url": None,
                "publish_result": None,
            }
        note = None
        if name == "critic":
            update["plan"], note = after_critic(state, update["critique"])

        activity.append(describe(name, update, state))
        if note:
            activity.append(note)
        return update | {"step_count": steps, "activity": activity}

    node.__name__ = name
    return node


def _human_node(name: str) -> Callable[[Mapping], dict]:
    """Steps that pause for the user manage their own activity lines; errors other than the
    interrupt (e.g. nothing to review) are reported to the Manager like a worker failure."""
    run = _call(name)

    def human_node(state: Mapping) -> dict:
        steps = (state.get("step_count") or 0) + 1
        try:
            return run(state) | {"step_count": steps}
        except FATAL:
            raise
        except Exception as exc:  # noqa: BLE001
            return {
                "step_count": steps,
                "plan": [],
                "last_error": f"{name} failed: {exc}",
                "activity": [*(state.get("activity") or []), f"{name}: FAILED"],
            }

    human_node.__name__ = name
    return human_node


def describe(name: str, update: Mapping, state: Mapping) -> str:
    """One-line summary of what a worker did (shown in the CLI and to the Manager)."""
    if name == "topic_scout":
        if update.get("topic"):
            return f"topic_scout: picked '{update['topic']['topic']}'"
        return f"topic_scout: shortlisted {len(update.get('topic_options') or [])} topics"
    if name == "researcher":
        brief = update["research_brief"]
        return (
            f"researcher: brief with {len(brief['key_points'])} key points "
            f"from {len(brief['sources'])} sources"
        )
    if name == "writer":
        verb = "revised" if state.get("draft") else "wrote"
        text = update["draft"]["text"]
        return f"writer: {verb} the draft (~{len(text)} chars)"
    if name == "critic":
        c = update["critique"]
        low_name, low = min(c["scores"].items(), key=lambda kv: kv[1])
        return f"critic: {c['verdict']} (lowest: {low_name} {low})"
    if name == "illustrator":
        image = update["image"]
        return f"illustrator: made an image ({image['provider']}) — {image['alt_text']}"
    if name == "publisher":
        r = update["publish_result"]
        if r["status"] == "share_ready":
            return "publisher: share link ready — open it and press Post on LinkedIn"
        return f"publisher: {r['status']}" + (f" ({r['url']})" if r.get("url") else "")
    return f"{name}: done"
