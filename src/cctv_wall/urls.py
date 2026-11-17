"""Camera URLs at play time: credentials go in only here, plus stream switching and redaction.

Separate from the model so playback concerns never touch validation, and from the GUI
so they stay testable as plain functions.
"""
from __future__ import annotations

import re
from urllib.parse import quote, urlsplit, urlunsplit

from cctv_wall.models import Camera

MASK = "****"
_GENERIC_STREAMS = ("1", "2", "3", "4")
# (marker, the value each stream takes: stream 1 is values[0]). Group 1 is kept as is, so a
# channel number around the marker (Hikvision's "1" in 101, Dahua's channel=) never changes.
_STREAM_MARKERS = (
    (re.compile(r"(?i)(/channels/\d+?)(0[1-4])(?=$|[/?#&])"), ("01", "02", "03", "04")),  # Hikvision
    (re.compile(r"(?i)([?&]subtype=)([0-2])(?![0-9])"), ("0", "1", "2")),                  # Dahua
    (re.compile(r"(?i)([?&]streamtype=)(main|sub)(?![a-z])"), ("main", "sub")),
    (re.compile(r"(?i)(stream)([1-4])"), _GENERIC_STREAMS),
    (re.compile(r"(?i)([?&]stream=)([1-4])"), _GENERIC_STREAMS),
)
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


def _stream_marker(url: str) -> tuple[re.Match[str], tuple[str, ...]] | None:
    """The first recognised stream marker after the host, with the values its streams take."""
    tail = url[_authority_end(url):]
    for pattern, values in _STREAM_MARKERS:
        match = pattern.search(tail)
        if match:
            return match, values
    return None


def stream_count(url: str) -> int:
    """How many streams the URL's format can name; 0 when no marker is recognised."""
    found = _stream_marker(url)
    return len(found[1]) if found else 0


def stream_from_direct_url(url: str) -> int | None:
    """Return the explicit stream number in a direct URL, when it is safe to change."""
    found = _stream_marker(url)
    if found is None:
        return None
    match, values = found
    return values.index(match.group(2).lower()) + 1


def direct_url_with_stream(url: str, stream: int) -> str | None:
    """Replace recognised stream markers without guessing a vendor-specific URL format.
    None when no marker is recognised or the format has no such stream."""
    found = _stream_marker(url)
    if found is None or not 1 <= stream <= len(found[1]):
        return None
    values = found[1]
    cut = _authority_end(url)
    head, tail = url[:cut], url[cut:]
    # Every marker of the same kind changes together (".../stream1?stream=1" stays consistent).
    for pattern, kind in _STREAM_MARKERS:
        if kind is values:
            tail = pattern.sub(lambda match: f"{match.group(1)}{values[stream - 1]}", tail)
    return head + tail

