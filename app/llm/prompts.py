from functools import lru_cache

from app.config import PROMPTS_DIR


@lru_cache
def load_prompt(name: str) -> str:
    """Load a markdown prompt from app/prompts/<name>.md."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def render_prompt(name: str, **values) -> str:
    """Load a prompt and fill {placeholders}. Literal braces must be doubled."""
    return load_prompt(name).format(**values)
