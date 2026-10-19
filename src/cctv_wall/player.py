"""The only module that imports libvlc.

The wall talks to the Player / PlayerFactory protocols, so the GUI can be built
and tested on a machine without VLC (NullPlayerFactory), and swapping in another
backend later would not touch a single line of UI code.

One libvlc Instance is shared by every tile: each Instance costs memory and a
plugin scan, which matters on the weak PCs this app targets.
"""
from __future__ import annotations

import sys
from enum import Enum
from typing import Protocol, Sequence

from cctv_wall.performance import PerformanceProfile


class PlaybackError(RuntimeError):
    """A stream could not be started, with a reason fit to show inside a tile."""


class PlaybackState(str, Enum):
    """What a player is actually doing, independent of any backend's own enum.

    play() returning success only means libvlc accepted the URL. A camera that
    answers and then sends nothing lands in ENDED, which is the case that used to
    be reported as a healthy tile.
    """

    IDLE = "idle"
    OPENING = "opening"
    PLAYING = "playing"
    ENDED = "ended"
    ERROR = "error"


# libvlc state name -> our state. Keyed by name so this module never imports vlc.
_VLC_STATE_NAMES: dict[str, PlaybackState] = {
    "NothingSpecial": PlaybackState.IDLE,
    "Opening": PlaybackState.OPENING,
    "Buffering": PlaybackState.OPENING,
    "Playing": PlaybackState.PLAYING,
    "Paused": PlaybackState.PLAYING,
    "Stopped": PlaybackState.IDLE,
    "Ended": PlaybackState.ENDED,
    "Error": PlaybackState.ERROR,
}


class Player(Protocol):
    """One video surface bound to one window."""

    def play(self, url: str, options: Sequence[str], window_id: int) -> None: ...

    def state(self) -> PlaybackState: ...

    def release(self) -> None: ...


class PlayerFactory(Protocol):
    """Creates players and owns whatever they share."""

    def create(self) -> Player: ...

    def shutdown(self) -> None: ...


class VlcPlayer:
    """Wraps one libvlc media player and hides the platform-specific embedding."""

    def __init__(self, instance) -> None:
        self._instance = instance
        self._player = instance.media_player_new()
        self._released = False

    def play(self, url: str, options: Sequence[str], window_id: int) -> None:
        media = self._instance.media_new(url)
        for option in options:
            media.add_option(option)
        self._player.set_media(media)
        self._embed(window_id)
        self._disable_embedded_input()
        if self._player.play() == -1:
            raise PlaybackError("libvlc refused to start this stream")

    def state(self) -> PlaybackState:
        name = str(self._player.get_state()).rsplit(".", 1)[-1]
        return _VLC_STATE_NAMES.get(name, PlaybackState.IDLE)

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
    """Owns the shared libvlc Instance configured by a performance profile."""

    def __init__(self, profile: PerformanceProfile) -> None:
        import vlc  # imported here so the app can start without VLC and explain why

        self._instance = vlc.Instance(*profile.instance_args)
        if self._instance is None:
            raise PlaybackError("libvlc rejected the performance options")

    def create(self) -> Player:
        return VlcPlayer(self._instance)

    def shutdown(self) -> None:
        self._instance.release()


class NullPlayer:
    """Records what it was asked to do. Used by the tests and by --dry-run."""

    def __init__(self, state: PlaybackState = PlaybackState.PLAYING) -> None:
        self.calls: list[tuple[str, tuple[str, ...], int]] = []
        self.released = False
        self.reported_state = state

    def play(self, url: str, options: Sequence[str], window_id: int) -> None:
        self.calls.append((url, tuple(options), window_id))

    def state(self) -> PlaybackState:
        return self.reported_state

    def release(self) -> None:
        self.released = True


class NullPlayerFactory:
    """A PlayerFactory that needs no VLC at all."""

    def __init__(self, state: PlaybackState = PlaybackState.PLAYING) -> None:
        self.players: list[NullPlayer] = []
        self._state = state

    def create(self) -> Player:
        player = NullPlayer(self._state)
        self.players.append(player)
        return player

    def shutdown(self) -> None:
        pass
