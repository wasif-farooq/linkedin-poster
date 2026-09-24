"""User-facing messages for errors that end a run (shared by the CLI and the web API)."""

import openai

from app.llm.client import MissingAPIKeyError
from app.llm.structured import StructuredOutputError
from app.llm.usage import LLMBudgetExceededError, SearchBudgetExceededError
from app.tools.sources.web_search import SearchError

# Exceptions a run can end with that deserve a friendly message rather than a traceback.
KNOWN_ERRORS = (
    MissingAPIKeyError,
    LLMBudgetExceededError,
    SearchBudgetExceededError,
    SearchError,
    StructuredOutputError,
    openai.APIError,
)


def describe_error(exc: BaseException) -> tuple[int, str] | None:
    """(exit code, message) for a known run-ending error, else None."""
    if isinstance(exc, MissingAPIKeyError):
        return 1, str(exc)
    if isinstance(exc, openai.RateLimitError):
        return 2, (
            "Rate limited by the model provider even after backing off. "
            "Wait a few minutes, or lower LLM_REQUESTS_PER_MINUTE."
        )
    if isinstance(exc, openai.PermissionDeniedError):
        return 2, f"Model access denied (free-tier restriction?): {exc}"
    if isinstance(
        exc,
        LLMBudgetExceededError | SearchBudgetExceededError | SearchError | StructuredOutputError,
    ):
        return 2, str(exc)
    if isinstance(exc, openai.APIConnectionError | openai.APITimeoutError):
        return 3, "Couldn't reach the model provider (network down or timed out). Try again."
    if isinstance(exc, openai.APIError):
        return 3, f"Model provider error: {exc}. Try again shortly."
    return None
