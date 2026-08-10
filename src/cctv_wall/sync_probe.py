"""Read-only RTSP capability probe for strict multi-camera time synchronisation.

This deliberately does not decode or display video.  It opens the same RTSP session
the player would, requests RTP/RTCP over the existing TCP connection, then observes
RTCP Sender Reports.  An SR is the essential evidence that a source can map its RTP
clock to an absolute NTP clock; RTP timestamps alone are not enough.
"""
from __future__ import annotations

import base64
import hashlib
import os
import socket
import time
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit, urlunsplit


PROBE_SECONDS = 8.0
SOCKET_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True, slots=True)
class SyncProbeResult:
    """Only safe-to-display values from one camera diagnostic session."""

    camera_label: str
    rtsp: bool
    codec: str = ""
    clock_rate: int | None = None
    sender_reports: int = 0
    ntp_seconds: int | None = None
    rtp_timestamp: int | None = None
    error: str = ""

    @property
    def can_strictly_sync(self) -> bool:
        # RFC 3550 permits a sender without wall-clock time to put zero here. Such a
        # report still proves RTP is alive, but cannot align cameras to a real second.
        return self.rtsp and self.sender_reports > 0 and bool(self.ntp_seconds)


class SyncProbeError(RuntimeError):
    """An RTSP server did not permit or complete the read-only diagnostic."""


