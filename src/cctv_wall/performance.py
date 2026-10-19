"""Performance profiles — the knobs that decide whether a weak PC copes.

Three named presets instead of a dozen checkboxes. Each one bundles the libvlc
instance arguments, the per-stream options, and how many tiles a page may hold.
Adding a preset means adding a PerformanceProfile; no other module changes.

Why these options help on slow machines:
    --avcodec-hw=any          let the GPU decode H.264/H.265 instead of the CPU
    --no-audio                audio decoding and mixing per tile is waste on CCTV
    :avcodec-skiploopfilter   drops the deblocking filter — the biggest CPU saving
    :avcodec-skip-frame=1     skip non-reference frames when already behind
    --no-osd / --no-stats     no overlay rendering, no bookkeeping
    tiles_per_page            hard cap on concurrent decoders; the rest wait on page 2
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from cctv_wall import quality as quality_module

RTSP_PREFIX = "rtsp://"


@dataclass(frozen=True, slots=True)
class PerformanceProfile:
    """How hard the app is allowed to work the machine."""

    key: str
    instance_args: tuple[str, ...]
    stream_options: tuple[str, ...]
    tiles_per_page: int

    def __post_init__(self) -> None:
        if self.tiles_per_page < 1:
            raise ValueError("tiles_per_page must be at least 1")


# VLC is embedded in a Qt native surface.  Let Qt own mouse/keyboard input so double-click
# focus and the right-click stream menu are reliable on Windows.
# CCTV monitoring is silent by design, so no profile decodes audio at all.
_SHARED_ARGS = ("--no-video-title-show", "--no-snapshot-preview", "--no-sub-autodetect-file",
                "--no-mouse-events", "--no-keyboard-events", "--no-fullscreen", "--quiet",
                "--no-audio")

LOW_END = PerformanceProfile(
    key="low_end",
    instance_args=_SHARED_ARGS + (
        "--avcodec-hw=any", "--no-osd", "--no-stats",
        "--network-caching=1500", "--live-caching=1500", "--drop-late-frames",
        "--skip-frames",
    ),
    stream_options=(":avcodec-skiploopfilter=all", ":avcodec-skip-frame=1",
                    ":clock-jitter=0", ":clock-synchro=0"),
    tiles_per_page=4,
)

BALANCED = PerformanceProfile(
    key="balanced",
    instance_args=_SHARED_ARGS + (
        "--avcodec-hw=any", "--no-osd",
        "--network-caching=1000", "--live-caching=1000", "--drop-late-frames",
    ),
    stream_options=(":avcodec-skiploopfilter=nonref", ":clock-jitter=0"),
    tiles_per_page=9,
)

FULL = PerformanceProfile(
    key="full",
    instance_args=_SHARED_ARGS + ("--avcodec-hw=any", "--network-caching=1000"),
    stream_options=(),
    tiles_per_page=16,
)

PROFILES: Mapping[str, PerformanceProfile] = MappingProxyType(
    {p.key: p for p in (LOW_END, BALANCED, FULL)})


def profile_for(key: str) -> PerformanceProfile:
    """Never raises: an unknown key falls back to the safest preset."""
    return PROFILES.get(key, LOW_END)


def media_options_for(url: str, quality: str, profile: PerformanceProfile) -> tuple[str, ...]:
    """Per-stream libvlc options: transport, size cap, and the profile's own tuning."""
    options: list[str] = list(profile.stream_options)
    if url.startswith(RTSP_PREFIX):
        # TCP costs a little latency and buys freedom from packet-loss smearing.
        options.append(":rtsp-tcp")
    height = quality_module.height_for(quality)
    if height is not None:
        options.append(f":adaptive-maxheight={height}")
    return tuple(options)
