"""The libvlc playback backend and the protocols every backend implements.

The wall talks to the Player / PlayerFactory protocols, so the GUI can be built
and tested on a machine without VLC (NullPlayerFactory), and the strict-sync
backend (gst_sync) slots in without touching UI code.

One libvlc Instance is shared by every tile: each Instance costs memory and a
plugin scan, which matters on the weak PCs this app targets.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from cctv_wall.performance import INSTANCE_ARGS, media_options_for


class PlaybackError(RuntimeError):
    """A stream could not be started, with a reason fit to show inside a tile."""


class PlaybackState(str, Enum):
    """What a player is actually doing, independent of any backend's own enum.

    play() returning success only means the backend accepted the URL; a camera that
    answers and then sends nothing lands in ENDED, not PLAYING.
    """

    IDLE = "idle"
    OPENING = "opening"
    PLAYING = "playing"
    ENDED = "ended"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class PlaybackStats:
    """Counters since the stream started; a rate is the difference between two samples."""

    width: int
    height: int
    displayed_frames: int
    lost_frames: int        # decoded but dropped because they were already late
    input_kbps: int


# libvlc state name -> our state. Keyed by name so this module never imports vlc.
_VLC_STATE_NAMES: dict[str, PlaybackState] = {
    "NothingSpecial": PlaybackState.IDLE,
    "Opening": PlaybackState.OPENING,
    "Buffering": PlaybackState.OPENING,
    "Playing": PlaybackState.PLAYING,
    "Paused": PlaybackState.PLAYING,   # a live RTSP pause is transient, not an outage
    "Stopped": PlaybackState.IDLE,
    "Ended": PlaybackState.ENDED,
    "Error": PlaybackState.ERROR,
}


# libvlc marquee positions: 1 left, 2 right, 4 top, 8 bottom, added together.
_MARQUEE_CORNERS = {"top_left": 5, "top_right": 6, "bottom_left": 9, "bottom_right": 10}


class Player(Protocol):
    """One video surface bound to one window."""

    def play(self, url: str, window_id: int) -> None: ...

    def state(self) -> PlaybackState: ...

    def stats(self) -> PlaybackStats | None:
        """None when the backend cannot report them."""

    def show_overlay(self, text: str | None, corner: str = "bottom_right") -> None:
        """Draw text in a corner of the picture itself (models.STATS_CORNERS), or remove it with None."""

    def frame_lag(self) -> float | None:
        """Seconds the picture on screen trails its capture time by the camera's own clock;
        None when the backend cannot tell."""

    def release(self) -> None: ...


class PlayerFactory(Protocol):
    """Creates players and owns whatever they share."""

    # True when every player runs on one shared clock: tiles cannot be started apart or
    # reconnected one at a time without the whole page losing sync.
    synchronized: bool

    def create(self) -> Player: ...

    def shutdown(self) -> None: ...


class VlcPlayer:
    """Wraps one libvlc media player and hides the platform-specific embedding."""

    def __init__(self, instance) -> None:
        self._instance = instance
        self._player = instance.media_player_new()
        self._media = None
        self._released = False

    def play(self, url: str, window_id: int) -> None:
        media = self._media = self._instance.media_new(url)
        for option in media_options_for(url):
            media.add_option(option)
        self._player.set_media(media)
        self._embed(window_id)
        self._disable_embedded_input()
        if self._player.play() == -1:
            raise PlaybackError("libvlc refused to start this stream")

    def state(self) -> PlaybackState:
        name = str(self._player.get_state()).rsplit(".", 1)[-1]
        return _VLC_STATE_NAMES.get(name, PlaybackState.IDLE)

    def stats(self) -> PlaybackStats | None:
        import vlc

        counters = vlc.MediaStats()
        if self._media is None or not self._media.get_stats(counters):
            return None
        width, height = self._video_size()
        # input_bitrate is in bytes per millisecond.
        return PlaybackStats(width, height, counters.displayed_pictures, counters.lost_pictures,
                             round(counters.input_bitrate * 8000))

    def show_overlay(self, text: str | None, corner: str = "bottom_right") -> None:
        """libvlc's marquee draws inside the video, which a Qt widget cannot: the native video
        window paints over its siblings. That is also why it cannot be dragged: the picture
        never sees the mouse, so it is placed in one of the corners instead."""
        import vlc

        option = vlc.VideoMarqueeOption
        if text is None:
            self._player.video_set_marquee_int(option.Enable, 0)
            return
        _width, height = self._video_size()
        self._player.video_set_marquee_int(option.Enable, 1)
        self._player.video_set_marquee_int(option.Position, _MARQUEE_CORNERS.get(corner, 10))
        # The size is in video pixels: about the same share of the tile at any resolution.
        self._player.video_set_marquee_int(option.Size, max(14, height // 24))
        self._player.video_set_marquee_int(option.Timeout, 0)
        self._player.video_set_marquee_string(option.Text, text)

    def _video_size(self) -> tuple[int, int]:
        import vlc

        try:
            return self._player.video_get_size(0)
        except vlc.VLCException:
            return 0, 0   # no video track yet

    def frame_lag(self) -> None:
        return None   # libvlc does not expose a frame's capture (RTCP/NTP) time

    def release(self) -> None:
        """Tear down without blocking the Qt event loop on an unhealthy RTSP connection.

        ``media_player.stop()`` is synchronous in libVLC 3 and can wait indefinitely for
        a network decoder. Newer libVLC versions offer ``stop_async``; otherwise releasing
        the player is the bounded operation and still drops the media, socket, and decoder.
        """
        if self._released:
            return
        self._released = True
        stop_async = getattr(self._player, "stop_async", None)
        if callable(stop_async):
            try:
                stop_async()
            except OSError:
                pass
        self._player.release()

    def _embed(self, window_id: int) -> None:
        if sys.platform == "win32":
            self._player.set_hwnd(window_id)
        elif sys.platform == "darwin":
            self._player.set_nsobject(window_id)
        else:
            self._player.set_xwindow(window_id)

    def _disable_embedded_input(self) -> None:
        """Keep double-click and right-click under Qt rather than VLC's native surface."""
        for method_name in ("video_set_mouse_input", "video_set_key_input"):
            method = getattr(self._player, method_name, None)
            if callable(method):
                try:
                    method(False)
                except OSError:
                    pass