class _RtspConnection:
    """Minimal RTSP-over-TCP client, including Basic and common Digest authentication."""

    def __init__(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme.lower() != "rtsp" or not parts.hostname:
            raise SyncProbeError("not an RTSP source")
        self._parts = parts
        self._host = parts.hostname
        self._port = parts.port or 554
        self._user = unquote(parts.username or "")
        self._password = unquote(parts.password or "")
        host = self._host if ":" not in self._host else f"[{self._host}]"
        self.url = urlunsplit(("rtsp", f"{host}:{self._port}", parts.path or "/", parts.query, ""))
        self._socket: socket.socket | None = None
        self._buffer = bytearray()
        self._sequence = 1
        self._session = ""
        self._auth_challenge = ""

    def __enter__(self) -> "_RtspConnection":
        self._socket = socket.create_connection((self._host, self._port), SOCKET_TIMEOUT_SECONDS)
        self._socket.settimeout(SOCKET_TIMEOUT_SECONDS)
        return self

    def __exit__(self, *_unused: object) -> None:
        if self._socket is not None:
            try:
                self.request("TEARDOWN", self.url)
            except (OSError, SyncProbeError):
                pass
            self._socket.close()

    def request(self, method: str, target: str, headers: dict[str, str] | None = None,
                body: str = "") -> tuple[int, dict[str, str], str]:
        extra = dict(headers or {})
        if self._auth_challenge:
            extra["Authorization"] = self._authentication_header(self._auth_challenge, method, target)
        if self._session:
            extra.setdefault("Session", self._session)
        extra["CSeq"] = str(self._sequence)
        self._sequence += 1
        extra.setdefault("User-Agent", "CCTV-Wall sync diagnostic")
        if body:
            extra["Content-Length"] = str(len(body.encode()))
        request = f"{method} {target} RTSP/1.0\r\n" + "".join(
            f"{key}: {value}\r\n" for key, value in extra.items()) + "\r\n" + body
        assert self._socket is not None
        self._socket.sendall(request.encode())
        status, response_headers, response_body = self._response()
        session = response_headers.get("session", "").split(";", 1)[0]
        if session:
            self._session = session
        return status, response_headers, response_body

    def authenticate(self) -> None:
        status, headers, _body = self.request("OPTIONS", self.url)
        if status != 401:
            if status >= 300:
                raise SyncProbeError(f"RTSP OPTIONS failed ({status})")
            return
        challenge = headers.get("www-authenticate", "")
        self._auth_challenge = challenge
        status, _headers, _body = self.request("OPTIONS", self.url)
        if status >= 300:
            raise SyncProbeError(f"RTSP authentication failed ({status})")

    def _authentication_header(self, challenge: str, method: str, target: str) -> str:
        if challenge.lower().startswith("basic "):
            token = base64.b64encode(f"{self._user}:{self._password}".encode()).decode()
            return f"Basic {token}"
        if not challenge.lower().startswith("digest "):
            raise SyncProbeError("RTSP server requested unsupported authentication")
        fields = _digest_fields(challenge[7:])
        realm, nonce = fields.get("realm", ""), fields.get("nonce", "")
        if not nonce:
            raise SyncProbeError("RTSP Digest authentication did not include a nonce")
        uri = urlsplit(target).path or "/"
        if urlsplit(target).query:
            uri += f"?{urlsplit(target).query}"
        digest = lambda value: hashlib.md5(value.encode()).hexdigest()  # noqa: S324 - RTSP Digest standard
        ha1 = digest(f"{self._user}:{realm}:{self._password}")
        ha2 = digest(f"{method}:{uri}")
        qop = fields.get("qop", "").split(",", 1)[0].strip()
        if qop:
            nonce_count, cnonce = "00000001", os.urandom(8).hex()
            response = digest(f"{ha1}:{nonce}:{nonce_count}:{cnonce}:{qop}:{ha2}")
            suffix = f", qop={qop}, nc={nonce_count}, cnonce=\"{cnonce}\""
        else:
            response, suffix = digest(f"{ha1}:{nonce}:{ha2}"), ""
        return (f'Digest username="{self._user}", realm="{realm}", nonce="{nonce}", '
                f'uri="{uri}", response="{response}"{suffix}')

    def _response(self) -> tuple[int, dict[str, str], str]:
        # A few NVRs begin interleaving RTP/RTCP as soon as SETUP succeeds, even while
        # their response to the next request is still in flight.  Those binary frames are
        # valid traffic, not a malformed RTSP status line; discard them before parsing.
        self._discard_interleaved_frames()
        header_bytes = self._read_until(b"\r\n\r\n")
        header_text = header_bytes.decode("iso-8859-1")
        lines = header_text.split("\r\n")
        try:
            status = int(lines[0].split()[1])
        except (IndexError, ValueError) as error:
            raise SyncProbeError("invalid RTSP response") from error
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.lower()] = value.strip()
        length = int(headers.get("content-length", "0"))
        return status, headers, self._read_exact(length).decode("utf-8", errors="replace")

    def _discard_interleaved_frames(self) -> None:
        while True:
            while not self._buffer:
                self._receive()
            if self._buffer[0] != ord("$"):
                return
            while len(self._buffer) < 4:
                self._receive()
            length = int.from_bytes(self._buffer[2:4], "big")
            while len(self._buffer) < 4 + length:
                self._receive()
            del self._buffer[:4 + length]

    def interleaved_packets(self, duration: float):
        """Yield channel/payload pairs until the observation window expires."""
        assert self._socket is not None
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            try:
                marker = self._read_exact(1)
            except socket.timeout:
                continue
            if marker != b"$":
                # Servers occasionally send keep-alive text. It is irrelevant after PLAY.
                continue
            channel = self._read_exact(1)[0]
            length = int.from_bytes(self._read_exact(2), "big")
            yield channel, self._read_exact(length)

    def _read_until(self, separator: bytes) -> bytes:
        while separator not in self._buffer:
            self._receive()
        index = self._buffer.index(separator)
        value = bytes(self._buffer[:index])
        del self._buffer[:index + len(separator)]
        return value

    def _read_exact(self, length: int) -> bytes:
        while len(self._buffer) < length:
            self._receive()
        value = bytes(self._buffer[:length])
        del self._buffer[:length]
        return value

    def _receive(self) -> None:
        assert self._socket is not None
        chunk = self._socket.recv(65_536)
        if not chunk:
            raise SyncProbeError("RTSP connection closed during diagnostic")
        self._buffer.extend(chunk)


