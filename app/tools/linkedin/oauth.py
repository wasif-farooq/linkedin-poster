"""One-time LinkedIn OAuth (3-legged, OpenID Connect) with a local callback server.

LinkedIn member tokens last ~60 days and (for most apps) can't be refreshed, so
`linkedin-poster auth` is simply re-run when the token expires.
"""

import http.server
import json
import os
import secrets
import threading
import time
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from app.config import DATA_DIR, get_settings
from app.tools.linkedin.client import LinkedInAuthError, LinkedInClient

AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
SCOPES = "openid profile w_member_social"
TOKEN_PATH = DATA_DIR / "linkedin_token.json"
EXPIRY_MARGIN = 3600  # treat tokens as expired an hour early


@dataclass
class LinkedInToken:
    access_token: str
    expires_at: float
    member_id: str
    name: str = ""

    @property
    def author_urn(self) -> str:
        return f"urn:li:person:{self.member_id}"

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at - EXPIRY_MARGIN

    @property
    def days_left(self) -> int:
        return max(int((self.expires_at - time.time()) // 86400), 0)


def load_token(path: Path | None = None) -> LinkedInToken:
    """The saved token, or LinkedInAuthError explaining how to get one."""
    path = path or TOKEN_PATH
    try:
        token = LinkedInToken(**json.loads(path.read_text()))
    except FileNotFoundError:
        raise LinkedInAuthError(
            "Not connected to LinkedIn yet. Run `linkedin-poster auth`."
        ) from None
    except (ValueError, TypeError) as exc:
        raise LinkedInAuthError(
            f"Saved LinkedIn token is unreadable ({exc}). Run `linkedin-poster auth`."
        ) from exc
    if token.expired:
        raise LinkedInAuthError("Your LinkedIn token has expired. Run `linkedin-poster auth`.")
    return token


def save_token(token: LinkedInToken, path: Path | None = None) -> None:
    path = path or TOKEN_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    # It's a credential: create it owner-only from the start (no world-readable window).
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(asdict(token), indent=2))
    os.chmod(path, 0o600)  # also tighten a pre-existing file


def authorization_url(state: str) -> str:
    s = get_settings()
    return (
        AUTHORIZE_URL
        + "?"
        + urlencode(
            {
                "response_type": "code",
                "client_id": s.linkedin_client_id,
                "redirect_uri": s.linkedin_redirect_uri,
                "state": state,
                "scope": SCOPES,
            }
        )
    )


def exchange_code(code: str) -> tuple[str, int]:
    s = get_settings()
    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": s.linkedin_client_id,
            "client_secret": s.linkedin_client_secret,
            "redirect_uri": s.linkedin_redirect_uri,
        },
        timeout=30,
    )
    if not resp.is_success:
        raise LinkedInAuthError(f"Token exchange failed ({resp.status_code}): {resp.text[:300]}")
    data = resp.json()
    return data["access_token"], int(data.get("expires_in", 0))


def run_auth_flow(
    *, open_browser: bool = True, timeout: float = 300, on_url=print
) -> LinkedInToken:
    """Open the consent page, catch the redirect on localhost, save the token."""
    s = get_settings()
    if not (s.linkedin_client_id and s.linkedin_client_secret):
        raise LinkedInAuthError(
            "Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET (in .env or your shell) first."
        )
    redirect = urlsplit(s.linkedin_redirect_uri)
    state = secrets.token_urlsafe(24)
    result: dict = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib API
            url = urlsplit(self.path)
            if url.path != redirect.path:
                self.send_response(404)
                self.end_headers()
                return
            params = {k: v[0] for k, v in parse_qs(url.query).items()}
            if params.get("state") != state:
                result["error"] = "State mismatch (possible CSRF); try again."
            elif "error" in params:
                result["error"] = params.get("error_description") or params["error"]
            else:
                result["code"] = params.get("code")
            ok = "code" in result
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Connected! You can close this tab." if ok else f"Failed: {result.get('error')}"
            self.wfile.write(f"<h2>LinkedIn Poster</h2><p>{msg}</p>".encode())
            done.set()

        def log_message(self, *args):  # keep the terminal quiet
            pass

    server = http.server.HTTPServer(
        (redirect.hostname or "localhost", redirect.port or 80), Handler
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = authorization_url(state)
        on_url(url)
        if open_browser:
            webbrowser.open(url)
        if not done.wait(timeout):
            raise LinkedInAuthError("Timed out waiting for the LinkedIn redirect.")
    finally:
        server.shutdown()
        server.server_close()

    if "code" not in result:
        raise LinkedInAuthError(f"LinkedIn authorization failed: {result.get('error')}")
    return complete_authorization(result["code"])


WEB_CALLBACK_PATH = "/api/linkedin/callback"


def uses_web_callback() -> bool:
    """True when LinkedIn redirects to this app's own callback route (a deployed server),
    rather than to the one-off localhost server that `auth` runs on a workstation."""
    return urlsplit(get_settings().linkedin_redirect_uri).path == WEB_CALLBACK_PATH


def complete_authorization(code: str) -> LinkedInToken:
    """Exchange the authorization code, look up who connected, save the token."""
    access_token, expires_in = exchange_code(code)
    with LinkedInClient(access_token, version=get_settings().linkedin_version) as client:
        me = client.userinfo()
    token = LinkedInToken(
        access_token=access_token,
        expires_at=time.time() + (expires_in or 60 * 86400),
        member_id=me["sub"],
        name=me.get("name", ""),
    )
    save_token(token)
    return token
