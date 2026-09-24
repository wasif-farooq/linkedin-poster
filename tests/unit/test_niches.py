import pytest

from app.tools.sources.niches import load_niche

YAML = """
settings:
  max_age_days: 3
niches:
  ai-engineering:
    aliases: [AI, LLMs]
    keywords: [LLM]
    feeds: [https://a.feed]
  default:
    keywords: []
    feeds: [https://default.feed]
"""


@pytest.fixture
def feeds_file(tmp_path):
    path = tmp_path / "feeds.yaml"
    path.write_text(YAML)
    return path


@pytest.mark.parametrize("niche", ["ai-engineering", "AI Engineering", "ai_engineering", "llms"])
def test_resolves_key_and_aliases(feeds_file, niche):
    cfg = load_niche(niche, feeds_file)
    assert cfg.name == "ai-engineering"
    assert cfg.feeds == ["https://a.feed"]
    assert cfg.settings.max_age_days == 3
    assert cfg.settings.max_candidates == 40  # default kept


def test_unknown_niche_falls_back_to_default(feeds_file):
    cfg = load_niche("Rust for embedded systems", feeds_file)
    assert cfg.feeds == ["https://default.feed"]
    assert cfg.keywords[0] == "Rust for embedded systems"
    assert "Rust" in cfg.keywords and "for" not in cfg.keywords


def test_repo_feeds_yaml_is_valid():
    cfg = load_niche("ai engineering")
    assert cfg.name == "ai-engineering" and cfg.feeds and cfg.keywords
