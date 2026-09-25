"""Build the candidate pool for the Topic Scout: fetch, keep what's fresh, merge duplicate
coverage of one story, rank by relevance and heat, cap."""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from urllib.parse import urlsplit

from app.schemas.topic import Candidate
from app.tools.sources import feeds, hackernews, news
from app.tools.sources.niches import NicheConfig

# "Show HN: my 2019 essay (2019)": HN marks reposts of old articles with the year.
_YEAR_TAG = re.compile(r"[(\[]((?:19|20)\d\d)[)\]]")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "in", "on", "to", "with", "is", "are", "how",
    "why", "what", "its", "it", "at", "by", "from", "new", "now", "your", "you", "this", "that",
}  # fmt: skip
SAME_STORY = 0.5  # title word overlap (Jaccard) above which two items are the same story
SHARED_NAMES = 4  # ...or this many shared words making up 40% of the shorter title


def collect_candidates(niche: NicheConfig) -> list[Candidate]:
    """Everything from the fallback window is fetched once; the ranking then uses the
    freshness window, and only widens it when that leaves too few stories."""
    s = niche.settings
    wide = max(s.fallback_max_age_days, s.max_age_days)
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [
            pool.submit(feeds.fetch_feeds, niche.feeds, limit=s.per_feed_limit, max_age_days=wide),
            pool.submit(
                hackernews.collect, niche.keywords, max_age_days=wide, min_points=s.hn_min_points
            ),
            pool.submit(
                news.collect, niche.news_queries, limit=s.news_results_per_query, max_age_days=wide
            ),
        ]
        items = [c for job in jobs for c in job.result()]
    fresh = within_days(items, s.max_age_days)
    if len(fresh) < s.min_candidates:
        fresh = within_days(items, wide)
    return rank_candidates(fresh, niche.keywords, limit=s.max_candidates)


def within_days(items: list[Candidate], days: float) -> list[Candidate]:
    now = datetime.now(UTC)
    return [c for c in items if (age := age_hours(c, now)) is not None and age <= days * 24]


def age_hours(c: Candidate, now: datetime | None = None) -> float | None:
    if not c.published:
        return None
    try:
        published = datetime.fromisoformat(c.published.replace("Z", "+00:00"))
    except ValueError:
        return None
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    return max(((now or datetime.now(UTC)) - published).total_seconds() / 3600, 0)


def rank_candidates(
    items: list[Candidate], keywords: list[str], *, limit: int = 50
) -> list[Candidate]:
    """Drop old reposts, merge items about the same story, and rank: relevance first, then
    heat (recency, how many sources cover it, HN points per hour).

    A news-search hit is only a candidate when another source covers the same story too;
    on its own it could be any blog. Pass items curated feeds first so a story is
    represented by its best source."""
    patterns = [_keyword_pattern(k) for k in keywords if k.strip()]
    this_year = datetime.now(UTC).year
    stories: list[Candidate] = []
    words: list[set[str]] = []
    seen: dict[str, int] = {}  # url/title key -> index in stories
    for item in items:
        if any(int(y) < this_year for y in _YEAR_TAG.findall(item.title)):
            continue
        keys = {_url_key(item.url), _title_key(item.title)}
        tokens = _title_words(item.title)
        match = next((seen[k] for k in keys if k in seen), None)
        if match is None:
            match = next(
                (i for i, other in enumerate(words) if _overlap(tokens, other) >= SAME_STORY), None
            )
        if match is not None:
            story = stories[match]
            if item.source != story.source and item.source not in story.also_in:
                story.also_in.append(item.source)
            if item.points and (story.points or 0) < item.points:
                story.points, story.comments = item.points, item.comments
            for k in keys:
                seen.setdefault(k, match)
            continue
        text = f"{item.title} {item.summary}"
        hits = sum(1 for p in patterns if p.search(text))
        seen |= dict.fromkeys(keys, len(stories))
        stories.append(item.model_copy(update={"keyword_hits": hits, "also_in": []}))
        words.append(tokens)
    stories = [c for c in stories if c.kind != "news" or c.also_in]

    now = datetime.now(UTC)
    ages = [age_hours(c, now) for c in stories]
    window = max([a for a in ages if a is not None], default=24) or 24

    def score(pair: tuple[Candidate, float | None]) -> tuple:
        c, age = pair
        age = window if age is None else age
        curated = {"feed": 5, "news": 2, "hn": 0}[c.kind]
        recency = 8 * (1 - age / window)  # just out: +8, oldest in the pool: 0
        coverage = min(len(c.also_in), 3) * 3
        # capped so heat never outranks a keyword hit
        traction = min((c.points or 0) / 100, 4) + min((c.points or 0) / max(age, 2) / 10, 3)
        relevance = min(c.keyword_hits, 2) * 10  # on-topic; more hits don't make it hotter
        return (relevance + curated + recency + coverage + traction, -age)

    ranked = sorted(zip(stories, ages, strict=True), key=score, reverse=True)
    return [c for c, _ in ranked[:limit]]


def _title_words(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9][a-z0-9.+#-]*", title.lower()) if w not in _STOPWORDS}


def _overlap(a: set[str], b: set[str]) -> float:
    """Jaccard similarity of two titles' words, or a match on many shared names
    ("White House", "OpenAI", "Anthropic", "UK") across differently worded headlines."""
    if len(a) < 4 or len(b) < 4:  # too short to tell stories apart
        return 0.0
    shared = len(a & b)
    if shared >= SHARED_NAMES and shared / min(len(a), len(b)) >= 0.4:
        return 1.0
    return shared / len(a | b)


def _keyword_pattern(keyword: str) -> re.Pattern:
    return re.compile(rf"(?<!\w){re.escape(keyword.strip())}(?!\w)", re.IGNORECASE)


def _url_key(url: str) -> str:
    parts = urlsplit(url)
    host = parts.netloc.lower().removeprefix("www.")
    query = "&".join(q for q in sorted(parts.query.split("&")) if q and not q.startswith("utm_"))
    return f"url:{host}{parts.path.rstrip('/')}?{query}"


def _title_key(title: str) -> str:
    return "title:" + re.sub(r"\W+", " ", title.lower()).strip()
