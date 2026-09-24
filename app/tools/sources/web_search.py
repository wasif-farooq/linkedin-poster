"""Free web/news search (no API key) with disk cache, pacing and backoff.

Default provider is `ddgs` (DuckDuckGo metasearch). It's unofficial and throttles
bursts, so every query is cached, spaced out, and retried with backoff.
Add another provider by implementing `SearchProvider` and registering it in PROVIDERS.
"""

import hashlib
import json
import logging
import threading
import time
from typing import Literal, Protocol

from app.config import DATA_DIR, get_settings
from app.llm.usage import tracker
from app.schemas.research import SearchResult

log = logging.getLogger(__name__)

Kind = Literal["web", "news"]
CACHE_DIR = DATA_DIR / "cache" / "search"


class SearchError(RuntimeError):
    pass


class SearchProvider(Protocol):
    name: str

    def search(
        self, query: str, *, kind: Kind, max_results: int, timelimit: str | None
    ) -> list[SearchResult]: ...


class DDGSProvider:
    name = "ddgs"

    def search(self, query, *, kind, max_results, timelimit):
        from ddgs import DDGS
        from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException

        client = DDGS()
        method = client.news if kind == "news" else client.text
        try:
            rows = method(query, max_results=max_results, timelimit=timelimit)
        except (RatelimitException, TimeoutException):
            raise  # retried by the caller
        except DDGSException as exc:
            if "no results" in str(exc).lower():
                return []
            raise
        return [
            SearchResult(
                title=r.get("title") or "",
                url=r.get("href") or r.get("url") or "",
                snippet=r.get("body") or "",
                published=r.get("date"),
                source=r.get("source"),
            )
            for r in rows
            if (r.get("href") or r.get("url")) and r.get("title")
        ]


PROVIDERS: dict[str, type] = {"ddgs": DDGSProvider}

_pace_lock = threading.Lock()
_last_call = 0.0


def search(
    query: str,
    *,
    kind: Kind = "web",
    max_results: int | None = None,
    timelimit: str | None = None,
    provider: SearchProvider | None = None,
) -> list[SearchResult]:
    """Cached, paced, budgeted search. `timelimit`: d, w, m, y or None."""
    settings = get_settings()
    max_results = max_results or settings.search_results_per_query
    provider = provider or PROVIDERS[settings.search_provider]()

    key = _cache_key(provider.name, query, kind, max_results, timelimit)
    cached = _read_cache(key, settings.search_cache_hours)
    if cached is not None:
        tracker.record_search(cached=True)
        return cached

    tracker.record_search(cached=False)  # raises if the per-run search budget is spent
    results = _with_backoff(
        lambda: provider.search(query, kind=kind, max_results=max_results, timelimit=timelimit),
        retries=settings.search_retries,
        base_delay=settings.search_backoff,
        min_interval=settings.search_min_interval,
    )
    _write_cache(key, results)
    return results


def _with_backoff(fn, *, retries: int, base_delay: float, min_interval: float):
    global _last_call
    for attempt in range(retries + 1):
        with _pace_lock:  # keep queries at least `min_interval` apart
            wait = _last_call + min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last_call = time.monotonic()
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - providers raise assorted errors
            if attempt >= retries:
                raise SearchError(f"Search failed after {retries + 1} attempts: {exc}") from exc
            delay = base_delay * 2**attempt
            log.warning("Search error (%s); retrying in %.0fs", exc, delay)
            time.sleep(delay)
    raise AssertionError("unreachable")


def _cache_key(*parts) -> str:
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:32]


def _read_cache(key: str, ttl_hours: float) -> list[SearchResult] | None:
    path = CACHE_DIR / f"{key}.json"
    try:
        if time.time() - path.stat().st_mtime > ttl_hours * 3600:
            return None
        return [SearchResult.model_validate(r) for r in json.loads(path.read_text())]
    except (OSError, ValueError):
        return None


def _write_cache(key: str, results: list[SearchResult]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / f"{key}.json").write_text(json.dumps([r.model_dump() for r in results]))
    except OSError as exc:
        log.debug("Could not write search cache: %s", exc)
