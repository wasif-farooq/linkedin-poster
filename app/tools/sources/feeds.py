"""RSS/Atom feed fetching."""

import html
import logging
import re
from calendar import timegm
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import feedparser
import httpx

from app.schemas.topic import Candidate

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; linkedin-poster/0.1)"
_TAG_RE = re.compile(r"<[^>]+>")


def fetch_feed(
    url: str, *, limit: int = 15, max_age_days: int = 7, client: httpx.Client | None = None
) -> list[Candidate]:
    """Fetch one feed and return its recent items. Network/parse errors return []."""
    try:
        if client is None:
            with httpx.Client(timeout=15, follow_redirects=True, transport=_transport()) as c:
                resp = c.get(url, headers={"User-Agent": USER_AGENT})
        else:
            resp = client.get(url, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Feed fetch failed for %s: %s", url, exc)
        return []
    return parse_feed(resp.content, url, limit=limit, max_age_days=max_age_days)


def parse_feed(
    content: bytes | str, url: str = "", *, limit: int = 15, max_age_days: int = 7
) -> list[Candidate]:
    parsed = feedparser.parse(content)
    source = (parsed.feed.get("title") or url).strip()
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)

    items: list[Candidate] = []
    for entry in parsed.entries:
        link = entry.get("link")
        title = clean_text(entry.get("title", ""))
        if not link or not title:
            continue
        published = _entry_datetime(entry)
        if published and published < cutoff:
            continue
        items.append(
            Candidate(
                title=title,
                url=link,
                source=source,
                summary=clean_text(entry.get("summary", ""))[:400],
                published=published.isoformat() if published else None,
            )
        )
        if len(items) >= limit:
            break
    return items


def fetch_feeds(urls: list[str], *, limit: int = 15, max_age_days: int = 7) -> list[Candidate]:
    """Fetch several feeds in parallel."""
    if not urls:
        return []
    with (
        httpx.Client(timeout=15, follow_redirects=True, transport=_transport()) as client,
        ThreadPoolExecutor(max_workers=min(8, len(urls))) as pool,
    ):
        results = pool.map(
            lambda u: fetch_feed(u, limit=limit, max_age_days=max_age_days, client=client), urls
        )
        return [item for batch in results for item in batch]


def _transport() -> httpx.HTTPTransport:
    """Retries dropped/refused connections (not HTTP errors) a couple of times."""
    return httpx.HTTPTransport(retries=2)


def clean_text(text: str) -> str:
    text = html.unescape(_TAG_RE.sub(" ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _entry_datetime(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime.fromtimestamp(timegm(value), tz=UTC)
    return None
