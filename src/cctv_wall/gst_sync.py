"""Optional GStreamer backend for strict RTCP/NTP timestamp synchronisation.

The official ``gstreamer-bundle`` supplies the supported Python GI bindings on
Windows.  Using those bindings is important here: native video overlays and GObject
lifetimes must be managed by GStreamer, not hand-declared through ctypes.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from cctv_wall.event_log import logger
from cctv_wall.player import PlaybackError, PlaybackState
from cctv_wall.urls import redact

# A strict wall intentionally trades latency for the common presentation timestamp.
# Every element play() builds, kept here so --check can prove a deployed exe will link
# the pipeline instead of failing one tile at a time. test_sync.py keeps the two in step.
REQUIRED_ELEMENTS = ("rtspsrc", "rtph264depay", "h264parse", "decodebin",
                     "videoconvert", "d3d11videosink")
# The D3D11 decoder is preferable when a driver's implementation is usable.  The
# libav decoder is deliberately bundled as a CPU fallback for Windows 10 and older
# GPUs, where a D3D11 video sink may exist but no H.264 hardware decoder is exposed.
H264_DECODER_ELEMENTS = ("d3d11h264dec", "avdec_h264")
_NTP_SYNC_BUFFER_MS = 3_000
_PRESENTATION_DELAY_NS = _NTP_SYNC_BUFFER_MS * 1_000_000
_DLL_DIRECTORIES: list[object] = []


def _prepare_frozen_runtime() -> None:
    """Expose the explicitly bundled GStreamer runtime before importing GI."""
    root = getattr(sys, "_MEIPASS", "")
    if not root or sys.platform != "win32":
        return
    gstreamer = Path(root) / "gstreamer"
    runtime = gstreamer / "runtime"
    binary_directory = runtime / "bin"
    if binary_directory.is_dir():
        _DLL_DIRECTORIES.append(os.add_dll_directory(str(binary_directory)))
        # PyGObject itself checks this variable before loading gi/_gi*.pyd.
        os.environ["PYGI_DLL_DIRS"] = str(binary_directory)
        # add_dll_directory only covers libraries loaded through Python's own importer.
        # The DLLs named inside a typelib are opened by GLib's g_module_open(), which
        # calls LoadLibrary without LOAD_LIBRARY_SEARCH_USER_DIRS — so it never sees
        # those directories, and PATH is the only search path that reaches it. Without
        # this, gi imports fine and then Gst comes up hollow ("must be an interface").
        os.environ["PATH"] = os.pathsep.join(
            (str(binary_directory), os.environ.get("PATH", "")))
    plugin_root = gstreamer / "plugins"
    plugin_directories = [runtime / "lib" / "gstreamer-1.0"]
    if plugin_root.is_dir():
        plugin_directories.extend(path for path in plugin_root.iterdir() if path.is_dir())
    plugin_directories = [path for path in plugin_directories if path.is_dir()]
    if plugin_directories:
        os.environ["GST_PLUGIN_SYSTEM_PATH_1_0"] = os.pathsep.join(map(str, plugin_directories))
    scanner = runtime / "libexec" / "gstreamer-1.0" / "gst-plugin-scanner.exe"
    if scanner.is_file():
        os.environ["GST_PLUGIN_SCANNER_1_0"] = str(scanner)
    for key, directory in {
        "XDG_DATA_DIRS": runtime / "share",
        "XDG_CONFIG_DIRS": runtime / "etc" / "xdg",
    }.items():
        if directory.is_dir():
            os.environ[key] = str(directory)
    python_root = Path(root) / "gstreamer" / "python"
    python_site = python_root / "Lib" / "site-packages"
    typelib_directory = python_root / "Lib" / "girepository-1.0"
    if python_site.is_dir() and str(python_site) not in sys.path:
        sys.path.insert(0, str(python_site))
    typelib_directories = [typelib_directory, runtime / "lib" / "girepository-1.0"]
    existing_typelibs = [path for path in typelib_directories if path.is_dir()]
    if existing_typelibs:
        os.environ["GI_TYPELIB_PATH"] = os.pathsep.join(map(str, existing_typelibs))


def _load_gst() -> tuple[Any, Any]:
    """Load the official optional runtime only when the operator enables strict sync."""
    _prepare_frozen_runtime()
    try:
        # Deliberately dynamic: the frozen build ships GI next to the matching
        # GStreamer runtime, rather than PyInstaller's unrelated GI auto-hook.
        gi = importlib.import_module("gi")

        gi.require_version("Gst", "1.0")
        gi.require_version("GstVideo", "1.0")
        Gst = importlib.import_module("gi.repository.Gst")
        GstVideo = importlib.import_module("gi.repository.GstVideo")
    except (ImportError, OSError, ValueError) as error:
        logger().warning("strict sync GStreamer runtime could not load: %s", error)
        raise PlaybackError(
            f"strict timestamp sync runtime is unavailable: {error}") from error
    Gst.init(None)
    return Gst, GstVideo


class GStreamerSyncPlayer:
    """An H.264 RTSP tile whose RTP timestamps are scheduled against NTP time."""

    def __init__(self, gst: Any, gst_video: Any, clock: Any) -> None:
        self._gst = gst
        self._gst_video = gst_video
        self._clock = clock
        self._pipeline: Any | None = None
        self._sink: Any | None = None
        self._bus: Any | None = None
        self._error = ""

    def play(self, url: str, _options: Sequence[str], window_id: int) -> None:
        if not url.lower().startswith("rtsp://"):
            raise PlaybackError("strict timestamp sync supports RTSP cameras only")
        gst = self._gst
        pipeline = gst.Pipeline.new(None)
        # Register it before configuring elements. If any subsequent step fails, the
        # wall's normal failed-player cleanup can still transition it to NULL.
        self._pipeline = pipeline
        source = self._element("rtspsrc")
        depay = self._element("rtph264depay")
        parser = self._element("h264parse")
        decoder = self._element("decodebin")
        convert = self._element("videoconvert")
        sink = self._element("d3d11videosink")
        for element in (source, depay, parser, decoder, convert, sink):
            pipeline.add(element)
        source.set_property("location", url)
        source.set_property("ntp-sync", True)
        source.set_property("buffer-mode", 4)  # GstRTSPSrcBufferMode.synced
        source.set_property("latency", _NTP_SYNC_BUFFER_MS)
        source.set_property("drop-on-latency", False)
        source.set_property("do-rtcp", True)
        source.set_property("protocols", 4)  # GstRTSPLowerTrans.TCP
        self._sink = sink
        sink.set_property("sync", True)
        sink.set_property("ts-offset", _PRESENTATION_DELAY_NS)
        if not depay.link(parser) or not parser.link(decoder) or not convert.link(sink):
            raise PlaybackError("GStreamer could not link the strict sync pipeline")
        # Joining mid-GOP would decode P-frames without their reference: solid green
        # until the next keyframe. Drop them and ask the camera for a keyframe instead.
        depay.set_property("wait-for-keyframe", True)
        depay.set_property("request-keyframe", True)
        source.connect("pad-added", self._link_first_pad, depay.get_static_pad("sink"))
        decoder.connect("pad-added", self._link_first_pad, convert.get_static_pad("sink"))
        try:
            self._gst_video.VideoOverlay.set_window_handle(sink, window_id)
        except (AttributeError, TypeError, RuntimeError) as error:
            raise PlaybackError("GStreamer D3D11 sink cannot embed into the video tile") from error
        # Every tile uses the very same system clock. Fast sources wait in the common
        # presentation offset; slower ones naturally spend that time in transit.
        pipeline.use_clock(self._clock)
        self._bus = pipeline.get_bus()
        pipeline.set_state(gst.State.PLAYING)

    def state(self) -> PlaybackState:
        if self._pipeline is None:
            return PlaybackState.IDLE
        message = self._bus.pop_filtered(self._gst.MessageType.ERROR | self._gst.MessageType.EOS)
        if message is not None:
            if message.type == self._gst.MessageType.ERROR:
                error, debug = message.parse_error()
                self._error = str(error)
                detail = _safe_debug_detail(debug)
                logger().warning("strict sync GStreamer error: %s%s", self._error,
                                 f"; detail={detail}" if detail else "")
                return PlaybackState.ERROR
            return PlaybackState.ENDED
        _change, current, _pending = self._pipeline.get_state(0)
        if current == self._gst.State.PLAYING:
            # A live pipeline is PLAYING long before its first frame clears the shared delay.
            if self._sink is None or self._sink.get_property("last-sample") is None:
                return PlaybackState.OPENING
            return PlaybackState.PLAYING
        if current in (self._gst.State.PAUSED, self._gst.State.READY):
            return PlaybackState.OPENING
        return PlaybackState.IDLE

    def release(self) -> None:
        if self._pipeline is not None:
            self._pipeline.set_state(self._gst.State.NULL)
        self._bus = None
        self._sink = None
        self._pipeline = None

    def _element(self, name: str) -> Any:
        element = self._gst.ElementFactory.make(name, None)
        if element is None:
            raise PlaybackError(f"GStreamer component unavailable: {name}")
        return element

    @staticmethod
    def _link_first_pad(_source: Any, pad: Any, target: Any) -> None:
        if not target.is_linked():
            pad.link(target)


class GStreamerSyncPlayerFactory:
    """Factory for a site wall; all its players share a single GStreamer clock."""

    synchronized = True

    def __init__(self) -> None:
        self._gst, self._gst_video = _load_gst()
        self._clock = self._gst.SystemClock.obtain()
        logger().info("strict timestamp sync runtime initialized; shared system clock acquired")

    def create(self) -> GStreamerSyncPlayer:
        return GStreamerSyncPlayer(self._gst, self._gst_video, self._clock)

    def missing_elements(self) -> tuple[str, ...]:
        """Required pipeline components, including at least one H.264 decoder."""
        missing = [name for name in REQUIRED_ELEMENTS
                   if self._gst.ElementFactory.find(name) is None]
        if not any(self._gst.ElementFactory.find(name) is not None
                   for name in H264_DECODER_ELEMENTS):
            missing.append("H.264 decoder (d3d11h264dec or avdec_h264)")
        return tuple(missing)

    def shutdown(self) -> None:
        self._clock = None


def _safe_debug_detail(detail: str | None) -> str:
    """Keep useful GStreamer diagnostics without persisting RTSP credentials."""
    return redact(str(detail)).strip() if detail else ""
