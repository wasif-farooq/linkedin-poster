from pydantic import BaseModel, Field


class ImagePrompt(BaseModel):
    """What the Illustrator LLM returns."""

    prompt: str = Field(
        description="Text-to-image prompt: subject, composition, style, palette, lighting"
    )
    alt_text: str = Field(description="One-sentence description of the image for screen readers")


class PostImage(ImagePrompt):
    """A generated image as kept in the state (the file lives in data/images)."""

    file: str = Field(description="File name under data/images")
    provider: str
    direction: str = Field(default="", description="The user's style request, if any")
