"""Health checks for every dependency (shared by `linkedin-poster doctor` and the web UI)."""

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal

from app.config import DATA_DIR, get_settings

Status = Literal["ok", "warn", "fail"]


@dataclass
class Check:
    name: str
    status: Status
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def run_checks() -> list[Check]:
    checks: list[tuple[str, Callable[[], tuple[Status, str]]]] = [
        ("Language model", _model),
        ("RSS feeds", _rss),
        ("Hacker News", _hn),
        ("Web search", _search),
        ("LinkedIn", _linkedin),
        ("Local storage", _storage),
    ]
    results = []
    for name, fn in checks:
        try:
            status, detail = fn()
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            status, detail = "fail", f"{type(exc).__name__}: {exc}"
        results.append(Check(name, status, detail))
    return results


def _model() -> tuple[Status, str]:
    from app.llm.client import get_llm

    llm = get_llm(max_tokens=2000)
    start = time.perf_counter()
    reply = str(llm.invoke("Reply with exactly: ok").content).strip()
    detail = f"{llm.model_name} replied in {time.perf_counter() - start:.1f}s"
    return ("ok" if reply else "fail"), detail


def _rss() -> tuple[Status, str]:
    from app.tools.sources import feeds
    from app.tools.sources.niches import load_niche

    url = load_niche("ai engineering").feeds[0]
    items = feeds.fetch_feed(url, max_age_days=30)
    return ("ok" if items else "fail"), f"{len(items)} items from {url}"


def _hn() -> tuple[Status, str]:
    from app.tools.sources import hackernews

    items = hackernews.front_page(limit=5)
    return ("ok" if items else "fail"), f"{len(items)} front-page stories"


def _search() -> tuple[Status, str]:
    from app.tools.sources import web_search

    hits = web_search.search("LangGraph multi-agent", max_results=3)
    return ("ok" if hits else "fail"), f"{len(hits)} results via {get_settings().search_provider}"


def _linkedin() -> tuple[Status, str]:
    status = linkedin_status()
    if not status["configured"]:
        return "warn", "LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET not set (needed to publish)"
    if not status["connected"]:
        return "fail", status["error"]
    warn = status["days_left"] < 7
    detail = f"connected as {status['name']}; token expires in {status['days_left']} days"
    return ("warn" if warn else "ok"), detail + (" — reconnect soon" if warn else "")


def _storage() -> tuple[Status, str]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    probe = DATA_DIR / ".doctor"
    probe.write_text("ok")
    probe.unlink()
    return "ok", f"{DATA_DIR} is writable"


def linkedin_status() -> dict:
    """Connection info without calling LinkedIn (token file only)."""
    from app.tools.linkedin.client import LinkedInAuthError
    from app.tools.linkedin.oauth import load_token

    settings = get_settings()
    configured = bool(settings.linkedin_client_id and settings.linkedin_client_secret)
    try:
        token = load_token()
    except LinkedInAuthError as exc:
        return {"configured": configured, "connected": False, "error": str(exc)}
    return {
        "configured": configured,
        "connected": True,
        "name": token.name or token.member_id,
        "author_urn": token.author_urn,
        "days_left": token.days_left,
    }
