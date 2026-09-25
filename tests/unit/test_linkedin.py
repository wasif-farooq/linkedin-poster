import contextlib
import json
import socket
import stat
import threading
import time
import urllib.request
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx

from app.config import get_settings
from app.tools.linkedin import oauth
from app.tools.linkedin.client import (
    LinkedInAuthError,
    LinkedInClient,
    LinkedInError,
    escape_little,
    post_url,
)

POSTS = "https://api.linkedin.com/rest/posts"
USERINFO = "https://api.linkedin.com/v2/userinfo"


# --- little-format escaping -----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("plain text", "plain text"),
        ("Claude (Anthropic) [1]", r"Claude \(Anthropic\) \[1\]"),
        ("a_b *c* ~d~ <e> {f} | @g \\h", r"a\_b \*c\* \~d\~ \<e\> \{f\} \| \@g \\h"),
        ("Ship it #AIEngineering #LLM", "Ship it #AIEngineering #LLM"),  # hashtags stay live
        ("Issue #42 and C# code", "Issue #42 and C\\# code"),  # '#' not starting a tag is escaped
        ("→ arrows • bullets — dashes", "→ arrows • bullets — dashes"),
    ],
)
def test_escape_little(text, expected):
    assert escape_little(text) == expected


def test_post_url():
    assert post_url("urn:li:share:1") == "https://www.linkedin.com/feed/update/urn:li:share:1/"


# --- client ---------------------------------------------------------------------------


@respx.mock
def test_create_post_sends_versioned_request_and_returns_urn():
    route = respx.post(POSTS).mock(
        return_value=httpx.Response(201, headers={"x-restli-id": "urn:li:share:123"})
    )
    with LinkedInClient("tok", version="202609") as client:
        urn = client.create_post("urn:li:person:abc", "Hello (world)\n\n#AI")
    assert urn == "urn:li:share:123"
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer tok"
    assert req.headers["LinkedIn-Version"] == "202609"
    assert req.headers["X-Restli-Protocol-Version"] == "2.0.0"
    body = json.loads(req.content)
    assert body["author"] == "urn:li:person:abc"
    assert body["commentary"] == "Hello \\(world\\)\n\n#AI"
    assert body["visibility"] == "PUBLIC" and body["lifecycleState"] == "PUBLISHED"
    assert body["distribution"]["feedDistribution"] == "MAIN_FEED"


@respx.mock
def test_image_upload_then_post_with_media():
    init = respx.post("https://api.linkedin.com/rest/images").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": {
                    "uploadUrl": "https://www.linkedin.com/dms-uploads/abc",
                    "image": "urn:li:image:C4D",
                }
            },
        )
    )
    upload = respx.put("https://www.linkedin.com/dms-uploads/abc").mock(
        return_value=httpx.Response(201)
    )
    post = respx.post(POSTS).mock(
        return_value=httpx.Response(201, headers={"x-restli-id": "urn:li:share:9"})
    )
    with LinkedInClient("tok", version="202609") as client:
        urn = client.upload_image("urn:li:person:abc", b"PNGDATA")
        client.create_post("urn:li:person:abc", "Hi", image_urn=urn, alt_text="A lake")
    assert init.calls.last.request.url.params["action"] == "initializeUpload"
    assert json.loads(init.calls.last.request.content) == {
        "initializeUploadRequest": {"owner": "urn:li:person:abc"}
    }
    assert upload.calls.last.request.content == b"PNGDATA"
    body = json.loads(post.calls.last.request.content)
    assert body["content"] == {"media": {"id": "urn:li:image:C4D", "altText": "A lake"}}


@respx.mock
def test_userinfo():
    respx.get(USERINFO).mock(return_value=httpx.Response(200, json={"sub": "abc", "name": "Me"}))
    with LinkedInClient("tok", version="202609") as client:
        assert client.userinfo()["sub"] == "abc"


