import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.config import get_settings

_STOPWORDS = {"and", "or", "the", "a", "an", "of", "for", "in", "on", "to", "with"}


@dataclass
class SourceSettings:
    max_age_days: int = 7
    per_feed_limit: int = 15
    hn_min_points: int = 30
    max_candidates: int = 40


@dataclass
class NicheConfig:
    name: str
    keywords: list[str] = field(default_factory=list)
    feeds: list[str] = field(default_factory=list)
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
            return NicheConfig(key, cfg.get("keywords") or [], cfg.get("feeds") or [], settings)

    default = niches.get("default") or {}
    keywords = (default.get("keywords") or []) + _keywords_from_text(niche)
    return NicheConfig(niche, keywords, default.get("feeds") or [], settings)


def _norm(text: str) -> str:
    return re.sub(r"[\s_-]+", " ", text.strip().lower())


def _keywords_from_text(text: str) -> list[str]:
    phrase = text.strip()
    words = [w for w in re.findall(r"[\w+#.]+", phrase) if w.lower() not in _STOPWORDS]
    out = [phrase] if len(words) > 1 else []
    return out + words
