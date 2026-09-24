"""Structured output that works even with models that have weak tool-calling.

Strategy:
1. (mode "auto"/"native") try the model's native structured output (function calling).
2. Fall back to asking for raw JSON matching the schema, extracting the JSON
   from the reply and validating it; on failure, retry with the error fed back.
"""

import json
import logging
import re

import openai
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.llm.usage import LLMBudgetExceededError

log = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class StructuredOutputError(RuntimeError):
    pass


class TruncatedOutputError(StructuredOutputError):
    """The model hit max_tokens (reasoning models spend much of it on thinking)."""


# Errors where retrying with a different strategy just wastes quota.
_NON_RECOVERABLE = (
    openai.RateLimitError,
    openai.AuthenticationError,
    LLMBudgetExceededError,
    TruncatedOutputError,
)

# Models whose native structured output failed once in this process.
_native_unsupported: set[str] = set()


def _model_key(llm: BaseChatModel) -> str:
    return getattr(llm, "model_name", None) or type(llm).__name__


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (handles fences and <think> blocks)."""
    text = _THINK_RE.sub("", text).strip()
    candidates = [m.strip() for m in _FENCE_RE.findall(text)] + [text]
    for candidate in candidates:
        start = candidate.find("{")
        while start != -1:
            end = _matching_brace(candidate, start)
            if end == -1:
                break
            try:
                value = json.loads(candidate[start : end + 1])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                pass
            start = candidate.find("{", start + 1)
    raise ValueError("No JSON object found in model reply")


def _matching_brace(text: str, start: int) -> int:
    depth, in_str, escaped = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _check_truncated(message) -> None:
    metadata = getattr(message, "response_metadata", None) or {}
    if metadata.get("finish_reason") == "length":
        raise TruncatedOutputError(
            "Model reply was cut off at max_tokens (reasoning models spend much of it thinking). "
            "Raise LLM_MAX_TOKENS."
        )


def _json_instructions(schema: type[BaseModel]) -> str:
    return (
        "Respond with ONLY a single JSON object (no prose, no markdown fences) "
        "that validates against this JSON Schema:\n"
        f"{json.dumps(schema.model_json_schema(), indent=2)}"
    )


def invoke_structured[T: BaseModel](
    llm: BaseChatModel,
    schema: type[T],
    messages: list[BaseMessage],
    *,
    retries: int | None = None,
    mode: str | None = None,
) -> T:
    """Invoke `llm` and return a validated `schema` instance."""
    settings = get_settings()
    retries = settings.structured_retries if retries is None else retries
    mode = mode or settings.structured_mode

    model_key = _model_key(llm)
    if mode == "native" or (mode == "auto" and model_key not in _native_unsupported):
        try:
            out = llm.with_structured_output(
                schema, method="function_calling", include_raw=True
            ).invoke(messages)
            _check_truncated(out["raw"])
            if isinstance(out["parsed"], schema):
                return out["parsed"]
            if mode == "native":
                raise StructuredOutputError(
                    f"Native structured output failed: {out['parsing_error']}"
                )
            if not getattr(out["raw"], "tool_calls", None):
                _native_unsupported.add(model_key)  # model ignored the tool: stop trying it
            # else: it called the tool but got the content wrong -- a bad answer, not a missing
            # capability; fall through to JSON mode without flagging the model.
            log.debug(
                "Native structured output unusable for %s: %s", model_key, out["parsing_error"]
            )
        except _NON_RECOVERABLE:
            raise  # quota/budget/truncation: falling back would only burn another call
        except Exception as exc:  # noqa: BLE001 - any other provider failure falls back to JSON
            if mode == "native":
                raise StructuredOutputError(str(exc)) from exc
            # Remember so later calls to this model skip straight to JSON (saves free-tier calls).
            _native_unsupported.add(model_key)
            log.debug("Native structured output failed for %s, using JSON: %s", model_key, exc)

    convo = [*messages, SystemMessage(content=_json_instructions(schema))]
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        reply = llm.invoke(convo)
        _check_truncated(reply)  # retrying with the same token cap would just fail again
        text = reply.content if isinstance(reply.content, str) else str(reply.content)
        try:
            return schema.model_validate(extract_json(text))
        except (ValueError, ValidationError) as exc:
            last_error = exc
            log.debug("Structured parse attempt %d failed: %s", attempt + 1, exc)
            convo = [
                *convo,
                AIMessage(content=text),
                HumanMessage(
                    content=f"That reply was invalid: {exc}\nReturn ONLY the corrected JSON object."
                ),
            ]
    raise StructuredOutputError(
        f"Could not get valid {schema.__name__} after {retries + 1} attempts: {last_error}"
    )