@respx.mock
@pytest.mark.parametrize(
    ("status", "error", "fragment"),
    [
        (401, LinkedInAuthError, "auth"),
        (403, LinkedInAuthError, "Share on LinkedIn"),
        (429, LinkedInError, "rate limit"),
        (422, LinkedInError, "boom"),
    ],
)
def test_create_post_errors(status, error, fragment):
    route = respx.post(POSTS).mock(return_value=httpx.Response(status, json={"message": "boom"}))
    with LinkedInClient("tok", version="202609") as client, pytest.raises(error, match=fragment):
        client.create_post("urn:li:person:abc", "x")
    assert route.call_count == 1  # never retried: a failed POST may still have posted


@respx.mock
def test_create_post_without_id_header():
    respx.post(POSTS).mock(return_value=httpx.Response(201))
    with (
        LinkedInClient("tok", version="202609") as client,
        pytest.raises(LinkedInError, match="no post ID"),
    ):
        client.create_post("urn:li:person:abc", "x")


# --- token storage --------------------------------------------------------------------


def test_token_roundtrip_and_permissions():
    token = oauth.LinkedInToken("secret", time.time() + 10 * 86400, "abc", "Me")
    oauth.save_token(token)
    assert stat.S_IMODE(oauth.TOKEN_PATH.stat().st_mode) == 0o600
    loaded = oauth.load_token()
    assert loaded.author_urn == "urn:li:person:abc" and loaded.days_left in (9, 10)


def test_missing_and_expired_tokens():
    with pytest.raises(LinkedInAuthError, match="Not connected"):
        oauth.load_token()
    oauth.save_token(oauth.LinkedInToken("t", time.time() + 60, "abc"))  # inside expiry margin
    with pytest.raises(LinkedInAuthError, match="expired"):
        oauth.load_token()


# --- full OAuth flow (real local callback server, mocked LinkedIn endpoints) -----------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


@pytest.fixture
def linkedin_app(monkeypatch):
    settings = get_settings()
    port = _free_port()
    monkeypatch.setattr(settings, "linkedin_client_id", "cid")
    monkeypatch.setattr(settings, "linkedin_client_secret", "csecret")
    monkeypatch.setattr(settings, "linkedin_redirect_uri", f"http://localhost:{port}/callback")
    return settings


def _browser(query_for):
    """Simulates the user approving in the browser: LinkedIn redirects to our callback."""

    def on_url(url):
        params = parse_qs(urlsplit(url).query)
        assert params["scope"] == ["openid profile w_member_social"]
        redirect = params["redirect_uri"][0]
        query = query_for(params["state"][0])

        def hit():
            time.sleep(0.2)
            with contextlib.suppress(Exception):  # 400 responses raise; that's fine here
                urllib.request.urlopen(f"{redirect}?{query}", timeout=5).read()

        threading.Thread(target=hit, daemon=True).start()

    return on_url


@respx.mock
def test_auth_flow_saves_token(linkedin_app):
    token_route = respx.post(oauth.TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "new-tok", "expires_in": 5184000})
    )
    respx.get(USERINFO).mock(return_value=httpx.Response(200, json={"sub": "m1", "name": "Me"}))
    respx.route(host="localhost").pass_through()

    token = oauth.run_auth_flow(
        open_browser=False, timeout=10, on_url=_browser(lambda s: f"code=abc&state={s}")
    )

    assert token.member_id == "m1" and token.days_left >= 59
    form = parse_qs(token_route.calls.last.request.content.decode())
    assert form["code"] == ["abc"] and form["client_secret"] == ["csecret"]
    assert oauth.load_token().access_token == "new-tok"


@respx.mock
def test_auth_flow_rejects_state_mismatch(linkedin_app):
    respx.route(host="localhost").pass_through()
    with pytest.raises(LinkedInAuthError, match="State mismatch"):
        oauth.run_auth_flow(
            open_browser=False, timeout=10, on_url=_browser(lambda s: "code=abc&state=forged")
        )


def test_auth_requires_app_credentials(monkeypatch):
    monkeypatch.setattr(get_settings(), "linkedin_client_id", "")
    with pytest.raises(LinkedInAuthError, match="LINKEDIN_CLIENT_ID"):
        oauth.run_auth_flow(open_browser=False)
