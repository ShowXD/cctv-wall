"""Video wall widgets.  The wall owns only visible players; presentation stays local."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Thread
from typing import Callable, Sequence

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QMenu, QSizePolicy, QVBoxLayout, QWidget

from cctv_wall import layout
from cctv_wall.event_log import logger
from cctv_wall.i18n import Translator
from cctv_wall.models import MAX_STREAM, MIN_STREAM, Camera
from cctv_wall.player import PlaybackError, PlaybackState, Player, PlayerFactory
from cctv_wall.urls import build_url, redact, stream_from_direct_url

FIRST_AUDIT_MS = 9000
AUDIT_INTERVAL_MS = 5000
PLAYBACK_CONFIRMATION_INTERVAL_MS = 250
# The quick check only covers the first connections; past this the 5 s audit takes over, so a
# camera stuck connecting does not keep a 250 ms timer running for the whole session.
PLAYBACK_CONFIRMATION_TICKS = 120
AI_FLASH_MS = 1000
STATE_EXPLANATION_KEYS = {
    PlaybackState.OPENING: "connection_waiting",
    PlaybackState.ENDED: "no_video",
    PlaybackState.ERROR: "vlc_error",
    PlaybackState.IDLE: "not_playing",
}
# States in which a tile has no picture and is worth reconnecting. OPENING is not one: a weak
# PC negotiates slowly, and treating that as an outage would keep interrupting a connection
# that is about to succeed.
DEAD_STATES = frozenset({PlaybackState.ERROR, PlaybackState.ENDED, PlaybackState.IDLE})
# Backoff counts audits, so it needs no timer of its own: 1, 2, 4, 6 audits of 5 s is a
# 5, 10, 20, 30 s wait, capped so a broken source is not hammered.
MAX_RECONNECT_BACKOFF_TICKS = 6


def _connection_start_interval(factory: PlayerFactory, tiles_per_page: int) -> int:
    """Gap between starting two tiles' connections.

    Starting every RTSP session in the same event-loop turn can overwhelm a weak PC or a
    camera/NVR with a small connection budget. The shared-clock backend starts them together.
    """
    if factory.synchronized:
        return 0
    if tiles_per_page <= 4:
        return 650
    if tiles_per_page <= 9:
        return 350
    return 175


class _AiLine(QLabel):
    """One result line under a tile. Each result lights it in its camera's colour for a moment,
    since consecutive results often differ only by a second. A plain switch, not a fade: remote
    desktop drops the in-between frames of a fade, and a one-second hold survives a slow refresh."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("tileAi")
        # A long result must not widen the tile: that re-lays out the grid and resizes the
        # native video windows beside it. The tooltip keeps the full text.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._colour = ""
        self._flash = QTimer(self)
        self._flash.setSingleShot(True)
        self._flash.setInterval(AI_FLASH_MS)
        self._flash.timeout.connect(self._settle)

    def show_result(self, text: str, colour: str) -> None:
        # Restyling re-parses the application style sheet; a line that is already lit in this
        # colour only needs its timer restarted.
        if not (self._flash.isActive() and colour == self._colour):
            self._colour = colour
            self.setStyleSheet(f"border-left: 4px solid {colour}; background: {colour}; color: #0b0f14;")
        self._flash.start()
        self.setText(text)
        self.setToolTip(text)

    def _settle(self) -> None:
        self.setStyleSheet(f"border-left: 4px solid {self._colour};")


class VideoSurface(QWidget):
    """The native VLC target that forwards operator gestures to the Qt card."""

    def __init__(self, on_focus: Callable[[], None], on_menu: Callable[[QContextMenuEvent], None]) -> None:
        super().__init__()
        self._on_focus = on_focus
        self._on_menu = on_menu
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_focus()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self._on_menu(event)


