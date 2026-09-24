"""Publisher: gets the approved final text onto LinkedIn.

PUBLISH_MODE=share (default): returns a "Share on LinkedIn" link that opens LinkedIn's
composer pre-filled — the person presses Post there, so nothing can publish on its own.
PUBLISH_MODE=api: posts through the LinkedIn API, with the safety layers below.

Safety layers (in order):
1. the graph only routes here when state["approved"] (routing.APPROVAL_REQUIRED) — rechecked here;
2. identical text already published? return that post instead of posting twice;
3. an explicit "publish now?" confirmation via interrupt() for real posts;
4. the API call is never retried automatically (a timeout may still have created the post).
"""

from collections.abc import Mapping

from langgraph.types import interrupt

from app.config import get_settings
from app.db.repository import PostRepository
from app.tools.linkedin.client import LinkedInClient, post_url
from app.tools.linkedin.oauth import load_token
from app.tools.linkedin.share import compose_url, share_text


class NotApprovedError(RuntimeError):
    pass


def run(state: Mapping) -> dict:
    text = state.get("final_post")
    if not state.get("approved") or not text:
        raise NotApprovedError("The draft must be approved before it can be published.")

    topic = state.get("topic")
    title = topic if isinstance(topic, str) else (topic or {}).get("topic", "")
    sources = _source_urls(state)
    repo = PostRepository()

    existing = repo.find_published(text)
    if existing:
        return _result("already_published", existing.urn, existing.url)

    if get_settings().publish_mode == "share":
        # Nothing is posted from here: the person opens this link and presses Post on
        # LinkedIn. It's recorded as shared when they use it (POST …/shared).
        return _result("share_ready", None, compose_url(share_text(text)))

    if get_settings().publish_dry_run:
        repo.add(status="dry_run", topic=title, text=text, source_urls=sources)
        return _result("dry_run", None, None)

    token = load_token()  # raises LinkedInAuthError with instructions if missing/expired
    answer = interrupt(
        {"type": "publish_confirm", "post": text, "chars": len(text), "account": token.name}
    )
    if not (isinstance(answer, dict) and answer.get("confirm") is True):
        return _result("cancelled", None, None)

    with LinkedInClient(token.access_token, version=get_settings().linkedin_version) as client:
        urn = client.create_post(token.author_urn, text)
    url = post_url(urn)
    repo.add(status="published", topic=title, text=text, urn=urn, url=url, source_urls=sources)
    return _result("published", urn, url)


def _result(status: str, urn: str | None, url: str | None) -> dict:
    return {
        "publish_result": {"status": status, "urn": urn, "url": url},
        "post_urn": urn,
        "post_url": url,
    }


def _source_urls(state: Mapping) -> list[str]:
    brief = state.get("research_brief") or {}
    return [s["url"] for s in brief.get("sources", [])]
