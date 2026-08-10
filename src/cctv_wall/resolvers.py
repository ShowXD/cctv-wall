"""Turning a source URL into something libvlc can open.

Most URLs need nothing done to them; YouTube pages must be resolved to a real
media URL first. Both cases satisfy the same StreamResolver protocol, so the wall
depends on the abstraction and never asks "is this YouTube?" itself.

Adding a site (Twitch, a DVR web player, ...) means adding a resolver class and
listing it in default_resolver() — the wall stays untouched.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Protocol, Sequence

from cctv_wall import quality as quality_module
from cctv_wall.urls import is_youtube

YT_DLP_TIMEOUT_SECONDS = 60


class ResolveError(RuntimeError):
    """The URL cannot be turned into a playable stream, with a reason for the user."""


class StreamResolver(Protocol):
    """Knows whether it can handle a URL, and how to make it playable."""

    def handles(self, url: str) -> bool: ...

    def resolve(self, url: str, quality: str) -> str: ...


class PassthroughResolver:
    """RTSP, HTTP, HLS and local files are already playable. The last resort."""

    def handles(self, url: str) -> bool:
        return True

    def resolve(self, url: str, quality: str) -> str:
        return url


class YouTubeResolver:
    """Asks yt-dlp for a single muxed stream no taller than the chosen quality."""

    def __init__(self, executable: str | None = None,
                 timeout: int = YT_DLP_TIMEOUT_SECONDS) -> None:
        self._executable = executable
        self._timeout = timeout

    def handles(self, url: str) -> bool:
        return is_youtube(url)

    def resolve(self, url: str, quality: str) -> str:
        """Prefer the CLI; fall back to the library, which is what a frozen exe has."""
        executable = self._executable or shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
        if executable:
            return self._resolve_with_cli(executable, url, quality)
        return self._resolve_with_library(url, quality)

    def _resolve_with_cli(self, executable: str, url: str, quality: str) -> str:
        command = [executable, "-f", self._format(quality), "-g", "--no-warnings", url]
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=self._timeout)
        except (OSError, subprocess.SubprocessError) as e:
            raise ResolveError(f"could not run yt-dlp: {e}") from e
        if result.returncode != 0 or not result.stdout.strip():
            reason = (result.stderr or "").strip().splitlines()
            raise ResolveError(f"yt-dlp failed: {reason[-1][:160] if reason else 'no output'}")
        return result.stdout.strip().splitlines()[0]

    def _resolve_with_library(self, url: str, quality: str) -> str:
        """Inside a PyInstaller exe there is no yt-dlp on PATH, only the module."""
        try:
            from yt_dlp import YoutubeDL
        except ImportError as e:
            raise ResolveError("yt-dlp is unavailable: not on PATH and not importable") from e
        options = {"format": self._format(quality), "quiet": True, "no_warnings": True,
                   "noplaylist": True, "socket_timeout": self._timeout}
        try:
            with YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=False)
        except Exception as e:  # yt-dlp raises a wide range of its own error types
            raise ResolveError(f"yt-dlp failed: {str(e)[:160]}") from e
        stream = (info or {}).get("url")
        if not stream:
            raise ResolveError("yt-dlp returned no playable stream URL")
        return str(stream)

    @staticmethod
    def _format(quality: str) -> str:
        height = quality_module.height_for(quality)
        cap = f"[height<={height}]" if height else ""
        # A single muxed stream keeps libvlc from having to pair audio and video.
        return f"best{cap}[protocol^=http]/best{cap}/best"


class ResolverChain:
    """First resolver that claims the URL wins."""

    def __init__(self, resolvers: Sequence[StreamResolver]) -> None:
        if not resolvers:
            raise ValueError("a resolver chain needs at least one resolver")
        self._resolvers = tuple(resolvers)

    def handles(self, url: str) -> bool:
        return any(r.handles(url) for r in self._resolvers)

    def resolve(self, url: str, quality: str) -> str:
        for resolver in self._resolvers:
            if resolver.handles(url):
                return resolver.resolve(url, quality)
        raise ResolveError(f"no resolver can handle {url!r}")


def default_resolver() -> ResolverChain:
    """YouTube first, everything else straight through."""
    return ResolverChain((YouTubeResolver(), PassthroughResolver()))