class VideoTile(QFrame):
    """A video-first camera card; metadata stays in a tooltip unless an error needs attention."""

    def __init__(self, camera: Camera, translator: Translator,
                 on_focus: Callable[[Camera], None],
                 on_stream_change: Callable[[Camera, int], None],
                 on_retry: Callable[[Camera], None]) -> None:
        super().__init__()
        self.camera = camera
        self._translator = translator
        self._on_focus = on_focus
        self._on_stream_change = on_stream_change
        self._on_retry = on_retry
        self.setObjectName("videoTile")
        self.setMinimumSize(180, 120)
        self.surface = VideoSurface(lambda: self._on_focus(self.camera), self._show_stream_menu)
        self.surface.setObjectName("videoSurface")
        card = QVBoxLayout(self)
        card.setContentsMargins(1, 1, 1, 1)
        card.addWidget(self.surface, 1)
        # A native video surface paints over Qt siblings, so text lives in its own strip.
        # One line per kind of result the connection keeps (or a single line), in its order.
        self._ai_box = QVBoxLayout()
        self._ai_box.setSpacing(0)
        card.addLayout(self._ai_box)
        self._ai_lines: dict[int, _AiLine] = {}
        self._notice = QLabel()
        self._notice.setObjectName("tileNotice")
        self._notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notice.setWordWrap(True)
        self._notice.setCursor(Qt.CursorShape.PointingHandCursor)
        self._notice.hide()
        card.addWidget(self._notice)
        self.setToolTip(camera.label)   # the picture is the UI; hover only names the source


    def show_notice(self, message: str, level: str) -> None:
        # Buffering is normal for CCTV, so it gets no strip: only errors and the strict-sync
        # wait take pixels from the video.
        if level not in ("error", "sync"):
            self._notice.hide()
            return
        # The audit repeats the same notice every 5 s; restyling it each time is wasted work.
        if (self._notice.isVisible() and self._notice.text() == message
                and self._notice.property("level") == level):
            return
        self._notice.setText(message)
        self._notice.setProperty("level", level)
        self._refresh_style(self._notice)
        self._notice.show()

    def set_playing(self) -> None:
        self._notice.hide()

    def set_camera(self, camera: Camera) -> None:
        """Show an edited camera in this card; a renamed camera's old AI result no longer applies."""
        if camera.label != self.camera.label:
            for line in self._ai_lines.values():
                line.deleteLater()
            self._ai_lines.clear()
        self.camera = camera
        self.setToolTip(camera.label)

    def show_ai_event(self, text: str, colour: str, line: int = 0) -> None:
        """Latest AI result of one kind for this camera; the full history lives in the side
        panel, where this camera's rows carry the same colour as the lines' left edge."""
        ai_line = self._ai_lines.get(line)
        if ai_line is None:
            ai_line = self._ai_lines[line] = _AiLine()
            self._ai_box.insertWidget(sorted(self._ai_lines).index(line), ai_line)
        ai_line.show_result(text, colour)

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        position = event.position().toPoint()
        if self._notice.isVisible() and self._notice.geometry().contains(position):
            self._on_retry(self.camera)
            event.accept()
            return
        super().mousePressEvent(event)

    def _show_stream_menu(self, event: QContextMenuEvent) -> None:
        menu = QMenu(self.window())   # see SiteNavigation._show_context_menu
        menu.setTitle(self.camera.label)
        # Only a URL that names its stream (".../stream2", "?stream=2") can be switched;
        # guessing a vendor's URL format would break the camera instead.
        current_stream = stream_from_direct_url(self.camera.url)
        can_switch = current_stream is not None
        for stream in range(MIN_STREAM, MAX_STREAM + 1):
            action = QAction(self._translator.t("stream_choice", stream=stream), menu)
            action.setCheckable(True)
            action.setChecked(stream == current_stream)
            action.setEnabled(can_switch)
            action.triggered.connect(lambda _checked=False, value=stream: self._choose_stream(value))
            menu.addAction(action)
        menu.exec(event.globalPos())
        menu.deleteLater()

    def _choose_stream(self, stream: int) -> None:
        if stream != stream_from_direct_url(self.camera.url):
            self._on_stream_change(self.camera, stream)


@dataclass(slots=True)
class _Tile:
    view: VideoTile
    log_label: str                # Camera.label, which never carries credentials
    player: Player | None = None
    last_logged_state: PlaybackState | None = None
    backoff_ticks: int = 1        # audits to wait before the next reconnect
    ticks_until_retry: int = 0    # audits left in the current wait

    def reset_backoff(self) -> None:
        """Once the picture is back, the next outage reconnects at once."""
        self.backoff_ticks = 1
        self.ticks_until_retry = 0


