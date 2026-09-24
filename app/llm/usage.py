"""Per-run LLM usage tracking and a hard call budget (protects free-tier quotas)."""

import threading
from dataclasses import dataclass

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class LLMBudgetExceededError(RuntimeError):
    pass


class SearchBudgetExceededError(RuntimeError):
    pass


@dataclass
class UsageSnapshot:
    calls: int
    input_tokens: int
    output_tokens: int
    rate_limit_retries: int
    searches: int = 0
    search_cache_hits: int = 0

    def __str__(self) -> str:
        text = (
            f"LLM calls: {self.calls} | tokens in: {self.input_tokens:,} "
            f"out: {self.output_tokens:,}"
        )
        if self.rate_limit_retries:
            text += f" | rate-limit retries: {self.rate_limit_retries}"
        if self.searches or self.search_cache_hits:
            text += f" | searches: {self.searches} (+{self.search_cache_hits} cached)"
        return text


class UsageTracker(BaseCallbackHandler):
    """Counts LLM calls, tokens and web searches; enforces per-run budgets for both."""

    raise_error = True  # let LLMBudgetExceededError propagate out of the callback

    def __init__(self, max_calls: int | None = None, max_searches: int | None = None):
        self.max_calls = max_calls
        self.max_searches = max_searches
        self._lock = threading.Lock()
        self.reset()

    def reset(self, max_calls: int | None = None, max_searches: int | None = None) -> None:
        with self._lock:
            if max_calls is not None:
                self.max_calls = max_calls
            if max_searches is not None:
                self.max_searches = max_searches
            self.calls = 0
            self.input_tokens = 0
            self.output_tokens = 0
            self.rate_limit_retries = 0
            self.searches = 0
            self.search_cache_hits = 0

    def record_search(self, *, cached: bool) -> None:
        """Count a search; live (uncached) searches are limited by `max_searches`."""
        with self._lock:
            if cached:
                self.search_cache_hits += 1
                return
            if self.max_searches is not None and self.searches >= self.max_searches:
                raise SearchBudgetExceededError(
                    f"Search budget of {self.max_searches} per run reached "
                    "(raise MAX_SEARCHES_PER_RUN to allow more)."
                )
            self.searches += 1

    def searches_left(self) -> int | None:
        with self._lock:
            return None if self.max_searches is None else self.max_searches - self.searches

    def on_chat_model_start(self, serialized, messages, **kwargs) -> None:
        with self._lock:
            if self.max_calls is not None and self.calls >= self.max_calls:
                raise LLMBudgetExceededError(
                    f"LLM call budget of {self.max_calls} per run reached "
                    "(raise MAX_LLM_CALLS_PER_RUN to allow more)."
                )
            self.calls += 1

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        inp = out = 0
        for gens in response.generations:
            for gen in gens:
                usage = getattr(getattr(gen, "message", None), "usage_metadata", None)
                if usage:
                    inp += usage.get("input_tokens", 0)
                    out += usage.get("output_tokens", 0)
        with self._lock:
            self.input_tokens += inp
            self.output_tokens += out

    def record_rate_limit_retry(self) -> None:
        with self._lock:
            self.rate_limit_retries += 1

    def snapshot(self) -> UsageSnapshot:
        with self._lock:
            return UsageSnapshot(
                self.calls,
                self.input_tokens,
                self.output_tokens,
                self.rate_limit_retries,
                self.searches,
                self.search_cache_hits,
            )


tracker = UsageTracker()
