"""Fetch a web page and extract its main article text (free, no API)."""

import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import httpx
import trafilatura

from app.schemas.research import Article
from app.tools.sources.feeds import USER_AGENT

log = logging.getLogger(__name__)

# Pages that never yield readable article text without a login or JS.
SKIP_HOSTS = {"twitter.com", "x.com", "news.ycombinator.com", "linkedin.com", "youtube.com"}


def fetch_article(
    url: str, *, max_chars: int = 3000, client: httpx.Client | None = None
) -> Article | None:
    """Return the page's main text, or None if it can't be fetched/extracted."""
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    if host in SKIP_HOSTS:
        return None
    try:
        if client is None:
            with httpx.Client(
                timeout=20, follow_redirects=True, transport=httpx.HTTPTransport(retries=2)
            ) as c:
                resp = c.get(url, headers={"User-Agent": USER_AGENT})
        else:
            resp = client.get(url, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.info("Article fetch failed for %s: %s", url, exc)
        return None
    if "html" not in resp.headers.get("content-type", "html"):
        return None

    html = resp.text
    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    if not text or len(text) < 200:
        return None
    meta = trafilatura.extract_metadata(html)
    return Article(
        url=url,
        title=(meta.title if meta and meta.title else ""),
        text=_truncate(text, max_chars),
        published=(meta.date if meta else None),
    )


def fetch_articles(urls: list[str], *, max_chars: int = 3000) -> dict[str, Article]:
    """Fetch several pages in parallel; returns {url: Article} for the ones that worked."""
    if not urls:
        return {}
    transport = httpx.HTTPTransport(retries=2)
    with (
        httpx.Client(timeout=20, follow_redirects=True, transport=transport) as client,
        ThreadPoolExecutor(max_workers=min(6, len(urls))) as pool,
    ):
        results = pool.map(lambda u: fetch_article(u, max_chars=max_chars, client=client), urls)
        return {a.url: a for a in results if a}


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    return cut[: cut.rfind(" ")] + " …" if " " in cut else cut
