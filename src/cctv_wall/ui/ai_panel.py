"""Side panel listing AI results from a site's TCP feed, timed to match the video."""
from __future__ import annotations

import time
from collections import deque
from typing import Callable, Sequence
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import QComboBox, QFrame, QLabel, QListWidget, QListWidgetItem, QVBoxLayout

from cctv_wall.ai_feed import (ALIGN_AI_TIME, ALIGN_FRAME, STATUS_CONNECTED, AiEvent, AiFeedClient, AiFeedConfig,
                               release_due)
from cctv_wall.i18n import Translator
from cctv_wall.models import Camera, Site
from cctv_wall.ui.theme import painted_icon

MAX_ROWS = 500
RELEASE_INTERVAL_MS = 200
# One colour per camera, shared by its rows here and its tile's result strip, so a row can be
# matched to a tile at a glance. Mid-tones that read on both the dark and the light theme.
CAMERA_COLOURS = ("#e5534b", "#3fb950", "#4493f8", "#d29922", "#a371f7", "#db61a2", "#39c5cf", "#f0883e")
UNKNOWN_CAMERA_COLOUR = "#8b949e"
CONNECTED_COLOUR = "#2ea043"
RECONNECTING_COLOUR = "#d29922"
# More connections than this fold into one summary line until it is clicked.
STATUS_LINES_SHOWN = 3


def _camera_colour(index: int, shown: int) -> str:
    """The hand-picked colours while a page fits them; a bigger page gets hues spread by the
    golden ratio instead, so up to TILES_LIMIT tiles on screen never share one."""
    if shown <= len(CAMERA_COLOURS):
        return CAMERA_COLOURS[index % len(CAMERA_COLOURS)]
    return QColor.fromHsvF((index * 0.381966) % 1.0, 0.62, 0.92).name()


class _ClickableLabel(QLabel):
    def __init__(self, on_click: Callable[[], None]) -> None:
        super().__init__()
        self._on_click = on_click

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mousePressEvent(event)


class _FeedBridge(QObject):
    """Carries feed callbacks from the socket thread onto the GUI thread."""

    event_received = Signal(object, object)   # (client, AiEvent)
    status_changed = Signal(object, str)      # (client, status)


def _clock(epoch: float, with_milliseconds: bool = False) -> str:
    text = time.strftime("%H:%M:%S", time.localtime(epoch))
    return f"{text}.{int(epoch * 1000) % 1000:03d}" if with_milliseconds else text


def short_camera_name(label: str) -> str:
    """Unnamed cameras are labelled by their URL; the host alone tells them apart and fits."""
    host = urlsplit(label).hostname if "://" in label else None
    return host or label


def wrappable(text: str) -> str:
    """Compact JSON has no spaces, so a list row could only overflow; a zero-width space after
    each comma lets it wrap there without changing what is shown."""
    return text.replace(",", ",\u200b")


def _dot(colour: str) -> QIcon:
    def draw(painter: QPainter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colour))
        painter.drawEllipse(1, 1, 10, 10)
    return painted_icon(12, draw)


def tile_text(event: AiEvent) -> str:
    """AI time first, so it can be read against the camera's burned-in OSD clock."""
    shown = event.event_time if event.event_time is not None else event.received_at
    return f"{_clock(shown)}  {event.text}"


def _key(site_name: str, camera_label: str) -> str:
    """One camera across sites: two sites may both have a camera called "Gate". Site names
    come from a one-line field, so a newline cannot occur in one."""
    return f"{site_name}\n{camera_label}"