class VlcPlayerFactory:
    """Owns the shared libvlc Instance configured with the wall's tuning."""

    synchronized = False

    def __init__(self) -> None:
        import vlc  # imported here so the app can start without VLC and explain why

        self._instance = vlc.Instance(*INSTANCE_ARGS)
        if self._instance is None:
            raise PlaybackError("libvlc rejected the tuning options")

    def create(self) -> Player:
        return VlcPlayer(self._instance)

    def shutdown(self) -> None:
        # libvlc reference-counts the Instance: players still being released on the wall's
        # background thread keep it alive until they are done.
        self._instance.release()


class NullPlayer:
    """Records what it was asked to do. Used by the tests and by --dry-run."""

    def __init__(self, state: PlaybackState = PlaybackState.PLAYING) -> None:
        self.calls: list[tuple[str, int]] = []
        self.released = False
        self.reported_state = state
        self.overlay: str | None = None
        self.lag: float | None = None

    def play(self, url: str, window_id: int) -> None:
        self.calls.append((url, window_id))

    def state(self) -> PlaybackState:
        return self.reported_state

    def stats(self) -> PlaybackStats | None:
        return PlaybackStats(1920, 1080, 15 * len(self.calls), 0, 2048)

    def show_overlay(self, text: str | None, corner: str = "bottom_right") -> None:
        self.overlay = text
        self.overlay_corner = corner

    def frame_lag(self) -> float | None:
        return self.lag

    def release(self) -> None:
        self.released = True


class NullPlayerFactory:
    """A PlayerFactory that needs no VLC at all."""

    synchronized = False

    def __init__(self, state: PlaybackState = PlaybackState.PLAYING) -> None:
        self.players: list[NullPlayer] = []
        self._state = state

    def create(self) -> Player:
        player = NullPlayer(self._state)
        self.players.append(player)
        return player

    def shutdown(self) -> None:
        pass
