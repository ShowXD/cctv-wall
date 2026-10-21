"""libvlc tuning for the wall: one set of options chosen for weak PCs.

How many tiles a page holds is the operator's choice (Workspace.tiles_per_page);
the per-stream cost is fixed here.

Why these options help on slow machines:
    --avcodec-hw=any          let the GPU decode H.264/H.265 instead of the CPU
    --no-audio                CCTV monitoring is silent by design; never decode audio
    :avcodec-skiploopfilter   skip deblocking on non-reference frames — a large CPU saving
    --no-osd                  no on-screen-display rendering
Statistics stay on: they are a few counters per frame, and the status overlay reads them.
    --drop-late-frames        stay live instead of queueing frames that are already late
"""
from __future__ import annotations

RTSP_PREFIX = "rtsp://"

# VLC is embedded in a Qt native surface.  Let Qt own mouse/keyboard input so double-click
# focus and the right-click stream menu are reliable on Windows.
INSTANCE_ARGS = (
    "--no-video-title-show", "--no-snapshot-preview", "--no-sub-autodetect-file",
    "--no-mouse-events", "--no-keyboard-events", "--no-fullscreen", "--quiet",
    "--no-audio", "--avcodec-hw=any", "--no-osd",
    "--network-caching=1000", "--live-caching=1000", "--drop-late-frames",
)
STREAM_OPTIONS = (":avcodec-skiploopfilter=nonref", ":clock-jitter=0")


def media_options_for(url: str) -> tuple[str, ...]:
    """Per-stream libvlc options: transport plus the shared tuning."""
    options: list[str] = list(STREAM_OPTIONS)
    if url.startswith(RTSP_PREFIX):
        # TCP costs a little latency and buys freedom from packet-loss smearing.
        options.append(":rtsp-tcp")
    return tuple(options)
