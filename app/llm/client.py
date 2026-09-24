import logging
import time
from functools import lru_cache

import openai
from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.llm.usage import tracker

log = logging.getLogger(__name__)


class MissingAPIKeyError(RuntimeError):
    pass


class ZenChatModel(ChatOpenAI):
    """ChatOpenAI tuned for free tiers.

    - 429: longer backoff than the SDK's (~8s max): `rate_limit_backoff * 2**attempt`
      seconds, or the server's Retry-After.
    - Model gone / blocked (404, 403 e.g. FreeTierError): switch to the next model in
      `fallback_models` for the rest of this process. Free "stealth" models rotate often.
    """

    rate_limit_retries: int = 3
    rate_limit_backoff: float = 10.0
    fallback_models: list[str] = []

    def _generate(self, *args, **kwargs):
        attempt = 0
        while True:
            try:
                return super()._generate(*args, **kwargs)
            except openai.RateLimitError as exc:
                if attempt >= self.rate_limit_retries:
                    raise
                delay = _retry_after(exc) or self.rate_limit_backoff * 2**attempt
                log.warning("Rate limited by %s; retrying in %.0fs", self.model_name, delay)
                tracker.record_rate_limit_retry()
                time.sleep(delay)
                attempt += 1
            except (openai.NotFoundError, openai.PermissionDeniedError) as exc:
                replacement = _next_model(self.model_name, self.fallback_models)
                if not replacement:
                    raise
                log.warning(
                    "Model %s unavailable (%s); falling back to %s",
                    self.model_name,
                    type(exc).__name__,
                    replacement,
                )
                _unavailable.add(self.model_name)
                self.model_name = replacement


# Models that failed with 404/403 in this process; skipped by every later get_llm().
_unavailable: set[str] = set()


def _next_model(current: str, fallbacks: list[str]) -> str | None:
    return next((m for m in fallbacks if m != current and m not in _unavailable), None)


@lru_cache
def get_rate_limiter() -> InMemoryRateLimiter:
    """One limiter shared by every agent: they all spend the same API key's quota."""
    rpm = get_settings().llm_requests_per_minute
    return InMemoryRateLimiter(
        requests_per_second=rpm / 60, check_every_n_seconds=0.1, max_bucket_size=1
    )


def get_llm(role: str = "default", **overrides) -> BaseChatModel:
    """Chat model for an agent role, pointed at OpenCode Zen's OpenAI-compatible API."""
    settings = get_settings()
    if not settings.open_code_key:
        raise MissingAPIKeyError(
            "OPEN_CODE_KEY is not set. Export it in your shell or add it to .env."
        )
    model = settings.model_for(role)
    fallbacks = settings.fallback_model_list()
    if model in _unavailable:
        model = _next_model(model, fallbacks) or model
    params = {
        "model": model,
        "fallback_models": fallbacks,
        "base_url": settings.opencode_base_url,
        "api_key": settings.open_code_key,
        "temperature": settings.llm_temperature,
        "timeout": settings.llm_timeout,
        "max_tokens": settings.llm_max_tokens,
        "max_retries": 2,  # SDK-level retries for transient 5xx/connection errors
        "rate_limit_retries": settings.llm_rate_limit_retries,
        "rate_limit_backoff": settings.llm_rate_limit_backoff,
        "rate_limiter": get_rate_limiter(),
        "callbacks": [tracker],
    }
    params.update(overrides)
    return ZenChatModel(**params)


def _retry_after(exc: openai.RateLimitError) -> float | None:
    response = getattr(exc, "response", None)
    value = response.headers.get("retry-after") if response is not None else None
    try:
        return min(float(value), 300) if value else None
    except ValueError:
        return None