class AiEventPanel(QFrame):
    """Owns the feed connections of the sites on the wall, and only those."""

    def __init__(self, translator: Translator,
                 on_event_shown: Callable[[Camera, str, str, int], None],
                 on_camera_chosen: Callable[[str, Camera], None],
                 on_connection_change: Callable[[int, int], None],
                 frame_lag: Callable[[Camera], float | None] = lambda _camera: None) -> None:
        super().__init__()
        self.setObjectName("aiPanel")
        self.setMinimumWidth(260)
        self._translator = translator
        self._on_event_shown = on_event_shown
        self._frame_lag = frame_lag
        self._on_camera_chosen = on_camera_chosen
        self._on_connection_change = on_connection_change
        self._dots: dict[str, QIcon] = {}
        self._sites: tuple[Site, ...] = ()
        self._shown_keys: tuple[str, ...] = ()   # tiles on the page, in order: they get colours first
        # _key(site, label) -> the camera, and its colour, for the sites on the wall.
        self._cameras: dict[str, tuple[str, Camera]] = {}
        self._colours: dict[str, str] = {}
        self._client_sites: dict[AiFeedClient, str] = {}
        # One queue per connection: each feed has its own delay, so a single queue
        # ordered by arrival could hold a short-delay result behind a long-delay one.
        self._pending: dict[AiFeedClient, deque[AiEvent]] = {}
        self._connected: dict[AiFeedClient, bool] = {}
        self._bridge = _FeedBridge(self)
        self._bridge.event_received.connect(self._receive)
        self._bridge.status_changed.connect(self._show_status)
        # Runs only while results wait for their display time; an idle feed costs no ticks.
        self._release_timer = QTimer(self)
        self._release_timer.setInterval(RELEASE_INTERVAL_MS)
        self._release_timer.timeout.connect(self._release)

        box = QVBoxLayout(self)
        box.setContentsMargins(8, 8, 8, 8)
        title = QLabel(translator.t("ai_events"))
        title.setObjectName("eyebrow")
        box.addWidget(title)
        self._status_expanded = False
        self._status = _ClickableLabel(self._toggle_status)
        self._status.setObjectName("aiStatus")
        self._status.setWordWrap(True)
        self._status.setTextFormat(Qt.TextFormat.RichText)
        box.addWidget(self._status)
        self._filter = QComboBox()
        # activated: a combo box being destroyed still reports an index change (see
        # ai_feed_editor._CodePicker); _fill_filter applies its own changes.
        self._filter.activated.connect(self._apply_filter)
        box.addWidget(self._filter)
        self._list = QListWidget()
        self._list.setObjectName("aiEventList")
        # Rows wrap to the panel's width instead of running off to the right.
        self._list.setWordWrap(True)
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setSpacing(2)
        self._list.itemClicked.connect(self._choose_camera)
        box.addWidget(self._list, 1)

    @property
    def has_feed(self) -> bool:
        return bool(self._pending)

    def watch(self, sites: Sequence[Site], shown: Sequence[tuple[str, Camera]] = ()) -> None:
        """Follow the sites on the wall, connecting the AI feeds they carry; shown is the page's
        (site, camera) tiles, which get distinct colours. Page changes call this too, so only
        connections that were added or removed are touched: picking a camera of another site
        must not drop the results already flowing for the first one."""
        sites = tuple(sites)
        shown_keys = tuple(_key(site_name, camera.label) for site_name, camera in shown)
        wanted = [(site.name, feed) for site in sites for feed in site.ai_feeds]
        current = {(self._client_sites[client], client.config): client for client in self._pending}
        for connection, client in current.items():
            if connection not in wanted:
                client.stop()
                del self._pending[client], self._connected[client], self._client_sites[client]
        kept = [connection for connection in wanted if connection in current]
        if not kept:
            self._list.clear()   # a different place altogether: the old results do not belong
        if sites != self._sites or shown_keys != self._shown_keys:
            self._sites, self._shown_keys = sites, shown_keys
            self._fill_filter()
        for site_name, feed in wanted:
            if (site_name, feed) not in current:
                self._connect(site_name, feed)
        if not wanted:
            self._release_timer.stop()
        self._status.setToolTip("\n".join(f"{feed.address}  {self._delay_tip(feed)}"
                                           for _site_name, feed in wanted))
        self._render_status()

    def _connect(self, site_name: str, feed: AiFeedConfig) -> None:
        # Tag every callback with its client so results from a feed that was just
        # stopped (site switch) cannot land on the new site's tiles.
        client = AiFeedClient(
            feed,
            on_event=lambda event: self._bridge.event_received.emit(client, event),
            on_status=lambda status: self._bridge.status_changed.emit(client, status))
        self._pending[client] = deque()
        self._connected[client] = False
        self._client_sites[client] = site_name
        client.start()

    def stop(self) -> None:
        self._release_timer.stop()
        for client in self._pending:
            client.stop()
        self._pending.clear()
        self._connected.clear()
        self._client_sites.clear()
        self._sites = ()

    def _receive(self, client: AiFeedClient, event: AiEvent) -> None:
        pending = self._pending.get(client)
        if pending is not None:
            pending.append(event)
            if not self._release_timer.isActive():
                self._release_timer.start()

    def _show_status(self, client: AiFeedClient, status: str) -> None:
        if client not in self._connected:
            return
        self._connected[client] = status == STATUS_CONNECTED
        self._render_status()

    def _toggle_status(self) -> None:
        if len(self._connected) > STATUS_LINES_SHOWN:
            self._status_expanded = not self._status_expanded
            self._render_status()

    def _render_status(self) -> None:
        total, connected_count = len(self._connected), sum(self._connected.values())
        foldable = total > STATUS_LINES_SHOWN
        self._status.setCursor(Qt.CursorShape.PointingHandCursor if foldable
                               else Qt.CursorShape.ArrowCursor)
        if foldable and not self._status_expanded:
            colour = CONNECTED_COLOUR if connected_count == total else RECONNECTING_COLOUR
            text = self._translator.t("ai_status_summary", connected=connected_count, total=total)
            self._status.setText(f'<span style="color:{colour}">●</span> {text} ▾')
        else:
            lines = []
            for feed_client, connected in self._connected.items():
                colour = CONNECTED_COLOUR if connected else RECONNECTING_COLOUR
                text = self._translator.t("ai_connected" if connected else "ai_reconnecting",
                                          address=feed_client.config.address)
                lines.append(f'<span style="color:{colour}">●</span> {text}')
            self._status.setText("<br>".join(lines) + (" ▴" if foldable else ""))
        self._on_connection_change(sum(self._connected.values()), len(self._connected))

    def _release(self) -> None:
        """Oldest first, like a log; the list follows new rows only while it is at the bottom,
        so scrolling back to read is not yanked away."""
        now = time.time()
        scroll = self._list.verticalScrollBar()
        following = scroll.value() >= scroll.maximum()
        added = False
        for client, pending in self._pending.items():
            site_name = self._client_sites[client]
            for event in release_due(pending, now, client.config,
                                     lambda label: self._camera_frame_lag(site_name, label)):
                key = _key(site_name, event.camera_label)
                self._add_row(event, key)
                added = True
                line = client.config.tile_row(event.group)
                target = self._cameras.get(key)
                # A kind not ticked for the tiles, or an id mapped to no camera, stays in this list.
                if line is not None and target is not None:
                    self._on_event_shown(target[1], tile_text(event), self._colour(key), line)
        if added:
            while self._list.count() > MAX_ROWS:
                self._list.takeItem(0)
            if following:
                # Wrapped rows get their height in the next layout pass; scroll after it.
                QTimer.singleShot(0, self._list.scrollToBottom)
        if not any(self._pending.values()):
            self._release_timer.stop()

    def _delay_tip(self, feed: AiFeedConfig) -> str:
        if feed.align == ALIGN_FRAME:
            return self._translator.t("ai_delay_tip_frame")
        if feed.align == ALIGN_AI_TIME:
            return self._translator.t("ai_delay_tip_ai_time", delay=feed.delay_ms)
        return self._translator.t("ai_delay_tip_received", delay=feed.delay_ms)

    def _camera_frame_lag(self, site_name: str, label: str) -> float | None:
        target = self._cameras.get(_key(site_name, label))
        return self._frame_lag(target[1]) if target is not None else None

    def _colour(self, key: str) -> str:
        return self._colours.get(key, UNKNOWN_CAMERA_COLOUR)

    def _dot_for(self, key: str) -> QIcon:
        colour = self._colour(key)
        if colour not in self._dots:
            self._dots[colour] = _dot(colour)
        return self._dots[colour]

    def _name(self, key: str) -> str:
        """Short enough for the panel; the site is added once several sites share it."""
        site_name, _newline, label = key.partition("\n")
        name = short_camera_name(label)
        return f"{site_name} · {name}" if len(self._sites) > 1 else name

    def _add_row(self, event: AiEvent, key: str) -> None:
        marker = "⚠ " if event.has_clock_skew else ""
        shown = event.event_time if event.event_time is not None else event.received_at
        item = QListWidgetItem(f"{marker}{self._name(key)}  ·  {_clock(shown)}\n"
                               f"{wrappable(event.text)}")
        item.setIcon(self._dot_for(key))
        item.setData(Qt.ItemDataRole.UserRole, key)
        tip = self._translator.t(
            "ai_event_tip",
            ai_time=_clock(event.event_time, True) if event.event_time is not None else "—",
            received=_clock(event.received_at, True))
        if event.has_clock_skew:
            tip += "\n" + self._translator.t("ai_clock_skew", seconds=event.clock_skew)
        item.setToolTip(tip)
        self._list.addItem(item)
        item.setHidden(self._hidden(key))

    def _fill_filter(self) -> None:
        self._cameras = {_key(site.name, camera.label): (site.name, camera)
                         for site in self._sites for camera in site.cameras}
        order = [key for key in self._shown_keys if key in self._cameras]
        order += [key for key in self._cameras if key not in order]
        self._colours = {key: _camera_colour(index, len(self._shown_keys))
                         for index, key in enumerate(order)}
        chosen = self._filter.currentData()
        self._filter.blockSignals(True)
        self._filter.clear()
        self._filter.addItem(self._translator.t("ai_all_cameras"), None)
        for key in self._cameras:
            self._filter.addItem(self._dot_for(key), self._name(key), key)
        self._filter.setCurrentIndex(max(self._filter.findData(chosen), 0))
        self._filter.blockSignals(False)
        self._apply_filter()

    def _hidden(self, key: str) -> bool:
        chosen = self._filter.currentData()
        return chosen is not None and chosen != key

    def _apply_filter(self) -> None:
        for row in range(self._list.count()):
            item = self._list.item(row)
            item.setHidden(self._hidden(item.data(Qt.ItemDataRole.UserRole)))

    def _choose_camera(self, item: QListWidgetItem) -> None:
        target = self._cameras.get(item.data(Qt.ItemDataRole.UserRole))
        if target is not None:
            self._on_camera_chosen(*target)
