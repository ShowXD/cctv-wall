"""Turn a Camera into a playable URL.

The only module that knows how the pieces (host, port, credentials, vendor path)
become a string. Separate from the model so adding a protocol never touches
validation, and separate from the GUI so it stays testable as a plain function.
"""
from __future__ import annotations

import re
from urllib.parse import quote, urlsplit, urlunsplit

from cctv_wall.models import Camera

MASK = "****"
_STREAM_PATH_TOKEN = re.compile(r"(?i)(stream)([1-4])")
_STREAM_QUERY_TOKEN = re.compile(r"(?i)([?&]stream=)([1-4])")
_URL_CREDENTIALS = re.compile(r"(?i)([a-z][a-z0-9+.-]*)://[^@/\s]*@")


def build_url(camera: Camera) -> str:
    """The playable URL: the camera's url with its credentials put back in."""
    return _with_credentials(camera.url, camera.user, camera.password)


def _with_credentials(url: str, user: str, password: str) -> str:
    """Insert user:password into a network URL; local paths and empty users stay as they are."""
    parts = urlsplit(url)
    if not user or not parts.netloc:
        return url
    userinfo = quote(user, safe="") + (f":{quote(password, safe='')}" if password else "")
    return urlunsplit(parts._replace(netloc=f"{userinfo}@{parts.netloc}"))


def redact(text: str) -> str:
    """Mask credentials embedded in any URL inside free-form text, for logs and notices."""
    return _URL_CREDENTIALS.sub(lambda match: f"{match.group(1)}://{MASK}@", text)


def _authority_end(url: str) -> int:
    """Where the host part stops. A hostname such as `stream1.lan` is not a stream marker."""
    scheme = url.find("://")
    if scheme < 0:
        return 0
    start = scheme + len("://")
    stops = [index for index in (url.find(c, start) for c in "/?#") if index >= 0]
    return min(stops) if stops else len(url)


def stream_from_direct_url(url: str) -> int | None:
    """Return the explicit stream number in a direct URL, when it is safe to change."""
    tail = url[_authority_end(url):]
    match = _STREAM_PATH_TOKEN.search(tail) or _STREAM_QUERY_TOKEN.search(tail)
    return int(match.group(2)) if match else None


def direct_url_with_stream(url: str, stream: int) -> str | None:
    """Replace recognised stream markers without guessing a vendor-specific URL format."""
    if stream_from_direct_url(url) is None:
        return None
    cut = _authority_end(url)
    head, tail = url[:cut], url[cut:]
    tail = _STREAM_PATH_TOKEN.sub(lambda match: f"{match.group(1)}{stream}", tail)
    return head + _STREAM_QUERY_TOKEN.sub(lambda match: f"{match.group(1)}{stream}", tail)

