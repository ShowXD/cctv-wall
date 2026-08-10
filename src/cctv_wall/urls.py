"""Turn a Camera into a playable URL.

The only module that knows how the pieces (host, port, credentials, vendor path)
become a string. Separate from the model so adding a protocol never touches
validation, and separate from the GUI so it stays testable as a plain function.
"""
from __future__ import annotations

import re
from urllib.parse import quote, urlparse, urlsplit, urlunsplit

from cctv_wall import vendors
from cctv_wall.models import Camera

RTSP_SCHEME = "rtsp"
YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"})
MASK = "****"
_STREAM_PATH_TOKEN = re.compile(r"(?i)(stream)([1-4])")
_STREAM_QUERY_TOKEN = re.compile(r"(?i)([?&]stream=)([1-4])")


def is_youtube(url: str) -> bool:
    """True only when the host itself is YouTube — not when it merely appears in the path."""
    return urlparse(url).hostname in YOUTUBE_HOSTS


def build_url(camera: Camera) -> str:
    """A direct url wins; otherwise assemble rtsp://user:pass@host:port/vendor-path."""
    if camera.url:
        return camera.url
    template = vendors.template_for(camera.vendor, camera.path_template)
    path = vendors.render_path(template, camera.stream)
    return f"{RTSP_SCHEME}://{_credentials(camera)}{camera.host}:{camera.port}/{path}"


def display_url(camera: Camera) -> str:
    """build_url with the password replaced by asterisks, safe to show on screen."""
    if camera.url:
        return _mask_url_password(camera.url)
    if not camera.user:
        return build_url(camera)
    user = quote(camera.user, safe="")
    return build_url(camera).replace(f"{user}:{_quoted_password(camera)}@",
                                     f"{user}:{MASK}@", 1)


def _mask_url_password(url: str) -> str:
    """Redact only a URL password; local paths and credential-free URLs stay untouched."""
    parsed = urlsplit(url)
    if parsed.username is None or parsed.password is None or not parsed.hostname:
        return url
    try:
        port = parsed.port
    except ValueError:
        # Leave an invalid URL unchanged so the editor can show its real validation error.
        return url
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"  # Re-add IPv6 brackets removed by urlsplit().
    endpoint = f"{host}:{port}" if port is not None else host
    netloc = f"{quote(parsed.username, safe='')}:{MASK}@{endpoint}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def stream_from_direct_url(url: str) -> int | None:
    """Return the explicit stream number in a direct URL, when it is safe to change."""
    match = _STREAM_PATH_TOKEN.search(url) or _STREAM_QUERY_TOKEN.search(url)
    return int(match.group(2)) if match else None


def direct_url_with_stream(url: str, stream: int) -> str | None:
    """Replace recognised stream markers without guessing a vendor-specific URL format."""
    if stream_from_direct_url(url) is None:
        return None
    updated = _STREAM_PATH_TOKEN.sub(lambda match: f"{match.group(1)}{stream}", url)
    return _STREAM_QUERY_TOKEN.sub(lambda match: f"{match.group(1)}{stream}", updated)


def _credentials(camera: Camera) -> str:
    if not camera.user:
        return ""
    return f"{quote(camera.user, safe='')}:{_quoted_password(camera)}@"


def _quoted_password(camera: Camera) -> str:
    return quote(camera.password, safe="")