def probe_rtsp(camera_label: str, url: str, duration: float = PROBE_SECONDS) -> SyncProbeResult:
    """Observe one source. Errors are returned for display rather than raised to the GUI."""
    if not url.lower().startswith("rtsp://"):
        return SyncProbeResult(camera_label, rtsp=False, error="not an RTSP source")
    try:
        with _RtspConnection(url) as connection:
            connection.authenticate()
            status, headers, sdp = connection.request("DESCRIBE", connection.url,
                                                       {"Accept": "application/sdp"})
            if status >= 300:
                raise SyncProbeError(f"RTSP DESCRIBE failed ({status})")
            # Cameras often provide a Content-Base different from the requested URL.
            # Resolving a relative a=control against it is required by RTSP and avoids
            # guessing path layouts for different NVR vendors.
            codec, clock_rate, control = _video_description(
                sdp, headers.get("content-base") or headers.get("content-location") or connection.url)
            status, _headers, _body = connection.request(
                "SETUP", control, {"Transport": "RTP/AVP/TCP;unicast;interleaved=0-1"})
            if status >= 300:
                raise SyncProbeError(f"RTSP SETUP failed ({status})")
            status, _headers, _body = connection.request("PLAY", connection.url, {"Range": "npt=0-"})
            if status >= 300:
                raise SyncProbeError(f"RTSP PLAY failed ({status})")
            reports, ntp, rtp = 0, None, None
            for channel, payload in connection.interleaved_packets(duration):
                if channel == 1:
                    found = _sender_reports(payload)
                    reports += len(found)
                    if found:
                        ntp, rtp = found[-1]
            return SyncProbeResult(camera_label, True, codec, clock_rate, reports, ntp, rtp)
    except (OSError, ValueError, SyncProbeError) as error:
        return SyncProbeResult(camera_label, True, error=str(error))


def _video_description(sdp: str, base_url: str) -> tuple[str, int | None, str]:
    """Return codec, RTP clock rate and absolute video control URL from SDP."""
    media, codec, clock_rate, control = "", "", None, ""
    for line in sdp.splitlines():
        line = line.strip()
        if line.startswith("m="):
            media = line.split()[0][2:]
        elif media == "video" and line.startswith("a=rtpmap:"):
            value = line.split(None, 1)[-1].split("/")
            codec = value[0]
            try:
                clock_rate = int(value[1])
            except (IndexError, ValueError):
                pass
        elif media == "video" and line.startswith("a=control:"):
            control = line.split(":", 1)[1]
    if not control or control == "*":
        return codec, clock_rate, base_url
    if control.startswith("rtsp://"):
        return codec, clock_rate, control
    return codec, clock_rate, base_url.rstrip("/") + "/" + control.lstrip("/")


def _sender_reports(payload: bytes) -> list[tuple[int, int]]:
    """Extract (NTP seconds, RTP timestamp) from compound RTCP SR packets."""
    reports: list[tuple[int, int]] = []
    offset = 0
    while offset + 4 <= len(payload):
        packet_type = payload[offset + 1]
        length = (int.from_bytes(payload[offset + 2:offset + 4], "big") + 1) * 4
        if length < 4 or offset + length > len(payload):
            break
        if packet_type == 200 and length >= 28:  # RTCP Sender Report
            ntp_seconds = int.from_bytes(payload[offset + 8:offset + 12], "big")
            rtp_timestamp = int.from_bytes(payload[offset + 16:offset + 20], "big")
            reports.append((ntp_seconds, rtp_timestamp))
        offset += length
    return reports


def _digest_fields(value: str) -> dict[str, str]:
    """Parse quoted Digest parameters without splitting commas inside quoted qop values."""
    fields: dict[str, str] = {}
    current, quoted = "", False
    for character in value + ",":
        if character == '"':
            quoted = not quoted
        if character == "," and not quoted:
            if "=" in current:
                key, field = current.split("=", 1)
                fields[key.strip().lower()] = field.strip().strip('"')
            current = ""
        else:
            current += character
    return fields
