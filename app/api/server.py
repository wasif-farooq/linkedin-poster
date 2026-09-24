"""HTTP API for the web UI: REST endpoints + Server-Sent Events for live agent progress.

Runs are serialized (one at a time): LLM/search budgets and the dry-run flag are
process-wide. Bind to localhost only: the API can publish to your LinkedIn and has no auth.
"""

import dataclasses
import json
import logging
import threading
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager, nullcontext
from typing import Any

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.config import get_settings
from app.db.repository import PostRepository
from app.graph.builder import build_graph
from app.graph.checkpointer import sqlite_checkpointer
from app.graph.state import new_turn
from app.llm.usage import tracker
from app.services.doctor import linkedin_status, run_checks
from app.services.errors import KNOWN_ERRORS, describe_error
from app.services.threads import (
    THREAD_ID_PATTERN,
    config_for,
    list_threads,
    thread_snapshot,
)

log = logging.getLogger(__name__)

DEV_ORIGINS = [  # Vite dev server (default port 5180; 5173 kept for other setups)
    "http://localhost:5180",
    "http://127.0.0.1:5180",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
MAX_VOICE_CHARS = 10_000
ThreadId = Path(pattern=THREAD_ID_PATTERN)


# --- request bodies ----------------------------------------------------------------------


class NewThread(BaseModel):
    niche: str | None = Field(default=None, max_length=100)


class SendMessage(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    dry_run: bool = False


class ResumeRun(BaseModel):
    answer: dict[str, Any]  # ReviewAction ({"action": ..., "text": ...}) or {"confirm": bool}
    dry_run: bool = False


class VoiceText(BaseModel):
    text: str = Field(max_length=MAX_VOICE_CHARS)


# --- runner ------------------------------------------------------------------------------


class Runner:
    """The compiled graph plus a lock so only one run happens at a time."""

    def __init__(self, checkpointer):
        self.checkpointer = checkpointer
        self.graph = build_graph(checkpointer)
        self.lock = threading.Lock()

    def events(self, thread_id: str, graph_input, dry_run: bool) -> Iterator[str]:
        """SSE stream of one graph run: start, step*, interrupt?, error?, done."""
        if not self.lock.acquire(blocking=False):  # acquired here so a dropped client can't leak it
            yield _sse(
                "error", {"message": "Another run is in progress. Try again when it finishes."}
            )
            return
        settings = get_settings()
        previous_dry_run = settings.publish_dry_run
        settings.publish_dry_run = dry_run
        tracker.reset(
            max_calls=settings.max_llm_calls_per_run, max_searches=settings.max_searches_per_run
        )
        config = config_for(thread_id)
        shown = len(self.graph.get_state(config).values.get("activity") or [])
        try:
            yield _sse("start", {"thread_id": thread_id})
            for chunk in self.graph.stream(graph_input, config, stream_mode="updates"):
                for node, update in chunk.items():
                    if node == "__interrupt__":
                        yield _sse("interrupt", update[0].value)
                        continue
                    if node == "begin_turn":
                        shown = 0
                    event, shown = _step_event(node, update or {}, shown)
                    yield _sse("step", event)
        except KNOWN_ERRORS as exc:
            _, message = describe_error(exc) or (2, str(exc))
            yield _sse("error", {"message": message})
        except Exception as exc:  # noqa: BLE001 - never leave the UI hanging
            log.exception("Run failed")
            yield _sse("error", {"message": f"Unexpected error: {exc}"})
        finally:
            settings.publish_dry_run = previous_dry_run
            self.lock.release()
        yield _sse(
            "done",
            {
                "thread": thread_snapshot(self.graph, thread_id),
                "usage": dataclasses.asdict(tracker.snapshot()),
            },
        )


def _step_event(node: str, update: dict, shown: int) -> tuple[dict, int]:
    event: dict[str, Any] = {"node": node}
    if node == "manager":
        event["plan"] = update.get("plan") or []
        event["reply"] = update.get("reply")
    elif node == "dispatch":
        event["next"] = update.get("next")
    activity = update.get("activity")
    if activity is not None:
        event["activity"] = activity[shown:]
        shown = len(activity)
    if update.get("last_error"):
        event["error"] = update["last_error"]
    return event, shown


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _stream(iterator: Iterator[str]) -> StreamingResponse:
    return StreamingResponse(
        iterator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- LinkedIn connect (OAuth runs its own localhost callback server) ----------------------


class LinkedInConnect:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.url: str | None = None
        self.error: str | None = None

    def start(self, timeout: float = 10) -> dict:
        from app.tools.linkedin.oauth import run_auth_flow

        with self.lock:
            if self.running:
                return self.state()
            self.running, self.url, self.error = True, None, None
        got_url = threading.Event()

        def on_url(url: str) -> None:
            self.url = url
            got_url.set()

        def worker() -> None:
            try:
                run_auth_flow(open_browser=False, on_url=on_url)
            except Exception as exc:  # noqa: BLE001 - surfaced via GET /api/linkedin
                self.error = str(exc)
            finally:
                self.running = False
                got_url.set()

        threading.Thread(target=worker, daemon=True).start()
        got_url.wait(timeout)
        return self.state()

    def state(self) -> dict:
        return {"running": self.running, "authorize_url": self.url, "error": self.error}


# --- app ---------------------------------------------------------------------------------


def create_app(checkpointer=None) -> FastAPI:
    """`checkpointer=None` opens the SQLite checkpointer in data/ for the app's lifetime."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx = sqlite_checkpointer() if checkpointer is None else nullcontext(checkpointer)
        with ctx as saver:
            app.state.runner = Runner(saver)
            app.state.linkedin = LinkedInConnect()
            yield

    app = FastAPI(title="LinkedIn Poster API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type"],
    )

    def runner() -> Runner:
        return app.state.runner

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "busy": runner().lock.locked()}

    # threads ---------------------------------------------------------------------------

    @app.get("/api/threads")
    def get_threads(limit: int = Query(30, ge=1, le=200)) -> list[dict]:
        r = runner()
        return list_threads(r.graph, r.checkpointer, limit)

    @app.post("/api/threads", status_code=201)
    def create_thread(body: NewThread) -> dict:
        thread_id = uuid.uuid4().hex[:8]
        if body.niche and body.niche.strip():
            runner().graph.update_state(config_for(thread_id), {"niche": body.niche.strip()})
        return {"id": thread_id}

    @app.get("/api/threads/{thread_id}")
    def get_thread(thread_id: str = ThreadId) -> dict:
        return thread_snapshot(runner().graph, thread_id)

    @app.post("/api/threads/{thread_id}/messages")
    def send_message(body: SendMessage, thread_id: str = ThreadId) -> StreamingResponse:
        r = _require_idle(runner())
        graph_input = new_turn(HumanMessage(content=body.text.strip()))
        return _stream(r.events(thread_id, graph_input, body.dry_run))

    @app.post("/api/threads/{thread_id}/resume")
    def resume(body: ResumeRun, thread_id: str = ThreadId) -> StreamingResponse:
        r = _require_idle(runner())
        if not r.graph.get_state(config_for(thread_id)).interrupts:
            raise HTTPException(409, "Nothing is waiting for a decision in this conversation.")
        return _stream(r.events(thread_id, Command(resume=body.answer), body.dry_run))

    # history, health, settings ---------------------------------------------------------

    @app.get("/api/history")
    def history(limit: int = Query(50, ge=1, le=500), include_dry_runs: bool = True) -> list[dict]:
        posts = PostRepository().list(limit, include_dry_runs=include_dry_runs)
        return [dataclasses.asdict(p) for p in posts]

    @app.get("/api/doctor")
    def doctor() -> list[dict]:
        r = _require_idle(runner())
        with r.lock:
            tracker.reset(max_calls=5, max_searches=1)
            return [c.to_dict() for c in run_checks()]

    @app.get("/api/linkedin")
    def linkedin() -> dict:
        return linkedin_status() | {"auth_flow": app.state.linkedin.state()}

    @app.post("/api/linkedin/connect")
    def linkedin_connect() -> dict:
        state = app.state.linkedin.start()
        if state["error"] and not state["authorize_url"]:
            raise HTTPException(400, state["error"])
        return state

    @app.get("/api/settings")
    def settings_view() -> dict:
        s = get_settings()
        return {
            "default_model": s.default_model,
            "role_models": {
                role: s.model_for(role)
                for role in ("manager", "topic_scout", "researcher", "writer", "critic")
            },
            "fallback_models": s.fallback_model_list(),
            "limits": {
                "llm_requests_per_minute": s.llm_requests_per_minute,
                "max_llm_calls_per_run": s.max_llm_calls_per_run,
                "max_searches_per_run": s.max_searches_per_run,
                "max_revisions": s.max_revisions,
                "critic_min_score": s.critic_min_score,
                "llm_max_tokens": s.llm_max_tokens,
            },
            "linkedin_version": s.linkedin_version,
            "publish_dry_run": s.publish_dry_run,
        }

    @app.get("/api/voice")
    def get_voice() -> dict:
        path = get_settings().voice_path
        return {"text": path.read_text(encoding="utf-8") if path.exists() else ""}

    @app.put("/api/voice")
    def put_voice(body: VoiceText) -> dict:
        path = get_settings().voice_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body.text, encoding="utf-8")
        return {"text": body.text}

    return app


def _require_idle(r: Runner) -> Runner:
    if r.lock.locked():
        raise HTTPException(409, "Another run is in progress. Try again when it finishes.")
    return r
