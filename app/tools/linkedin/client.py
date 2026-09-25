"""Minimal LinkedIn REST client: who am I, upload an image, and create a post."""

import re

import httpx

API = "https://api.linkedin.com"
POST_URL = "https://www.linkedin.com/feed/update/{urn}/"

# "little" text format reserved characters (Posts API commentary). Unescaped, they can
# silently truncate or mangle the post, e.g. everything after "(" disappearing.
_RESERVED = set("\\|{}@[]()<>#*_~")
_HASHTAG = re.compile(r"#[A-Za-z0-9]+")


class LinkedInError(RuntimeError):
    pass


class LinkedInAuthError(LinkedInError):
    """Missing, expired or insufficient token: the fix is `linkedin-poster auth`."""


def escape_little(text: str) -> str:
    """Escape reserved characters, keeping #hashtags as real hashtags."""
    out: list[str] = []
    pos = 0
    for m in _HASHTAG.finditer(text):
        out.append(_escape_plain(text[pos : m.start()]))
        out.append(m.group())
        pos = m.end()
    out.append(_escape_plain(text[pos:]))
    return "".join(out)


def _escape_plain(text: str) -> str:
    return "".join(f"\\{ch}" if ch in _RESERVED else ch for ch in text)


def post_url(urn: str) -> str:
    return POST_URL.format(urn=urn)


class LinkedInClient:
    def __init__(self, access_token: str, *, version: str, timeout: float = 30):
        self._http = httpx.Client(
            base_url=API,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {access_token}",
                "LinkedIn-Version": version,
                "X-Restli-Protocol-Version": "2.0.0",
            },
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._http.close()

    def userinfo(self) -> dict:
        """OpenID Connect profile: `sub` is the member id used in urn:li:person:{sub}."""
        resp = self._http.get("/v2/userinfo")
        _raise_for(resp, "fetch your LinkedIn profile")
        return resp.json()

    def upload_image(self, owner_urn: str, data: bytes) -> str:
        """Images API: register an upload, PUT the bytes; returns the image URN for a post."""
        resp = self._http.post(
            "/rest/images",
            params={"action": "initializeUpload"},
            json={"initializeUploadRequest": {"owner": owner_urn}},
        )
        _raise_for(resp, "start the image upload")
        value = resp.json().get("value") or {}
        upload_url, urn = value.get("uploadUrl"), value.get("image")
        if not upload_url or not urn:
            raise LinkedInError("LinkedIn returned no upload URL for the image.")
        put = self._http.put(upload_url, content=data, timeout=120)
        _raise_for(put, "upload the image")
        return urn

    def create_post(
        self, author_urn: str, text: str, *, image_urn: str | None = None, alt_text: str = ""
    ) -> str:
        """Publish a public post (text, optionally with one image); returns its URN. Never
        retried automatically: a timeout or 5xx may still have created the post."""
        body = {
            "author": author_urn,
            "commentary": escape_little(text),
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        if image_urn:
            body["content"] = {"media": {"id": image_urn, "altText": alt_text[:4000]}}
        resp = self._http.post("/rest/posts", json=body)
        _raise_for(resp, "publish the post")
        urn = resp.headers.get("x-restli-id")
        if not urn:
            raise LinkedInError("LinkedIn accepted the post but returned no post ID.")
        return urn


def _raise_for(resp: httpx.Response, action: str) -> None:
    if resp.is_success:
        return
    try:
        detail = resp.json().get("message") or resp.text
    except ValueError:
        detail = resp.text
    detail = (detail or "").strip()[:300]
    if resp.status_code == 401:
        raise LinkedInAuthError(
            f"LinkedIn rejected the token while trying to {action} (expired or revoked). "
            "Run `linkedin-poster auth` again."
        )
    if resp.status_code == 403:
        raise LinkedInAuthError(
            f"LinkedIn denied permission to {action}: {detail}. Make sure the app has the "
            "'Share on LinkedIn' product and re-run `linkedin-poster auth`."
        )
    if resp.status_code == 429:
        raise LinkedInError(f"LinkedIn rate limit hit while trying to {action}. Try again later.")
    raise LinkedInError(f"LinkedIn error {resp.status_code} while trying to {action}: {detail}")
