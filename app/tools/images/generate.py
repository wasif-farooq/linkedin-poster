"""Text-to-image backends, and where generated images are kept.

- pollinations: free, no key (image.pollinations.ai). Unofficial; anonymous requests get a
  small watermark, queue behind other traffic and are throttled.
- openai: gpt-image-1 through the Images API. Paid (~$0.04 per medium 1536x1024 image).

Images are saved as data/images/<32 hex>.<ext>; only that name is kept in the graph state.
"""

import base64
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx

from app import config
from app.config import get_settings
from app.llm.usage import tracker

IMAGE_NAME_PATTERN = r"^[a-f0-9]{32}\.(png|jpg|webp)$"
_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
MEDIA_TYPES = {ext: mime for mime, ext in _EXTENSIONS.items()}
# LinkedIn's recommended landscape size for single-image posts is 1200x627 (1.91:1).
WIDTH, HEIGHT = 1200, 627
POLLINATIONS_RETRIES = 2
POLLINATIONS_BACKOFF = 5.0  # seconds, doubled per retry
OPENAI_SIZE = "1536x1024"  # the closest landscape size gpt-image-1 supports


class ImageGenerationError(RuntimeError):
    pass


@dataclass
class GeneratedImage:
    data: bytes
    media_type: str
    provider: str


def provider_name() -> str:
    settings = get_settings()
    if settings.image_provider == "auto":
        return "openai" if settings.openai_api_key else "pollinations"
    return settings.image_provider


def generate(prompt: str, *, seed: int | None = None) -> GeneratedImage:
    tracker.record_image(get_settings().max_images_per_run)  # raises when spent
    name = provider_name()
    if name == "openai":
        return _openai(prompt)
    return _pollinations(prompt, seed)


def save(image: GeneratedImage) -> str:
    """Write the image under data/images and return its file name."""
    name = f"{uuid.uuid4().hex}.{_EXTENSIONS[image.media_type]}"
    config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    (config.IMAGES_DIR / name).write_bytes(image.data)
    return name


def image_path(name: str) -> Path | None:
    """The saved file for a name from the state, or None (unknown or malformed name)."""
    if not re.fullmatch(IMAGE_NAME_PATTERN, name or ""):
        return None
    path = config.IMAGES_DIR / name
    return path if path.is_file() else None


def _pollinations(prompt: str, seed: int | None) -> GeneratedImage:
    """The anonymous tier shares an upstream quota: busy spells come back as 429 or as 500
    wrapping the upstream 429, so both are retried with backoff."""
    settings = get_settings()
    params = {"width": WIDTH, "height": HEIGHT, "nologo": "true", "private": "true"}
    if seed is not None:
        params["seed"] = seed
    url = settings.pollinations_url + quote(prompt[:1500], safe="")
    for attempt in range(POLLINATIONS_RETRIES + 1):
        try:
            resp = httpx.get(
                url, params=params, timeout=settings.image_timeout, follow_redirects=True
            )
        except httpx.HTTPError as exc:
            raise ImageGenerationError(f"Pollinations didn't answer ({exc}). Try again.") from exc
        media_type = resp.headers.get("content-type", "").split(";")[0].strip()
        if resp.is_success and media_type in _EXTENSIONS:
            return GeneratedImage(resp.content, media_type, "pollinations")
        busy = resp.status_code == 429 or resp.status_code >= 500
        if not busy or attempt == POLLINATIONS_RETRIES:
            break
        time.sleep(POLLINATIONS_BACKOFF * 2**attempt)
    if busy:
        raise ImageGenerationError(
            "Pollinations' free tier is busy right now. Try again in a minute, or set "
            f"OPENAI_API_KEY for a paid, more reliable provider. ({_detail(resp)})"
        )
    raise ImageGenerationError(
        f"Pollinations returned {resp.status_code} ({media_type or 'no content type'})."
    )


def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        return str(body.get("message") or body.get("error") or "")[:160]
    except ValueError:
        return f"HTTP {resp.status_code}"


def _openai(prompt: str) -> GeneratedImage:
    settings = get_settings()
    if not settings.openai_api_key:
        raise ImageGenerationError("IMAGE_PROVIDER=openai needs OPENAI_API_KEY.")
    try:
        resp = httpx.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.openai_image_model,
                "prompt": prompt,
                "size": OPENAI_SIZE,
                "quality": settings.openai_image_quality,
                "n": 1,
            },
            timeout=settings.image_timeout,
        )
    except httpx.HTTPError as exc:
        raise ImageGenerationError(f"OpenAI didn't answer ({exc}). Try again.") from exc
    if not resp.is_success:
        try:
            detail = resp.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            detail = resp.text[:300]
        raise ImageGenerationError(f"OpenAI image error {resp.status_code}: {detail}")
    b64 = resp.json()["data"][0]["b64_json"]
    return GeneratedImage(base64.b64decode(b64), "image/png", "openai")
