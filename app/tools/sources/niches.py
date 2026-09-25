import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.config import get_settings

_STOPWORDS = {"and", "or", "the", "a", "an", "of", "for", "in", "on", "to", "with"}


@dataclass
class SourceSettings:
    max_age_days: int = 3  # the freshness window...
    fallback_max_age_days: int = 7  # ...widened to this when it finds too few stories
    min_candidates: int = 15
    per_feed_limit: int = 15
    news_results_per_query: int = 15
    hn_min_points: int = 30
    max_candidates: int = 50


@dataclass
class NicheConfig:
    name: str
    keywords: list[str] = field(default_factory=list)
    feeds: list[str] = field(default_factory=list)
    news_queries: list[str] = field(default_factory=list)  # keyword news searches
    settings: SourceSettings = field(default_factory=SourceSettings)


def load_niche(niche: str, path: Path | None = None) -> NicheConfig:
    """Resolve a niche string to its sources from feeds.yaml (falls back to `default`)."""
    path = path or get_settings().feeds_path
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    settings = SourceSettings(**(data.get("settings") or {}))
    niches: dict = data.get("niches") or {}

    wanted = _norm(niche)
    for key, cfg in niches.items():
        if key == "default":
            continue
        names = {_norm(key), *(_norm(a) for a in cfg.get("aliases") or [])}
        if wanted in names:
            return NicheConfig(
                key,
                cfg.get("keywords") or [],
                cfg.get("feeds") or [],
                cfg.get("news_queries") or [],
                settings,
            )

    default = niches.get("default") or {}
    keywords = (default.get("keywords") or []) + _keywords_from_text(niche)
    queries = (default.get("news_queries") or []) + [niche.strip()]
    return NicheConfig(niche, keywords, default.get("feeds") or [], queries, settings)


def _norm(text: str) -> str:
    return re.sub(r"[\s_-]+", " ", text.strip().lower())


def _keywords_from_text(text: str) -> list[str]:
    phrase = text.strip()
    words = [w for w in re.findall(r"[\w+#.]+", phrase) if w.lower() not in _STOPWORDS]
    out = [phrase] if len(words) > 1 else []
    return out + words
