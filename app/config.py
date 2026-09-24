from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

ROLES = ("manager", "topic_scout", "researcher", "writer", "critic")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # LLM (OpenCode Zen, OpenAI-compatible endpoint)
    open_code_key: str = ""
    opencode_base_url: str = "https://opencode.ai/zen/v1"
    default_model: str = "space-bunny-free"
    manager_model: str | None = None
    topic_scout_model: str | None = None
    researcher_model: str | None = None
    writer_model: str | None = None
    critic_model: str | None = None
    # Comma-separated; tried in order if a model is removed or blocked (404/403).
    llm_fallback_models: str = ""
    llm_temperature: float = 0.4
    llm_timeout: float = 120
    # Free-tier protection
    # Reasoning tokens count toward this cap: a brief can use ~4k thinking + ~1k answer.
    llm_max_tokens: int = 16000
    llm_requests_per_minute: float = Field(default=20, gt=0)  # shared by all agents
    llm_rate_limit_retries: int = Field(default=3, ge=0)  # extra retries on HTTP 429
    llm_rate_limit_backoff: float = Field(default=10, ge=0)  # seconds, doubled per retry
    max_llm_calls_per_run: int = Field(default=30, ge=1)  # hard stop for runaway loops
    structured_retries: int = 2
    # auto = try native function calling, fall back to JSON parsing; json = JSON only
    structured_mode: str = "auto"

    # Research (free web search, no API key)
    feeds_path: Path = ROOT_DIR / "config" / "feeds.yaml"
    search_provider: str = "ddgs"
    search_results_per_query: int = Field(default=5, ge=1, le=20)
    max_searches_per_run: int = Field(default=6, ge=0)  # live queries; cache hits are free
    search_cache_hours: float = 24
    search_min_interval: float = 2.0  # seconds between live queries (avoid throttling)
    search_retries: int = Field(default=2, ge=0)
    search_backoff: float = 5.0  # seconds, doubled per retry
    max_articles_per_run: int = Field(default=6, ge=0)  # full pages read per research
    article_max_chars: int = Field(default=3000, ge=500)

    # LinkedIn
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = "http://localhost:8765/callback"
    linkedin_version: str = "202609"  # YYYYMM; LinkedIn sunsets versions after ~1 year
    publish_dry_run: bool = False  # log + record instead of posting

    # Writing
    voice_path: Path = ROOT_DIR / "config" / "voice.md"
    post_target_min_chars: int = 700
    post_target_max_chars: int = 1800
    critic_min_score: int = Field(default=7, ge=1, le=10)  # any score below -> revise

    # Limits
    max_revisions: int = Field(default=2, ge=0)
    max_steps_per_turn: int = Field(default=12, ge=1)

    def model_for(self, role: str) -> str:
        return getattr(self, f"{role}_model", None) or self.default_model

    def fallback_model_list(self) -> list[str]:
        return [m.strip() for m in self.llm_fallback_models.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