def _release_detached(tiles: Sequence[_Tile]) -> None:
    """Release players off the Qt thread, then let their surfaces go."""
    for tile in tiles:
        try:
            tile.player.release()
        except Exception as error:
            logger().warning("camera=%s release failed: %s", tile.log_label, error)
        tile.player = None
        try:
            tile.view.deleteLater()
        except RuntimeError:
            pass   # the app quit first and Qt already destroyed the parentless surface


def _due_for_retry(tile: _Tile) -> bool:
    """Whether this audit reconnects the tile. Free of Qt so the backoff can be tested alone."""
    if tile.ticks_until_retry > 0:
        tile.ticks_until_retry -= 1
        return False
    tile.ticks_until_retry = tile.backoff_ticks
    tile.backoff_ticks = min(tile.backoff_ticks * 2, MAX_RECONNECT_BACKOFF_TICKS)
    return True


class WallView(QWidget):
    """Renders one page, preserving the low-memory one-player-per-visible-tile rule."""

    def __init__(self, factory: PlayerFactory, tiles_per_page: int, translator: Translator,
                 on_focus: Callable[[Camera], None], on_health_change: Callable[[], None],
                 on_stream_change: Callable[[Camera, int], None]) -> None:
        super().__init__()
        self._factory = factory
        self._tiles_per_page = tiles_per_page
        self._start_interval_ms = _connection_start_interval(factory, tiles_per_page)
        self._on_focus = on_focus
        self._on_health_change = on_health_change
        self._translator = translator
        self._on_stream_change = on_stream_change
        self._tiles: list[_Tile] = []
        self._focused_tile: _Tile | None = None
        self._pending_starts: list[_Tile] = []
        self._start_timer = QTimer(self)
        self._start_timer.setSingleShot(True)
        self._start_timer.timeout.connect(self._start_next)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(6, 0, 6, 6)
        self._grid.setSpacing(6)
        self._audit_timer = QTimer(self)
        self._audit_timer.timeout.connect(self.audit_now)
        self._playback_timer = QTimer(self)
        self._playback_timer.timeout.connect(self._confirm_playback)
        self._playback_ticks_left = 0
        self._reported_playing = -1

    def set_immersive(self, enabled: bool) -> None:
        """Trade decorative card gaps for image area while the wall fills its window."""
        if enabled:
            self._grid.setContentsMargins(0, 0, 0, 0)
        else:
            self._grid.setContentsMargins(6, 0, 6, 6)
        self._grid.setSpacing(2 if enabled else 6)

    @property
    def tiles_per_page(self) -> int:
        return self._tiles_per_page

    def configure(self, factory: PlayerFactory, tiles_per_page: int) -> None:
        """Swap backend and page size together, only while stopped."""
        if self._tiles:
            raise RuntimeError("cannot replace playback backend while tiles are active")
        self._factory = factory
        self._tiles_per_page = tiles_per_page
        self._start_interval_ms = _connection_start_interval(factory, tiles_per_page)

    def page_count(self, camera_count: int) -> int:
        return layout.page_count(camera_count, self.tiles_per_page)

    @property
    def playing_count(self) -> int:
        displayed = (self._focused_tile,) if self._focused_tile is not None else self._tiles
        return sum(tile.player is not None and tile.player.state() == PlaybackState.PLAYING
                   for tile in displayed)

    def video_surface_size(self) -> tuple[int, int] | None:
        """Size of one video area on the grid, or None when no tile is shown."""
        if not self._tiles or self._focused_tile is not None:
            return None
        surface = self._tiles[0].view.surface
        return surface.width(), surface.height()

    @property
    def tile_count(self) -> int:
        return len(self._tiles)

    @property
    def allocated_player_count(self) -> int:
        """Players already created for the visible page; queued tiles are not connected yet."""
        return sum(tile.player is not None for tile in self._tiles)

    def show_page(self, cameras: Sequence[Camera], page: int = 0) -> None:
        self.stop()
        self._clear_widgets()
        visible = cameras[layout.page_slice(page, self.tiles_per_page)]
        if not visible:
            self._show_hint(self._translator.t("no_cameras"), self._translator.t("add_camera_hint"))
            return
        _rows, columns = layout.grid_shape(len(visible))
        for index, camera in enumerate(visible):
            tile = _Tile(VideoTile(camera, self._translator, self._on_focus,
                                   self._on_stream_change, self._retry_camera),
                         camera.label)
            self._tiles.append(tile)
            self._grid.addWidget(tile.view, index // columns, index % columns)
            tile.view.surface.winId()   # Qt creates the native window lazily; play() needs it now
        self._pending_starts = list(self._tiles)
        self._start_next()
        self._playback_ticks_left = PLAYBACK_CONFIRMATION_TICKS
        self._reported_playing = -1
        self._playback_timer.start(PLAYBACK_CONFIRMATION_INTERVAL_MS)
        # Hold the first health warning until every staggered connection has had time to
        # negotiate, so a slow PC does not report cameras offline that are still connecting.
        self._audit_timer.start(FIRST_AUDIT_MS + self._start_interval_ms * len(visible))

    def focus_camera(self, camera: Camera) -> bool:
        """Expand an already-playing tile without touching its RTSP connection."""
        target = next((tile for tile in self._tiles if tile.view.camera == camera), None)
        if target is None:
            return False
        self._focused_tile = target
        for tile in self._tiles:
            tile.view.setVisible(tile is target)
        self._grid.addWidget(target.view, 0, 0)
        return True

    def restore_grid(self) -> None:
        """Return existing cards to their positions; players continue uninterrupted."""
        if self._focused_tile is None:
            return
        self._focused_tile = None
        _rows, columns = layout.grid_shape(len(self._tiles))
        for index, tile in enumerate(self._tiles):
            self._grid.addWidget(tile.view, index // columns, index % columns)
            tile.view.show()

    def show_ai_event(self, camera_label: str, text: str, colour: str, line: int = 0) -> None:
        """Route an AI result to the visible tile of that camera; other pages ignore it."""
        for tile in self._tiles:
            if tile.view.camera.label == camera_label:
                tile.view.show_ai_event(text, colour, line)

    def stop(self) -> None:
        """Cancel queued starts, then release the visible players."""
        self._start_timer.stop()
        self._pending_starts.clear()
        self._audit_timer.stop()
        self._playback_timer.stop()
        self._focused_tile = None
        # Native teardown can block on an unhealthy RTSP source; the surface has to
        # outlive it, so both are handed to a worker instead of stalling navigation.
        detached = [tile for tile in self._tiles if tile.player is not None]
        if detached:
            logger().info("stopping %d visible camera connection(s)", len(detached))
        for tile in detached:
            tile.view.hide()
            tile.view.setParent(None)
        self._tiles.clear()
        if detached:
            Thread(target=_release_detached, args=(detached,), daemon=True).start()

    def _release(self, tile: _Tile) -> None:
        """Release one tile's player; a native teardown failure must not affect the other tiles."""
        if tile.player is None:
            return
        try:
            tile.player.release()
        except Exception as error:
            logger().warning("camera=%s release failed: %s", tile.log_label, error)
        tile.player = None
        tile.last_logged_state = None

    def _advance_reconnect(self, tile: _Tile) -> bool:
        """Reconnect a dead tile on the backoff schedule, so long unattended watches recover alone."""
        if not _due_for_retry(tile):
            return False
        logger().info("camera=%s reconnecting", tile.log_label)
        self._release(tile)
        self._start(tile)
        return True

    def replace_camera(self, old: Camera, new: Camera) -> bool:
        """Reconnect only the tile showing `old`; the rest of the page keeps playing.

        False means the caller has to rebuild the page instead, because the strict-sync
        backend runs every tile on one shared clock. A camera not on this page needs nothing.
        """
        tile = next((t for t in self._tiles if t.view.camera == old), None)
        if tile is None:
            return True
        if self._factory.synchronized:
            return False
        tile.view.set_camera(new)
        tile.log_label = new.label
        if tile in self._pending_starts:
            return True   # not connected yet; it will start with the new settings
        tile.reset_backoff()
        logger().info("camera=%s reconnecting with new settings", tile.log_label)
        self._release(tile)
        self._start(tile)
        return True

    def _retry_camera(self, camera: Camera) -> None:
        """Operator asked for this one tile now; the backoff schedule starts over."""
        tile = next((t for t in self._tiles if t.view.camera == camera), None)
        if tile is None or tile in self._pending_starts:
            return
        tile.reset_backoff()
        logger().info("camera=%s manual reconnect", tile.log_label)
        self._release(tile)
        self._start(tile)

    def _outage_message(self, tile: _Tile, explanation_key: str, retried: bool) -> str:
        lines = [tile.log_label, self._translator.t(explanation_key)]
        if retried:
            lines.append(self._translator.t("reconnecting"))
        else:
            seconds = tile.ticks_until_retry * AUDIT_INTERVAL_MS // 1000
            lines.append(f"{self._translator.t('retry_in', seconds=seconds)}"
                         f"  ·  {self._translator.t('retry_now')}")
        return "\n".join(lines)

    def _start_next(self) -> None:
        """Start at most one connection per interval; stop() cancels the remaining queue."""
        if not self._pending_starts:
            return
        tile = self._pending_starts.pop(0)
        # A page switch may have removed the tile between timer scheduling and delivery.
        if tile in self._tiles:
            self._start(tile)
        if self._pending_starts:
            self._start_timer.start(self._start_interval_ms)

    def audit_now(self) -> None:
        for tile in tuple(self._tiles):
            if tile in self._pending_starts:
                continue  # not started yet, so not an outage
            if tile.player is None:
                # It never connected: keep the original error on screen, only schedule a retry.
                self._advance_reconnect(tile)
                continue
            state = tile.player.state()
            self._log_state_change(tile, state)
            if state == PlaybackState.PLAYING:
                tile.reset_backoff()
                tile.view.set_playing()
                continue
            explanation = STATE_EXPLANATION_KEYS.get(state, "not_playing")
            if state not in DEAD_STATES:
                self._show_opening(tile)
                continue
            retried = self._advance_reconnect(tile)
            tile.view.show_notice(self._outage_message(tile, explanation, retried), "error")
        self._on_health_change()
        if self._tiles:
            self._audit_timer.start(AUDIT_INTERVAL_MS)

    def _confirm_playback(self) -> None:
        """Clear notices as soon as tiles play, without waiting for the first audit."""
        playing = 0
        still_opening = bool(self._pending_starts)
        for tile in self._tiles:
            if tile.player is None:
                continue
            state = tile.player.state()
            self._log_state_change(tile, state)
            if state == PlaybackState.PLAYING:
                tile.view.set_playing()
                playing += 1
            elif state == PlaybackState.OPENING:
                still_opening = True
        if playing != self._reported_playing:
            self._reported_playing = playing
            self._on_health_change()
        self._playback_ticks_left -= 1
        if not still_opening or self._playback_ticks_left <= 0:
            self._playback_timer.stop()

    def _show_opening(self, tile: _Tile) -> None:
        """Strict sync holds every picture for its shared delay, so say why the tile is still empty."""
        if self._factory.synchronized:
            tile.view.show_notice(self._translator.t("syncing"), "sync")
        else:
            tile.view.show_notice(self._translator.t("connection_waiting"), "warning")

    def _start(self, tile: _Tile) -> None:
        player: Player | None = None
        try:
            camera = tile.view.camera
            logger().info("connecting camera=%s", tile.log_label)
            url = build_url(camera)
            player = self._factory.create()
            player.play(url, int(tile.view.surface.winId()))
            tile.player = player
            state = player.state()
            self._log_state_change(tile, state)
            if state == PlaybackState.PLAYING:
                tile.view.set_playing()
            else:
                self._show_opening(tile)
        except (PlaybackError, ValueError, OSError) as error:
            if player is not None:
                try:
                    player.release()
                except Exception as release_error:  # Preserve the useful connection error.
                    logger().warning("camera=%s failed-player release: %s", tile.log_label, release_error)
            reason = redact(str(error))
            logger().warning("camera=%s: %s", tile.log_label, reason)
            tile.view.show_notice(f"{tile.log_label}\n{reason}", "error")

    @staticmethod
    def _log_state_change(tile: _Tile, state: PlaybackState) -> None:
        """Emit one useful event per real player-state transition, never a five-second flood."""
        if tile.last_logged_state == state:
            return
        tile.last_logged_state = state
        logger().info("camera=%s playback=%s", tile.log_label, state.value)

    def _clear_widgets(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _show_hint(self, title: str, detail: str) -> None:
        empty = QWidget()
        empty.setObjectName("emptyWall")
        layout_box = QVBoxLayout(empty)
        layout_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(title)
        label.setObjectName("emptyWallTitle")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description = QLabel(detail)
        description.setObjectName("emptyWallDetail")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_box.addWidget(label)
        layout_box.addWidget(description)
        self._grid.addWidget(empty, 0, 0)
