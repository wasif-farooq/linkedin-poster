import logging
import time
from contextlib import contextmanager

import typer
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from app.config import DATA_DIR, get_settings
from app.llm.client import get_llm
from app.llm.structured import invoke_structured
from app.llm.usage import tracker

app = typer.Typer(help="Multi-agent LinkedIn post generator.", no_args_is_help=True)
dev = typer.Typer(help="Run a single agent on its own (for testing).", no_args_is_help=True)
app.add_typer(dev, name="dev")
console = Console()
LAST_BRIEF = DATA_DIR / "last_brief.json"


@app.callback()
def _main(verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging.")):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARNING)


@contextmanager
def llm_session(*, fatal: bool = True):
    """Reset the per-run LLM budget, turn quota errors into clean messages, print usage.
    With fatal=False (chat), errors are reported and swallowed so the REPL keeps going."""
    from app.services.errors import KNOWN_ERRORS, describe_error

    settings = get_settings()
    tracker.reset(
        max_calls=settings.max_llm_calls_per_run, max_searches=settings.max_searches_per_run
    )
    code = 0
    try:
        yield
    except KNOWN_ERRORS as exc:
        code, message = describe_error(exc) or (2, str(exc))
        console.print(f"[red]{escape(message)}[/red]")
    finally:
        console.print(f"[dim]{tracker.snapshot()}[/dim]")
    if code and fatal:
        raise typer.Exit(code)


class PingResult(BaseModel):
    greeting: str = Field(description="A one-sentence greeting")
    topic_idea: str = Field(description="One LinkedIn post topic idea about AI engineering")
    confidence: float = Field(ge=0, le=1, description="How good the idea is, 0-1")


@app.command()
def ping(model: str = typer.Option(None, help="Override the model for this call.")):
    """Check the LLM connection: one plain call and one structured call."""
    with llm_session():
        _ping(model)


def _ping(model: str | None) -> None:
    settings = get_settings()
    llm = get_llm(**({"model": model} if model else {}))
    console.print(f"Model: [bold]{llm.model_name}[/bold] @ {settings.opencode_base_url}")

    start = time.perf_counter()
    reply = llm.invoke([HumanMessage(content="Reply with exactly: pong")])
    console.print(
        Panel(str(reply.content).strip(), title=f"plain ({time.perf_counter() - start:.1f}s)")
    )

    start = time.perf_counter()
    result = invoke_structured(
        llm,
        PingResult,
        [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Greet me and suggest one LinkedIn post topic idea."),
        ],
    )
    console.print(
        Panel(
            result.model_dump_json(indent=2),
            title=f"structured PingResult ({time.perf_counter() - start:.1f}s)",
        )
    )
    console.print("[green]LLM connection OK[/green]")


@dev.command("scout")
def dev_scout(
    niche: str = typer.Option("ai engineering", "--niche", "-n", help="Niche to scout."),
    instructions: str = typer.Option("", "--instructions", "-i", help="Extra guidance."),
    show: int = typer.Option(15, help="How many candidates to list."),
    sources_only: bool = typer.Option(False, help="Only fetch candidates, skip the LLM."),
    research: bool = typer.Option(False, "--research", help="Then run the Researcher on it."),
):
    """Run the Topic Scout: fetch RSS + HN candidates and pick a topic."""
    from app.agents import topic_scout
    from app.tools.sources.candidates import collect_candidates
    from app.tools.sources.niches import load_niche

    cfg = load_niche(niche)
    console.print(
        f"Niche [bold]{cfg.name}[/bold]: {len(cfg.feeds)} feeds, {len(cfg.keywords)} HN keywords"
    )
    start = time.perf_counter()
    with console.status("Fetching candidates..."):
        candidates = collect_candidates(cfg)
    console.print(f"Fetched {len(candidates)} candidates in {time.perf_counter() - start:.1f}s")
    if not candidates:
        console.print("[red]No candidates found.[/red]")
        raise typer.Exit(1)
    _print_candidates(candidates[:show])
    if sources_only:
        return

    with llm_session():
        start = time.perf_counter()
        with console.status("Topic Scout is shortlisting..."):
            options = topic_scout.choose_topics(candidates, niche=niche, instructions=instructions)
        elapsed = time.perf_counter() - start
        for rank, option in enumerate(options, start=1):
            _print_topic(option, elapsed, rank=rank)
        choice = options[0]
        if research:
            _run_research(choice.topic, choice.angle, choice.source_urls, instructions)


@dev.command("research")
def dev_research(
    topic: str = typer.Option(..., "--topic", "-t", help="Topic to research."),
    angle: str = typer.Option("", "--angle", "-a", help="Point of view for the post."),
    url: list[str] = typer.Option(None, "--url", "-u", help="Seed article URL (repeatable)."),
    instructions: str = typer.Option("", "--instructions", "-i", help="Extra guidance."),
):
    """Run the Researcher: read seed articles, search the web, write a cited brief."""
    with llm_session():
        _run_research(topic, angle, url or [], instructions)


def _run_research(topic: str, angle: str, seed_urls: list[str], instructions: str):
    from app.agents import researcher

    start = time.perf_counter()
    with console.status("Researcher is reading and searching..."):
        brief = researcher.research(
            topic, angle=angle, seed_urls=seed_urls, instructions=instructions
        )
    _print_brief(brief, time.perf_counter() - start)
    LAST_BRIEF.parent.mkdir(parents=True, exist_ok=True)
    LAST_BRIEF.write_text(brief.model_dump_json(indent=2))
    console.print(f"[dim]Brief saved to {LAST_BRIEF.relative_to(DATA_DIR.parent)}[/dim]")
    return brief


@dev.command("write")
def dev_write(
    topic: str = typer.Option(None, "--topic", "-t", help="Research this topic first."),
    angle: str = typer.Option("", "--angle", "-a", help="Point of view for the post."),
    url: list[str] = typer.Option(None, "--url", "-u", help="Seed article URL (repeatable)."),
    instructions: str = typer.Option("", "--instructions", "-i", help="Extra guidance."),
    reuse_brief: bool = typer.Option(
        False, "--reuse-brief", help="Skip research; use the last saved brief (saves calls)."
    ),
    revisions: int = typer.Option(None, help="Max revisions (default: MAX_REVISIONS)."),
):
    """Run research (or reuse the last brief) -> Writer -> Critic -> revise loop."""
    from app.schemas.research import ResearchBrief

    if not topic and not reuse_brief:
        console.print(
            "[red]Pass --topic to research, or --reuse-brief to use the last brief.[/red]"
        )
        raise typer.Exit(1)
    if reuse_brief and not LAST_BRIEF.exists():
        console.print(
            "[red]No saved brief yet. Run `dev research` or `dev write --topic` first.[/red]"
        )
        raise typer.Exit(1)

    max_revisions = get_settings().max_revisions if revisions is None else revisions
    with llm_session():
        if reuse_brief:
            brief = ResearchBrief.model_validate_json(LAST_BRIEF.read_text())
            console.print(f"Using saved brief: [bold]{escape(brief.topic)}[/bold]")
        else:
            brief = _run_research(topic, angle, url or [], instructions)
        _write_and_review(brief, instructions, max_revisions)


def _write_and_review(brief, instructions: str, max_revisions: int) -> None:
    from app.agents import critic, writer
    from app.agents.context import format_feedback

    draft = None
    critique = None
    for attempt in range(max_revisions + 1):
        label = "Writing" if draft is None else f"Revising (#{attempt})"
        start = time.perf_counter()
        with console.status(f"Writer: {label.lower()}..."):
            draft = writer.write(
                brief,
                instructions=instructions,
                previous=draft,
                feedback=format_feedback(critique) if critique else None,
            )
        _print_draft(draft, f"{label} ({time.perf_counter() - start:.1f}s)")

        start = time.perf_counter()
        with console.status("Critic: reviewing..."):
            critique = critic.review(brief, draft)
        _print_critique(critique, time.perf_counter() - start)
        if critique.verdict == "pass":
            break

    if critique.verdict == "pass":
        console.print("[green bold]Critic passed the draft.[/green bold]")
    else:
        console.print(
            f"[yellow]Still 'revise' after {max_revisions} revision(s); "
            "a human would decide from here (Phase 5).[/yellow]"
        )


@app.command()
def chat(
    thread: str = typer.Option(None, "--thread", "-t", help="Resume a conversation by ID."),
    niche: str = typer.Option(None, "--niche", "-n", help="Niche for a new conversation."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Record 'published' posts locally instead of posting."
    ),
    auto_topic: bool = typer.Option(
        False, "--auto-topic", help="Let the Topic Scout pick instead of showing you a shortlist."
    ),
):
    """Chat with the Manager, who runs the Scout, Researcher, Writer and Critic for you."""
    import uuid

    if dry_run:
        get_settings().publish_dry_run = True
        console.print("[yellow]Dry run: nothing will be posted to LinkedIn.[/yellow]")
    from app.graph.builder import build_graph
    from app.graph.checkpointer import sqlite_checkpointer

    thread = thread or uuid.uuid4().hex[:8]
    config = {"configurable": {"thread_id": thread}}
    with sqlite_checkpointer() as saver:
        graph = build_graph(saver)
        existing = graph.get_state(config).values
        if niche and not existing.get("niche"):
            graph.update_state(config, {"niche": niche})
        _chat_banner(thread, existing)
        _handle_reviews(graph, config)  # a review may be waiting from a previous session
        while True:
            try:
                text = console.input("[bold cyan]you>[/bold cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break
            if not text:
                continue
            if text in ("/quit", "/exit", "/q"):
                break
            if text == "/draft":
                _show_current_draft(graph.get_state(config).values)
                continue
            if text == "/help":
                _chat_help()
                continue
            _chat_turn(graph, config, text, auto_topic)
    console.print(f"[dim]Resume with: linkedin-poster chat --thread {thread}[/dim]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Interface to bind (keep it local)."),
    port: int = typer.Option(8000, help="Port for the API."),
    reload: bool = typer.Option(False, help="Auto-reload on code changes (development)."),
):
    """Run the web API (the React UI talks to this)."""
    import uvicorn

    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print(
            f"[yellow]Warning: binding to {host}. The API has no login and can publish to your "
            "LinkedIn — anyone who can reach this port can use it.[/yellow]"
        )
    console.print(f"API on [bold]http://{host}:{port}[/bold]  (docs: /docs)")
    uvicorn.run("app.api.server:create_app", factory=True, host=host, port=port, reload=reload)


@app.command()
def resume(thread: str = typer.Option(..., "--thread", "-t", help="Conversation ID.")):
    """Continue a conversation, starting with any review that's waiting for you."""
    chat(thread=thread, niche=None, dry_run=False, auto_topic=False)


@app.command()
def threads(limit: int = typer.Option(10, help="How many to show.")):
    """List recent conversations (newest first) with their status."""
    from rich.table import Table

    from app.graph.builder import build_graph
    from app.graph.checkpointer import CHECKPOINT_DB, sqlite_checkpointer
    from app.services.threads import list_threads

    if not CHECKPOINT_DB.exists():
        console.print("[dim]No conversations yet.[/dim]")
        return
    labels = {
        "needs_review": "[magenta]waiting for your review[/magenta]",
        "confirm_publish": "[magenta]waiting for publish confirmation[/magenta]",
        "published": "[green]published[/green]",
        "approved": "[green]approved[/green]",
        "draft": "draft",
        "new": "-",
    }
    table = Table(title="Conversations")
    for col in ("Thread", "Topic", "Status"):
        table.add_column(col, overflow="fold")
    with sqlite_checkpointer() as saver:
        for t in list_threads(build_graph(saver), saver, limit):
            table.add_row(t["id"], escape(t["title"]), labels[t["status"]])
    console.print(table)


@app.command()
def doctor():
    """Check every dependency: model, feeds, Hacker News, web search, LinkedIn, storage."""
    from rich.table import Table

    from app.services.doctor import run_checks

    with llm_session(fatal=False), console.status("Running checks..."):
        results = run_checks()
    table = Table(title="linkedin-poster doctor")
    table.add_column("Check")
    table.add_column("")
    table.add_column("Detail", overflow="fold")
    marks = {"ok": "[green]✓[/green]", "warn": "[yellow]![/yellow]", "fail": "[red]✗[/red]"}
    for c in results:
        table.add_row(c.name, marks[c.status], escape(c.detail))
    console.print(table)
    if any(c.status == "fail" for c in results):
        raise typer.Exit(1)


@app.command()
def auth(status: bool = typer.Option(False, "--status", help="Show the current connection.")):
    """Connect your LinkedIn account (opens the browser; token lasts ~60 days)."""
    from app.tools.linkedin.client import LinkedInAuthError
    from app.tools.linkedin.oauth import TOKEN_PATH, load_token, run_auth_flow

    if status:
        try:
            token = load_token()
        except LinkedInAuthError as exc:
            console.print(f"[yellow]{exc}[/yellow]")
            raise typer.Exit(1) from None
        console.print(
            f"[green]Connected[/green] as [bold]{escape(token.name or token.member_id)}[/bold] "
            f"({token.author_urn}); token expires in {token.days_left} days."
        )
        return
    try:
        token = run_auth_flow(
            on_url=lambda url: console.print(
                "Opening LinkedIn in your browser. If it doesn't open, visit:\n"
                f"[link={url}]{escape(url)}[/link]"
            )
        )
    except LinkedInAuthError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(1) from None
    except OSError as exc:  # e.g. port 8765 already in use
        console.print(f"[red]Could not start the local callback server: {exc}[/red]")
        raise typer.Exit(1) from None
    console.print(
        f"[green]Connected[/green] as [bold]{escape(token.name)}[/bold]; "
        f"token saved to {TOKEN_PATH.relative_to(DATA_DIR.parent)} "
        f"(expires in {token.days_left} days)."
    )


@app.command()
def history(
    limit: int = typer.Option(20, help="How many posts to show."),
    all_: bool = typer.Option(False, "--all", help="Include dry runs."),
):
    """Posts you've published (newest first)."""
    from rich.table import Table

    from app.db.repository import PostRepository

    posts = PostRepository().list(limit, include_dry_runs=all_)
    if not posts:
        console.print("[dim]Nothing published yet.[/dim]")
        return
    table = Table(title="Post history")
    for col in ("When (UTC)", "Status", "Topic", "Link / URN"):
        table.add_column(col, overflow="fold")
    for p in posts:
        status = (
            "[green]published[/green]" if p.status == "published" else "[yellow]dry run[/yellow]"
        )
        table.add_row(p.created_at, status, escape(p.topic), escape(p.url or p.urn or "-"))
    console.print(table)


def _chat_banner(thread: str, existing: dict) -> None:
    status = "resumed" if existing.get("messages") else "new"
    console.print(
        Panel(
            f"Thread [bold]{thread}[/bold] ({status}). Talk to the Manager, e.g.\n"
            '  "find a trending topic and draft a post"\n'
            '  "write about <your topic>"   "make it shorter"   "show the sources"\n'
            "[dim]/draft shows the current draft · /help · /quit[/dim]",
            title="LinkedIn Poster — Manager",
            border_style="cyan",
        )
    )
    if existing.get("messages"):
        last = existing["messages"][-1]
        console.print(f"[dim]Last message: {escape(str(last.content)[:200])}[/dim]")


def _chat_help() -> None:
    console.print(
        "Ask the Manager in plain English. Commands: /draft (show current draft), /quit.\n"
        "Every new draft is shown to you for review: approve, edit, revise, reject, or later.\n"
        "Say 'let me review it' to bring a draft back for approval, and 'post it' to publish\n"
        "(you'll get a final yes/no). Run `linkedin-poster auth` once to connect LinkedIn."
    )


AGENT_LABELS = {
    "topic_scout": "🔎 Topic Scout",
    "topic_pick": "👤 Your pick",
    "researcher": "📚 Researcher",
    "writer": "✍️  Writer",
    "critic": "🧐 Critic",
    "human_review": "👤 Your review",
    "publisher": "🚀 Publisher",
}


def _chat_turn(graph, config, text: str, auto_topic: bool = False) -> None:
    from langchain_core.messages import HumanMessage

    from app.graph.state import new_turn

    before = graph.get_state(config).values
    shown = {"activity": 0, "draft_reviewed": False}
    try:
        _run_graph(
            graph, config, new_turn(HumanMessage(content=text)) | {"auto_topic": auto_topic}, shown
        )
        _handle_reviews(graph, config, shown)
    except KeyboardInterrupt:
        console.print(
            "\n[yellow]Interrupted. Your work so far is saved; send a new message to continue.[/yellow]"
        )
    except Exception as exc:  # noqa: BLE001 - keep the chat alive on unexpected bugs
        logging.getLogger(__name__).debug("Turn failed", exc_info=True)
        console.print(
            f"[red]Unexpected error: {escape(str(exc)) or type(exc).__name__}[/red] "
            "[dim](run with -v for details; your conversation is saved)[/dim]"
        )
    _show_turn_result(graph, config, before, shown)


def _run_graph(graph, config, graph_input, shown: dict) -> None:
    """Stream one graph run (a new turn or a resume), printing agent progress."""
    with llm_session(fatal=False):
        status = console.status("Manager is thinking...")
        status.start()
        try:
            for chunk in graph.stream(graph_input, config, stream_mode="updates"):
                for node, update in chunk.items():
                    if node != "__interrupt__":
                        _show_progress(node, update or {}, status, shown)
        finally:
            status.stop()


def _handle_reviews(graph, config, shown: dict | None = None) -> None:
    """While the graph is paused for review, ask the human and resume with their decision."""
    from langgraph.types import Command

    shown = shown if shown is not None else {"activity": 0, "draft_reviewed": False}
    while True:
        interrupts = graph.get_state(config).interrupts
        if not interrupts:
            return
        payload = interrupts[0].value
        if payload.get("type") == "publish_confirm":
            answer = _ask_publish(payload)
        elif payload.get("type") == "topic_choice":
            answer = _ask_topic(payload)
        else:
            answer = _ask_review(payload)
        if answer is None:
            thread = config["configurable"]["thread_id"]
            console.print(
                "[dim]Review left pending. Resume it any time with "
                f"`linkedin-poster resume --thread {thread}` "
                "(sending a new message instead starts a new turn; the draft is kept).[/dim]"
            )
            return
        shown["draft_reviewed"] = True
        _run_graph(graph, config, Command(resume=answer), shown)


def _ask_review(payload: dict) -> dict | None:
    """Show the draft for approval; returns a ReviewAction dict, or None for 'later'."""
    lines = [escape(payload["post"])]
    footer = [f"{payload['chars']} chars"]
    if payload.get("critic_verdict"):
        scores = " ".join(f"{k} {v}" for k, v in (payload.get("critic_scores") or {}).items())
        footer.append(f"critic: {payload['critic_verdict']} ({scores})")
    console.print(
        Panel(
            "\n".join(lines),
            title="Review draft",
            subtitle=" · ".join(footer),
            border_style="magenta",
            width=min(console.width, 90),
        )
    )
    for issue in payload.get("critic_issues") or []:
        console.print(f"[dim]critic: {escape(issue)}[/dim]")
    for err in payload.get("rule_errors") or []:
        console.print(f"[red]✗ {escape(err)}[/red]")

    can_approve = payload.get("can_approve", True)
    options = escape(
        ("[a]pprove  " if can_approve else "") + "[e]dit  [r]evise  [x] reject  [l]ater"
    )
    while True:
        try:
            choice = console.input(f"[bold magenta]{options}>[/bold magenta] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return None
        if choice in ("a", "approve") and can_approve:
            return {"action": "approve"}
        if choice in ("e", "edit"):
            text = _edit_text(payload["post"])
            if text and text.strip() != payload["post"].strip():
                return {"action": "edit", "text": text}
            console.print("[dim]No changes made.[/dim]")
        elif choice in ("r", "revise"):
            feedback = console.input("What should the Writer change? ").strip()
            if feedback:
                return {"action": "revise", "text": feedback}
        elif choice in ("x", "reject"):
            return {"action": "reject"}
        elif choice in ("l", "later"):
            return None


def _ask_topic(payload: dict) -> dict | None:
    """Show the Scout's shortlist; returns a TopicPickAnswer dict, or None for 'later'."""
    from rich.table import Table

    table = Table(title="Pick a topic", show_lines=True)
    table.add_column("#", justify="right")
    table.add_column("Topic & angle", overflow="fold")
    table.add_column("Why now", overflow="fold")
    for o in payload["options"]:
        table.add_row(
            str(o["id"] + 1),
            f"[bold]{escape(o['topic'])}[/bold]\n[dim]{escape(o['angle'])}[/dim]",
            escape(o["why_now"]),
        )
    console.print(table)
    count = len(payload["options"])
    prompt = escape(f"[1-{count}] pick  [m]ore topics  [t]ype your own  [l]ater> ")
    while True:
        try:
            choice = console.input(f"[bold magenta]{prompt}[/bold magenta]").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return None
        if choice.isdigit() and 1 <= int(choice) <= count:
            return {"choice": int(choice) - 1}
        if choice in ("m", "more"):
            hint = console.input("Any direction? (optional, Enter to skip) ").strip()
            return {"more": True, "hint": hint or None}
        if choice in ("t", "type"):
            topic = console.input("Your topic: ").strip()
            if topic:
                return {"topic": topic}
        elif choice in ("l", "later"):
            return None


def _ask_publish(payload: dict) -> dict | None:
    """Final yes/no before a real LinkedIn post. Default is no."""
    console.print(
        Panel(
            escape(payload["post"]),
            title=f"Publish to LinkedIn as {escape(payload.get('account') or 'you')}?",
            subtitle=f"{payload['chars']} chars · public post",
            border_style="red",
            width=min(console.width, 90),
        )
    )
    try:
        choice = console.input(escape("[y] publish now  [n] not now  [l]ater> ")).strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return None
    if choice in ("l", "later"):
        return None
    return {"confirm": choice in ("y", "yes")}


def _edit_text(text: str) -> str | None:
    """Open $EDITOR on the post; fall back to pasting in the terminal."""
    try:
        return typer.edit(text, extension=".txt")
    except Exception:  # noqa: BLE001 - no usable editor
        console.print("Paste the full post, then a line with a single '.' to finish:")
        lines = []
        while (line := console.input()) != ".":
            lines.append(line)
        return "\n".join(lines)


def _show_turn_result(graph, config, before: dict, shown: dict) -> None:
    state = graph.get_state(config).values
    if (
        state.get("draft")
        and state.get("draft") != before.get("draft")
        and not shown["draft_reviewed"]
    ):
        _show_current_draft(state)
    if state.get("approved") and not before.get("approved"):
        console.print(
            Panel(
                escape(state["final_post"]),
                title="✅ Approved final post",
                border_style="green",
                width=min(console.width, 90),
            )
        )
    result = state.get("publish_result") or {}
    if result != (before.get("publish_result") or {}):
        if result.get("status") == "published":
            console.print(f"[green bold]🚀 Published:[/green bold] {escape(result['url'])}")
        elif result.get("status") == "dry_run":
            console.print("[yellow]Dry run: recorded in history, not posted.[/yellow]")
        elif result.get("status") == "already_published":
            console.print(
                f"[yellow]Already published earlier:[/yellow] {escape(result.get('url') or '')}"
            )
        elif result.get("status") == "cancelled":
            console.print("[dim]Publishing cancelled.[/dim]")
    messages = state.get("messages") or []
    if (
        len(messages) > len(before.get("messages") or [])
        and getattr(messages[-1], "name", None) == "manager"
    ):
        console.print(
            Panel(escape(str(messages[-1].content)), title="Manager", border_style="cyan")
        )


def _show_progress(node: str, update: dict, status, shown: dict) -> None:
    if node == "manager":
        plan = update.get("plan") or []
        if plan:
            steps = " → ".join(AGENT_LABELS.get(p, p) for p in plan)
            note = f" [dim]{escape(update['reply'])}[/dim]" if update.get("reply") else ""
            console.print(f"[cyan]Manager plan:[/cyan] {steps}{note}")
            status.update("Working...")
    elif node == "dispatch":
        nxt = update.get("next")
        if nxt in AGENT_LABELS:
            status.update(f"{AGENT_LABELS[nxt]} is working...")
        elif nxt == "manager":
            status.update("Manager is reviewing the results...")
    elif node in AGENT_LABELS:
        activity = update.get("activity") or []
        for line in activity[shown["activity"] :]:
            mark = "[red]✗[/red]" if "FAILED" in line else "[green]✓[/green]"
            console.print(f"  {mark} {escape(line)}")
        shown["activity"] = len(activity)
        if update.get("last_error"):
            console.print(f"  [red]{escape(update['last_error'])}[/red]")


def _show_current_draft(state: dict) -> None:
    from app.schemas.post import Critique, Draft

    if not state.get("draft"):
        console.print("[dim]No draft yet.[/dim]")
        return
    _print_draft(Draft.model_validate(state["draft"]), "current")
    if state.get("critique"):
        c = Critique.model_validate(state["critique"])
        color = "green" if c.verdict == "pass" else "yellow"
        scores = "  ".join(f"{k} {v}" for k, v in c.scores.model_dump().items())
        console.print(f"[{color}]Critic: {c.verdict.upper()}[/{color}]  {scores}")


def _print_draft(draft, title: str) -> None:
    text = draft.full_text()
    console.print(
        Panel(
            escape(text),
            title=f"Draft — {title}",
            subtitle=f"{len(text)} chars · sources {draft.source_ids or '-'}",
            border_style="blue",
            width=min(console.width, 90),
        )
    )


def _print_critique(critique, elapsed: float) -> None:
    color = "green" if critique.verdict == "pass" else "yellow"
    scores = "  ".join(f"{k} {v}" for k, v in critique.scores.model_dump().items())
    lines = [f"[bold {color}]{critique.verdict.upper()}[/bold {color}]   {scores}"]
    for e in critique.rule_errors:
        lines.append(f"[red]✗ {escape(e)}[/red]")
    for w in critique.rule_warnings:
        lines.append(f"[yellow]! {escape(w)}[/yellow]")
    for i in critique.issues:
        lines.append(f"• {escape(i)}")
    for sug in critique.suggestions:
        lines.append(f"[dim]→ {escape(sug)}[/dim]")
    console.print(Panel("\n".join(lines), title=f"Critique ({elapsed:.1f}s)", border_style=color))


def _print_brief(brief, elapsed: float) -> None:
    from rich.table import Table

    def cite(ids):  # escaped so "[1]" isn't read as rich markup
        return " " + escape("".join(f"[{i}]" for i in ids)) if ids else ""

    lines = [
        f"[bold]{escape(brief.topic)}[/bold]",
        "",
        escape(brief.summary),
        "",
        "[cyan]Key points[/cyan]",
    ]
    lines += [f"  • {escape(kp.point)}{cite(kp.source_ids)}" for kp in brief.key_points]
    if brief.stats:
        lines += ["", "[cyan]Stats & facts[/cyan]"]
        lines += [f"  • {escape(st.fact)}{cite(st.source_ids)}" for st in brief.stats]
    if brief.counterpoints:
        lines += ["", "[cyan]Counterpoints[/cyan]"]
        lines += [f"  • {escape(c.point)}{cite(c.source_ids)}" for c in brief.counterpoints]
    if brief.queries:
        lines += ["", f"[dim]Queries: {escape(' | '.join(brief.queries))}[/dim]"]
    console.print(
        Panel("\n".join(lines), title=f"Research brief ({elapsed:.1f}s)", border_style="green")
    )

    table = Table(title="Cited sources")
    table.add_column("#", justify="right")
    table.add_column("Title / URL", overflow="fold")
    table.add_column("From")
    table.add_column("Full text")
    for s in brief.sources:
        table.add_row(
            str(s.id),
            f"{escape(s.title)}\n[dim]{escape(s.url)}[/dim]",
            s.origin,
            "yes" if s.full_text else "snippet",
        )
    console.print(table)


def _print_topic(choice, elapsed: float, rank: int = 1) -> None:
    body = (
        f"[bold]{escape(choice.topic)}[/bold]\n\n"
        f"[cyan]Angle:[/cyan] {escape(choice.angle)}\n"
        f"[cyan]Why now:[/cyan] {escape(choice.why_now)}\n"
        f"[cyan]Audience:[/cyan] {escape(choice.audience)}\n\n"
        f"[cyan]Based on:[/cyan] {', '.join(f'#{i}' for i in choice.chosen_ids)}\n"
        + "\n".join(
            f"  • {escape(t)}\n    {escape(u)}"
            for t, u in zip(choice.source_titles, choice.source_urls, strict=True)
        )
        + f"\n[cyan]Runner-ups:[/cyan] {', '.join(f'#{i}' for i in choice.runner_up_ids) or '-'}"
    )
    title = f"#{rank} — best pick ({elapsed:.1f}s)" if rank == 1 else f"#{rank}"
    console.print(Panel(body, title=title, border_style="green" if rank == 1 else "blue"))


def _print_candidates(candidates) -> None:
    from rich.table import Table

    table = Table(show_lines=False)
    table.add_column("#", justify="right")
    table.add_column("Title", overflow="fold")
    table.add_column("Source")
    table.add_column("KW", justify="right")
    table.add_column("HN pts", justify="right")
    table.add_column("Date")
    for i, c in enumerate(candidates, start=1):
        table.add_row(
            str(i),
            escape(c.title),
            c.source[:28],
            str(c.keyword_hits),
            "" if c.points is None else str(c.points),
            (c.published or "")[:10],
        )
    console.print(table)


if __name__ == "__main__":
    app()
