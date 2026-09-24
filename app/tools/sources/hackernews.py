"""Hacker News stories via the Algolia HN Search API (no key needed)."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.schemas.topic import Candidate

log = logging.getLogger(__name__)

API = "https://hn.algolia.com/api/v1/search"
ITEM_URL = "https://news.ycombinator.com/item?id={}"


def front_page(*, limit: int = 30, client: httpx.Client | None = None) -> list[Candidate]:
    """Current HN front page stories."""
    return _search({"tags": "front_page", "hitsPerPage": limit}, client)


def search_stories(
    query: str,
    *,
    max_age_days: int = 7,
    min_points: int = 30,
    limit: int = 10,
    client: httpx.Client | None = None,
) -> list[Candidate]:
    """Recent popular stories matching `query`."""
    since = int(time.time()) - max_age_days * 86400
    params = {
        "query": query,
        "tags": "story",
        "numericFilters": f"created_at_i>{since},points>{min_points}",
        "hitsPerPage": limit,
    }
    return _search(params, client)


def collect(keywords: list[str], *, max_age_days: int = 7, min_points: int = 30) -> list[Candidate]:
    """Front page + keyword searches, fetched in parallel."""
    with httpx.Client(timeout=15, transport=httpx.HTTPTransport(retries=2)) as client:
        jobs = [lambda: front_page(client=client)] + [
            (
                lambda kw=kw: search_stories(
                    kw, max_age_days=max_age_days, min_points=min_points, client=client
                )
            )
            for kw in keywords
        ]
        with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
            return [c for batch in pool.map(lambda job: job(), jobs) for c in batch]


def _search(params: dict, client: httpx.Client | None) -> list[Candidate]:
    try:
        if client is None:
            with httpx.Client(timeout=15, transport=httpx.HTTPTransport(retries=2)) as c:
                resp = c.get(API, params=params)
        else:
            resp = client.get(API, params=params)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("HN search failed (%s): %s", params.get("query") or params.get("tags"), exc)
        return []
    return [c for c in (_to_candidate(h) for h in hits) if c]


def _to_candidate(hit: dict) -> Candidate | None:
    title = hit.get("title")
    object_id = hit.get("objectID")
    if not title or not object_id:
        return None
    discussion = ITEM_URL.format(object_id)
    return Candidate(
        title=title,
        url=hit.get("url") or discussion,
        source="Hacker News",
        summary=f"HN discussion: {discussion}",
        published=hit.get("created_at"),
        points=hit.get("points"),
        comments=hit.get("num_comments"),
    )
