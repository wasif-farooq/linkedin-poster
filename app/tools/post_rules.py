"""Deterministic LinkedIn post checks (free: no LLM call).

Errors block publishing and force a revision; warnings are passed to the Critic/Writer.
"""

import re
from dataclasses import dataclass, field

from app.schemas.post import Draft

LINKEDIN_MAX_CHARS = 3000
HOOK_MAX_CHARS = 200  # roughly what shows before "...see more"
PARAGRAPH_MAX_CHARS = 350

_MARKDOWN = [
    (
        re.compile(r"\*\*[^*]+\*\*|__[^_]+__"),
        "markdown bold (**text**) — LinkedIn shows the asterisks",
    ),
    (
        re.compile(r"^\s{0,3}#{1,6}\s", re.MULTILINE),
        "markdown heading (# ...) — not rendered on LinkedIn",
    ),
    (re.compile(r"\[[^\]]+\]\([^)]+\)"), "markdown link [text](url) — not rendered on LinkedIn"),
]
_LIST_MARKER = re.compile(r"^\s*[-*]\s", re.MULTILINE)
_URL = re.compile(r"https?://\S+")
_HASHTAG_IN_BODY = re.compile(r"(?<![\w&])#[A-Za-z]\w+")


@dataclass
class RuleReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def check_post(draft: Draft, *, target_min: int = 700, target_max: int = 1800) -> RuleReport:
    report = RuleReport()
    body = draft.text.strip()
    full = draft.full_text()

    if not body:
        report.errors.append("Post is empty.")
        return report
    if len(full) > LINKEDIN_MAX_CHARS:
        report.errors.append(
            f"Post is {len(full)} chars; LinkedIn's limit is {LINKEDIN_MAX_CHARS}."
        )
    for pattern, message in _MARKDOWN:
        if pattern.search(body):
            report.errors.append(f"Uses {message}.")

    if _LIST_MARKER.search(body):
        report.warnings.append("Uses '-'/'*' list markers; '→' or '•' read better on LinkedIn.")

    hook = next(line for line in body.splitlines() if line.strip())
    if len(hook) > HOOK_MAX_CHARS:
        report.warnings.append(
            f"First line is {len(hook)} chars; keep the hook under {HOOK_MAX_CHARS} "
            "so it shows before 'see more'."
        )
    if not 3 <= len(draft.hashtags) <= 5:
        report.warnings.append(f"Has {len(draft.hashtags)} hashtags; use 3-5.")
    if _HASHTAG_IN_BODY.search(body):
        report.warnings.append("Hashtags in the body; keep them in the hashtag list at the end.")
    if _URL.search(body):
        report.warnings.append(
            "Contains a URL; LinkedIn reduces reach for external links. Name the source instead."
        )
    if len(full) < target_min:
        report.warnings.append(f"Only {len(full)} chars; aim for {target_min}-{target_max}.")
    elif len(full) > target_max:
        report.warnings.append(f"{len(full)} chars; aim for {target_min}-{target_max}.")
    long_paras = [p for p in re.split(r"\n\s*\n", body) if len(p) > PARAGRAPH_MAX_CHARS]
    if long_paras:
        report.warnings.append(
            f"{len(long_paras)} paragraph(s) over {PARAGRAPH_MAX_CHARS} chars; "
            "break them up for mobile readers."
        )
    return report
