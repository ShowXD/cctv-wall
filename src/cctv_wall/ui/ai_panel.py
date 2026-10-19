"""Side panel listing AI results from a site's TCP feed, timed to match the video."""
from __future__ import annotations

import time
from collections import deque
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import QComboBox, QFrame, QLabel, QListWidget, QListWidgetItem, QVBoxLayout

from cctv_wall.ai_feed import STATUS_CONNECTED, AiEvent, AiFeedClient, AiFeedConfig, release_due
from cctv_wall.i18n import Translator
from cctv_wall.models import Camera, Site

MAX_ROWS = 500
RELEASE_INTERVAL_MS = 200


class _FeedBridge(QObject):
    """Carries feed callbacks from the socket thread onto the GUI thread."""

    event_received = Signal(object, object)   # (client, AiEvent)
    status_changed = Signal(object, str)      # (client, status)


def _clock(epoch: float, with_milliseconds: bool = False) -> str:
    text = time.strftime("%H:%M:%S", time.localtime(epoch))
    return f"{text}.{int(epoch * 1000) % 1000:03d}" if with_milliseconds else text


def tile_text(event: AiEvent) -> str:
    """AI time first, so it can be read against the camera's burned-in OSD clock."""
    shown = event.event_time if event.event_time is not None else event.received_at
    return f"{_clock(shown)}  {event.text}"


class AiEventPanel(QFrame):
    """Owns the feed connections of the site on screen, and only those."""

    def __init__(self, translator: Translator,
                 on_event_shown: Callable[[str, str], None],
                 on_camera_chosen: Callable[[Camera], None]) -> None:
        super().__init__()
        self.setObjectName("aiPanel")
        self.setMinimumWidth(260)
        self._translator = translator
        self._on_event_shown = on_event_shown
        self._on_camera_chosen = on_camera_chosen
        self._site: Site | None = None
        # One queue per connection: each feed has its own delay, so a single queue
        # ordered by arrival could hold a short-delay result behind a long-delay one.
        self._pending: dict[AiFeedClient, deque[AiEvent]] = {}
        self._connected: dict[AiFeedClient, bool] = {}
        self._bridge = _FeedBridge(self)
        self._bridge.event_received.connect(self._receive)
        self._bridge.status_changed.connect(self._show_status)
        self._release_timer = QTimer(self)
        self._release_timer.timeout.connect(self._release)

        box = QVBoxLayout(self)
        box.setContentsMargins(8, 8, 8, 8)
        title = QLabel(translator.t("ai_events"))
        title.setObjectName("eyebrow")
        box.addWidget(title)
        self._status = QLabel()
        self._status.setObjectName("aiStatus")
        self._status.setWordWrap(True)
        box.addWidget(self._status)
        self._filter = QComboBox()
        self._filter.currentIndexChanged.connect(self._apply_filter)
        box.addWidget(self._filter)
        self._list = QListWidget()
        self._list.setObjectName("aiEventList")
        self._list.itemClicked.connect(self._choose_camera)
        box.addWidget(self._list, 1)

    @property
    def has_feed(self) -> bool:
        return bool(self._pending)

    def watch(self, site: Site | None) -> None:
        """Follow the site on screen. Page changes call this too, so it must be cheap."""
        feeds = site.ai_feeds if site is not None else ()
        if (self._site is not None and site is not None and site.name == self._site.name
                and feeds == self._site.ai_feeds):
            if site.cameras != self._site.cameras:
                self._site = site
                self._fill_filter()
            return
        self.stop()
        self._site = site
        if not feeds:
            return
        self._list.clear()
        self._fill_filter()
        for feed in feeds:
            self._connect(feed)
        self._status.setToolTip("\n".join(
            f"{feed.address}  {self._translator.t('ai_delay_tip', delay=feed.delay_ms)}"
            for feed in feeds))
        self._release_timer.start(RELEASE_INTERVAL_MS)

    def _connect(self, feed: AiFeedConfig) -> None:
        # Tag every callback with its client so results from a feed that was just
        # stopped (site switch) cannot land on the new site's tiles.
        client = AiFeedClient(
            feed,
            on_event=lambda event: self._bridge.event_received.emit(client, event),
            on_status=lambda status: self._bridge.status_changed.emit(client, status))
        self._pending[client] = deque()
        self._connected[client] = False
        client.start()

    def stop(self) -> None:
        self._release_timer.stop()
        for client in self._pending:
            client.stop()
        self._pending.clear()
        self._connected.clear()
        self._site = None

    def _receive(self, client: AiFeedClient, event: AiEvent) -> None:
        pending = self._pending.get(client)
        if pending is not None:
            pending.append(event)

    def _show_status(self, client: AiFeedClient, status: str) -> None:
        if client not in self._connected:
            return
        self._connected[client] = status == STATUS_CONNECTED
        self._status.setText("\n".join(
            self._translator.t("ai_connected" if connected else "ai_reconnecting",
                               address=feed_client.config.address)
            for feed_client, connected in self._connected.items()))
        self._status.setProperty("connected", all(self._connected.values()))
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _release(self) -> None:
        now = time.time()
        for client, pending in self._pending.items():
            for event in release_due(pending, now, client.config.delay_ms):
                self._add_row(event)
                self._on_event_shown(event.camera, tile_text(event))

    def _add_row(self, event: AiEvent) -> None:
        marker = "⚠ " if event.has_clock_skew else ""
        item = QListWidgetItem(f"{marker}{tile_text(event)}  ·  {event.camera}")
        item.setData(Qt.ItemDataRole.UserRole, event.camera)
        tip = self._translator.t(
            "ai_event_tip",
            ai_time=_clock(event.event_time, True) if event.event_time is not None else "—",
            received=_clock(event.received_at, True))
        if event.has_clock_skew:
            tip += "\n" + self._translator.t("ai_clock_skew", seconds=event.clock_skew)
        item.setToolTip(tip)
        self._list.insertItem(0, item)
        item.setHidden(self._hidden(event.camera))
        while self._list.count() > MAX_ROWS:
            self._list.takeItem(self._list.count() - 1)

    def _fill_filter(self) -> None:
        chosen = self._filter.currentData()
        self._filter.blockSignals(True)
        self._filter.clear()
        self._filter.addItem(self._translator.t("ai_all_cameras"), None)
        for camera in self._site.cameras if self._site is not None else ():
            self._filter.addItem(camera.label, camera.label)
        self._filter.setCurrentIndex(max(self._filter.findData(chosen), 0))
        self._filter.blockSignals(False)
        self._apply_filter()

    def _hidden(self, camera_name: str) -> bool:
        chosen = self._filter.currentData()
        return chosen is not None and chosen != camera_name

    def _apply_filter(self) -> None:
        for row in range(self._list.count()):
            item = self._list.item(row)
            item.setHidden(self._hidden(item.data(Qt.ItemDataRole.UserRole)))

    def _choose_camera(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.ItemDataRole.UserRole)
        site = self._site
        camera = next((c for c in site.cameras if c.label == name), None) if site else None
        if camera is not None:
            self._on_camera_chosen(camera)
