"""Keyword news search across thousands of outlets via Bing News RSS (free, no key).

Bing's RSS links go through a click tracker whose `url` parameter holds the article's
real address, so the Researcher can read the article itself. (Google News RSS has
better coverage, but its links only resolve with JavaScript.)
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import httpx

from app.schemas.topic import Candidate
from app.tools.sources.feeds import USER_AGENT, parse_feed

log = logging.getLogger(__name__)

API = "https://www.bing.com/news/search"
# Newest first, from the past week (interval "7" is the past 24 hours).
FILTERS = 'sortbydate="1" interval="8"'


def search_news(
    query: str, *, limit: int = 15, max_age_days: int = 7, client: httpx.Client | None = None
) -> list[Candidate]:
    params = {"q": query, "format": "rss", "count": 50, "qft": FILTERS, "mkt": "en-US"}
    try:
        if client is None:
            with httpx.Client(timeout=15, follow_redirects=True) as c:
                resp = c.get(API, params=params, headers={"User-Agent": USER_AGENT})
        else:
            resp = client.get(API, params=params, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("News search failed for %r: %s", query, exc)
        return []
    items = parse_feed(resp.content, API, limit=limit, max_age_days=max_age_days)
    out = []
    for item in items:
        url = article_url(item.url)
        if url:
            host = urlsplit(url).netloc.lower().removeprefix("www.")
            out.append(item.model_copy(update={"url": url, "source": host, "kind": "news"}))
    return out


def collect(queries: list[str], *, limit: int = 15, max_age_days: int = 7) -> list[Candidate]:
    """All queries in parallel."""
    if not queries:
        return []
    transport = httpx.HTTPTransport(retries=2)
    with (
        httpx.Client(timeout=15, follow_redirects=True, transport=transport) as client,
        ThreadPoolExecutor(max_workers=min(4, len(queries))) as pool,
    ):
        batches = pool.map(
            lambda q: search_news(q, limit=limit, max_age_days=max_age_days, client=client),
            queries,
        )
        return [c for batch in batches for c in batch]


def article_url(link: str) -> str | None:
    """The real article address behind a Bing click-tracking link (or the link itself)."""
    parts = urlsplit(link)
    if parts.netloc.endswith("bing.com"):
        target = parse_qs(parts.query).get("url", [None])[0]
        return target if target and target.startswith(("http://", "https://")) else None
    return link if parts.scheme in ("http", "https") else None
