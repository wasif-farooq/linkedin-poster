"""Build the candidate pool for the Topic Scout: fetch, dedupe, pre-rank, cap."""

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from app.schemas.topic import Candidate
from app.tools.sources import feeds, hackernews
from app.tools.sources.niches import NicheConfig


def collect_candidates(niche: NicheConfig) -> list[Candidate]:
    s = niche.settings
    with ThreadPoolExecutor(max_workers=2) as pool:
        rss = pool.submit(
            feeds.fetch_feeds, niche.feeds, limit=s.per_feed_limit, max_age_days=s.max_age_days
        )
        hn = pool.submit(
            hackernews.collect,
            niche.keywords,
            max_age_days=s.max_age_days,
            min_points=s.hn_min_points,
        )
        items = rss.result() + hn.result()
    return rank_candidates(items, niche.keywords, limit=s.max_candidates)


def rank_candidates(
    items: list[Candidate], keywords: list[str], *, limit: int = 40
) -> list[Candidate]:
    """Dedupe, score by keyword relevance / HN traction / recency, and keep the top `limit`."""
    patterns = [_keyword_pattern(k) for k in keywords if k.strip()]
    unique: list[Candidate] = []
    seen: set[str] = set()
    for item in items:
        keys = {_url_key(item.url), _title_key(item.title)}
        if keys & seen:
            continue
        seen |= keys
        text = f"{item.title} {item.summary}"
        hits = sum(1 for p in patterns if p.search(text))
        unique.append(item.model_copy(update={"keyword_hits": hits}))

    def score(c: Candidate) -> tuple:
        from_curated_feed = c.source != "Hacker News"
        # capped below one keyword hit so popularity never outranks relevance
        traction = min((c.points or 0) / 100, 4)
        return (c.keyword_hits * 10 + (5 if from_curated_feed else 0) + traction, c.published or "")

    unique.sort(key=score, reverse=True)
    return unique[:limit]


def _keyword_pattern(keyword: str) -> re.Pattern:
    return re.compile(rf"(?<!\w){re.escape(keyword.strip())}(?!\w)", re.IGNORECASE)


def _url_key(url: str) -> str:
    parts = urlsplit(url)
    host = parts.netloc.lower().removeprefix("www.")
    query = "&".join(q for q in sorted(parts.query.split("&")) if q and not q.startswith("utm_"))
    return f"url:{host}{parts.path.rstrip('/')}?{query}"


def _title_key(title: str) -> str:
    return "title:" + re.sub(r"\W+", " ", title.lower()).strip()
