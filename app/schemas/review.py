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
