from typing import Literal

from pydantic import BaseModel, model_validator


class ReviewAction(BaseModel):
    """The human's decision on a draft, sent back with Command(resume=...)."""

    action: Literal["approve", "edit", "revise", "reject"]
    text: str | None = None  # edit: the full edited post; revise: feedback for the Writer

    @model_validator(mode="after")
    def _text_required(self):
        if self.action in ("edit", "revise") and not (self.text and self.text.strip()):
            raise ValueError(f"'{self.action}' needs text")
        return self


class TopicPickAnswer(BaseModel):
    """The human's answer to the topic shortlist, sent back with Command(resume=...)."""

    choice: int | None = None  # 0-based index into the options shown
    more: bool = False  # show different topics
    hint: str | None = None  # optional steer for "more", e.g. "something about open source"
    topic: str | None = None  # the user's own topic instead
    cancel: bool = False

    @model_validator(mode="after")
    def _exactly_one(self):
        picked = [
            self.choice is not None,
            self.more,
            bool(self.topic and self.topic.strip()),
            self.cancel,
        ]
        if sum(picked) != 1:
            raise ValueError("answer with exactly one of: choice, more, topic, cancel")
        return self
