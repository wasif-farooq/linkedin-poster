"""'Share on LinkedIn' links: open LinkedIn's own composer pre-filled, no API or OAuth.

The person posting presses Post on LinkedIn, in their own session — nothing here can
publish on its own, which is what makes this safe for a public deployment.
"""

from urllib.parse import quote, urlencode

COMPOSE_URL = "https://www.linkedin.com/feed/"
OFFSITE_URL = "https://www.linkedin.com/sharing/share-offsite/"


def share_text(post: str, article_url: str | None = None) -> str:
    """The post, optionally with the source article on its own line before the hashtags,
    so LinkedIn attaches a link preview card for it."""
    post = post.strip()
    if not article_url:
        return post
    lines = post.splitlines()
    if lines and lines[-1].strip() and all(w.startswith("#") for w in lines[-1].split()):
        body, tags = "\n".join(lines[:-1]).rstrip(), lines[-1].strip()
        return f"{body}\n\n{article_url}\n\n{tags}"
    return f"{post}\n\n{article_url}"


def compose_url(text: str) -> str:
    """LinkedIn's composer with the text pre-filled."""
    return f"{COMPOSE_URL}?{urlencode({'shareActive': 'true', 'text': text}, quote_via=quote)}"


def article_share_url(article_url: str) -> str:
    """LinkedIn's official share plugin: a new post with just the article's link card."""
    return f"{OFFSITE_URL}?{urlencode({'url': article_url}, quote_via=quote)}"
