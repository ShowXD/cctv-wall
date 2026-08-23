"""Video wall widgets.  The wall owns only visible players; presentation stays local."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Thread
from typing import Callable, Sequence

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QMenu, QVBoxLayout, QWidget

from cctv_wall import layout
from cctv_wall.event_log import logger
from cctv_wall.i18n import Translator
from cctv_wall.models import MAX_STREAM, MIN_STREAM, Camera
from cctv_wall.performance import PerformanceProfile, media_options_for
from cctv_wall.player import PlaybackError, PlaybackState, Player, PlayerFactory
from cctv_wall.resolvers import ResolveError, StreamResolver
from cctv_wall.urls import build_url, redact, stream_from_direct_url

# Starting four RTSP sessions in the same event-loop turn can overwhelm a weak PC or a
# camera/NVR with a small connection budget. Stagger starts but keep navigation instant.
FIRST_AUDIT_MS = 9000
AUDIT_INTERVAL_MS = 5000
PLAYBACK_CONFIRMATION_INTERVAL_MS = 250
STATE_EXPLANATION_KEYS = {
    PlaybackState.OPENING: "connection_waiting",
    PlaybackState.ENDED: "no_video",
    PlaybackState.ERROR: "vlc_error",
    PlaybackState.IDLE: "not_playing",
}
# 這些狀態代表這一格已經沒有影像，值得重連。OPENING 不算故障：低階電腦協商本來就慢，
# 把它當成掉線會不斷打斷一個其實正在連線成功的來源。
DEAD_STATES = frozenset({PlaybackState.ERROR, PlaybackState.ENDED, PlaybackState.IDLE})
# 退避以「稽核次數」為單位，因此不需要額外計時器；一次等於 AUDIT_INTERVAL_MS。
# 1→2→4→6 次 ×5 秒＝延遲 5→10→20→30 秒，上限 30 秒，避免壞掉的來源被反覆猛打。
MAX_RECONNECT_BACKOFF_TICKS = 6


def _connection_start_interval(factory: PlayerFactory, profile: PerformanceProfile) -> int:
    """Space normal RTSP connections without delaying the shared-clock backend."""
    if getattr(factory, "synchronized", False):
        return 0
    if profile.tiles_per_page <= 4:
        return 650
    if profile.tiles_per_page <= 9:
        return 350
    return 175


class VideoSurface(QWidget):
    """The native VLC target that forwards operator gestures to the Qt card."""

    def __init__(self, on_solo: Callable[[], None], on_menu: Callable[[QContextMenuEvent], None]) -> None:
        super().__init__()
        self._on_solo = on_solo
        self._on_menu = on_menu
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_solo()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self._on_menu(event)


class VideoTile(QFrame):
    """A video-first camera card; metadata stays in a tooltip unless an error needs attention."""

    def __init__(self, camera: Camera, translator: Translator,
                 on_solo: Callable[[Camera], None] | None,
                 on_stream_change: Callable[[Camera, int], None] | None) -> None:
        super().__init__()
        self.camera = camera
        self._translator = translator
        self._on_solo = on_solo
        self._on_stream_change = on_stream_change
        self.setObjectName("videoTile")
        self.setMinimumSize(180, 120)
        self.surface = VideoSurface(self._open_solo, self._show_stream_menu)
        self.surface.setObjectName("videoSurface")
        card = QVBoxLayout(self)
        card.setContentsMargins(1, 1, 1, 1)
        card.addWidget(self.surface, 1)
        self._notice = QLabel()
        self._notice.setObjectName("tileNotice")
        self._notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notice.setWordWrap(True)
        self._notice.hide()
        card.addWidget(self._notice)
        self._set_tooltip()


    def show_notice(self, message: str, level: str) -> None:
        self._set_tooltip()
        # Transient buffering is normal for CCTV streams.  Only show a panel when an
        # operator needs to act, otherwise preserve every pixel for video.
        if level != "error":
            self._notice.hide()
            return
        self._notice.setText(message)
        self._notice.setProperty("level", level)
        self._refresh_style(self._notice)
        self._notice.show()

    def set_playing(self) -> None:
        self._set_tooltip()
        self._notice.hide()

    def _set_tooltip(self) -> None:
        # The image itself is the primary UI. Hover should identify the source only;
        # connection state and gesture hints add noise while inspecting a live scene.
        self.setToolTip(self.camera.label)

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _open_solo(self) -> None:
        if self._on_solo is not None:
            self._on_solo(self.camera)

    def _show_stream_menu(self, event: QContextMenuEvent) -> None:
        menu = QMenu(self)
        menu.setTitle(self.camera.label)
        direct_stream = stream_from_direct_url(self.camera.url) if self.camera.url else None
        current_stream = direct_stream or self.camera.stream
        can_switch = (not self.camera.url or direct_stream is not None) and self._on_stream_change is not None
        for stream in range(MIN_STREAM, MAX_STREAM + 1):
            action = QAction(self._translator.t("stream_choice", stream=stream), menu)
            action.setCheckable(True)
            action.setChecked(stream == current_stream)
            action.setEnabled(can_switch)
            action.triggered.connect(lambda _checked=False, value=stream: self._choose_stream(value))
            menu.addAction(action)
        menu.exec(event.globalPos())

    def _choose_stream(self, stream: int) -> None:
        if self._on_stream_change is not None and stream != self.camera.stream:
            self._on_stream_change(self.camera, stream)


@dataclass(slots=True)
class _Tile:
    view: VideoTile
    log_label: str
    player: Player | None = None
    last_logged_state: PlaybackState | None = None
    backoff_ticks: int = 1        # 下次重連要等幾次稽核
    ticks_until_retry: int = 0    # 還要等幾次稽核

    def reset_backoff(self) -> None:
        """影像恢復後把退避歸零，下一次掉線才會立刻重連。"""
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
        tile.view.deleteLater()


def _due_for_retry(tile: _Tile) -> bool:
    """這次稽核該不該重連。不碰 Qt，所以退避節奏可以單獨測試。"""
    if tile.ticks_until_retry > 0:
        tile.ticks_until_retry -= 1
        return False
    tile.ticks_until_retry = tile.backoff_ticks
    tile.backoff_ticks = min(tile.backoff_ticks * 2, MAX_RECONNECT_BACKOFF_TICKS)
    return True


class WallView(QWidget):
    """Renders one page, preserving the low-memory one-player-per-visible-tile rule."""

    def __init__(self, factory: PlayerFactory, resolver: StreamResolver,
                 profile: PerformanceProfile, on_solo: Callable[[Camera], None] | None = None,
                 on_health_change: Callable[[], None] | None = None,
                 translator: Translator | None = None,
                 on_stream_change: Callable[[Camera, int], None] | None = None) -> None:
        super().__init__()
        self._factory = factory
        self._resolver = resolver
        self._profile = profile
        self._start_interval_ms = _connection_start_interval(factory, profile)
        self._on_solo = on_solo
        self._on_health_change = on_health_change
        self._translator = translator or Translator()
        self._on_stream_change = on_stream_change
        self._tiles: list[_Tile] = []
        self._focused_tile: _Tile | None = None
        self._muted = False
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

    def set_immersive(self, enabled: bool) -> None:
        """Trade decorative card gaps for image area while the wall fills its window."""
        if enabled:
            self._grid.setContentsMargins(0, 0, 0, 0)
        else:
            self._grid.setContentsMargins(6, 0, 6, 6)
        self._grid.setSpacing(2 if enabled else 6)

    @property
    def tiles_per_page(self) -> int:
        return self._profile.tiles_per_page

    def set_factory(self, factory: PlayerFactory) -> None:
        """Swap backend only while stopped; used when strict sync is enabled or disabled."""
        if self._tiles:
            raise RuntimeError("cannot replace playback backend while tiles are active")
        self._factory = factory
        self._start_interval_ms = _connection_start_interval(factory, self._profile)

    def page_count(self, camera_count: int) -> int:
        return layout.page_count(camera_count, self.tiles_per_page)

    @property
    def playing_count(self) -> int:
        displayed = (self._focused_tile,) if self._focused_tile is not None else self._tiles
        return sum(tile.player is not None and tile.player.state() == PlaybackState.PLAYING
                   for tile in displayed)

    @property
    def allocated_player_count(self) -> int:
        """Players already created for the visible page; queued tiles are not connected yet."""
        return sum(tile.player is not None for tile in self._tiles)

    def show_page(self, cameras: Sequence[Camera], page: int = 0) -> int:
        self.stop()
        self._clear_widgets()
        visible = cameras[layout.page_slice(page, self.tiles_per_page)]
        if not visible:
            self._show_hint(self._translator.t("no_cameras"), self._translator.t("add_camera_hint"))
            return 0
        _rows, columns = layout.grid_shape(len(visible))
        for index, camera in enumerate(visible):
            # A direct RTSP URL may contain credentials. It remains useful as a visual
            # fallback label in the navigation tree, but must never escape into logs.
            log_label = camera.name or f"Camera {index + 1}"
            tile = _Tile(VideoTile(camera, self._translator, self._on_solo,
                                   self._on_stream_change), log_label)
            self._tiles.append(tile)
            self._grid.addWidget(tile.view, index // columns, index % columns)
            tile.view.surface.winId()
        self._pending_starts = list(self._tiles)
        self._start_next()
        self._playback_timer.start(PLAYBACK_CONFIRMATION_INTERVAL_MS)
        # Delay the first health warning until every staggered connection has had time to
        # negotiate. This avoids misleading "offline" reports on slower PCs.
        self._audit_timer.start(FIRST_AUDIT_MS + self._start_interval_ms * len(visible))
        return self.allocated_player_count

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

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        for tile in self._tiles:
            if tile.player is not None:
                tile.player.set_muted(muted)

    def stop(self) -> None:
        """Cancel queued starts before releasing visible players during page/site changes."""
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
        """釋放一格的播放器；原生解碼器收尾失敗不能連帶影響其他格。"""
        if tile.player is None:
            return
        try:
            tile.player.release()
        except Exception as error:
            logger().warning("camera=%s release failed: %s", tile.log_label, error)
        tile.player = None
        tile.last_logged_state = None

    def _advance_reconnect(self, tile: _Tile) -> None:
        """依退避節奏重連掉線的攝影機，讓長期監看不需要人工按重新連線。"""
        if not _due_for_retry(tile):
            return
        logger().info("camera=%s reconnecting", tile.log_label)
        self._release(tile)
        self._start(tile)

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
                continue  # 還沒輪到它連線，不是故障
            if tile.player is None:
                # 一開始就連不上的攝影機：保留原本的錯誤訊息，只安排重試。
                self._advance_reconnect(tile)
                continue
            state = tile.player.state()
            self._log_state_change(tile, state)
            if state == PlaybackState.PLAYING:
                tile.reset_backoff()
                tile.view.set_playing()
                continue
            explanation = STATE_EXPLANATION_KEYS.get(state, "not_playing")
            tile.view.show_notice(self._translator.t(explanation), "warning")
            if state in DEAD_STATES:
                self._advance_reconnect(tile)
        if self._on_health_change is not None:
            self._on_health_change()
        if self._tiles:
            self._audit_timer.start(AUDIT_INTERVAL_MS)

    def _confirm_playback(self) -> None:
        """Update the unobtrusive live indicator without triggering early error warnings."""
        confirmed = False
        still_opening = bool(self._pending_starts)
        for tile in self._tiles:
            if tile.player is None:
                continue
            state = tile.player.state()
            self._log_state_change(tile, state)
            if state == PlaybackState.PLAYING:
                tile.view.set_playing()
                confirmed = True
            elif state == PlaybackState.OPENING:
                still_opening = True
        if confirmed and self._on_health_change is not None:
            self._on_health_change()
        if not still_opening:
            self._playback_timer.stop()

    def _start(self, tile: _Tile) -> None:
        player: Player | None = None
        try:
            camera = tile.view.camera
            logger().info("connecting camera=%s", tile.log_label)
            url = self._resolver.resolve(build_url(camera), camera.quality)
            player = self._factory.create()
            player.play(url, media_options_for(url, camera.quality, self._profile),
                        int(tile.view.surface.winId()))
            player.set_muted(self._muted)
            tile.player = player
            state = player.state()
            self._log_state_change(tile, state)
            if state == PlaybackState.PLAYING:
                tile.view.set_playing()
        except (ResolveError, PlaybackError, ValueError, OSError) as error:
            if player is not None:
                try:
                    player.release()
                except Exception as release_error:  # Preserve the useful connection error.
                    logger().warning("camera=%s failed-player release: %s", tile.log_label, release_error)
            reason = redact(str(error))
            logger().warning("camera=%s: %s", tile.log_label, reason)
            tile.view.show_notice(reason, "error")

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
