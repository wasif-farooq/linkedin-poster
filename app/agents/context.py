"""Shared helpers for turning state objects into prompt text."""

from app.schemas.post import Critique, Draft
from app.schemas.research import ResearchBrief


def format_brief(brief: ResearchBrief, *, include_content: bool = False) -> str:
    def cite(ids: list[int]) -> str:
        return f" (sources: {', '.join(map(str, ids))})" if ids else ""

    lines = [
        f"Topic: {brief.topic}",
        f"Angle: {brief.angle or 'not set'}",
        "",
        "Summary:",
        brief.summary,
    ]
    lines += ["", "Key points:"] + [f"- {kp.point}{cite(kp.source_ids)}" for kp in brief.key_points]
    if brief.stats:
        lines += ["", "Stats & facts:"] + [f"- {s.fact}{cite(s.source_ids)}" for s in brief.stats]
    if brief.counterpoints:
        lines += ["", "Counterpoints:"] + [
            f"- {c.point}{cite(c.source_ids)}" for c in brief.counterpoints
        ]
    lines += ["", "Sources:"]
    for s in brief.sources:
        lines.append(f"[{s.id}] {s.title} ({s.url})")
        if include_content:
            lines.append(f"    {s.content[:600]}")
    return "\n".join(lines)


def format_feedback(critique: Critique | None, human_feedback: str | None = None) -> list[str]:
    """Flatten critic findings + human notes into a list of fixes for the Writer."""
    items: list[str] = []
    if human_feedback:
        items.append(f"From the author (highest priority): {human_feedback}")
    if critique:
        items += [f"Must fix: {e}" for e in critique.rule_errors]
        items += critique.issues
        items += [f"Suggestion: {s}" for s in critique.suggestions]
        items += [f"Formatting: {w}" for w in critique.rule_warnings]
    return items


def format_draft(draft: Draft) -> str:
    return f"{draft.full_text()}\n\n({len(draft.full_text())} characters)"
