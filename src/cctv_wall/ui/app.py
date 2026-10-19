"""The monitor workspace: application state coordinates dedicated Qt presentation views."""
from __future__ import annotations

import os
import re
from dataclasses import replace
from threading import Timer
from typing import Callable

from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QSpinBox, QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QSplitter, QToolButton, QVBoxLayout,
                               QStyle, QWidget)

from cctv_wall import layout
from cctv_wall.event_log import logger
from cctv_wall.i18n import LANGUAGE_LABELS, Translator
from cctv_wall.models import TILES_LIMIT, Camera, Site, Workspace
from cctv_wall.player import PlaybackError, PlayerFactory
from cctv_wall.resources import ProcessUsage, ResourceMonitor
from cctv_wall.ui import site_commands
from cctv_wall.ui.ai_panel import AiEventPanel
from cctv_wall.ui.editor import open_editor
from cctv_wall.ui.frameless import FramelessGrips
from cctv_wall.ui.logs import show_log_dialog
from cctv_wall.ui.navigation import SiteNavigation
from cctv_wall.ui.view_mode import ViewMode
from cctv_wall.ui.wall import WallView
from cctv_wall.urls import direct_url_with_stream

FactoryBuilder = Callable[[bool], PlayerFactory]
WorkspaceSaver = Callable[[Workspace], None]
NATIVE_SHUTDOWN_DEADLINE_SECONDS = 3.0


def wall_needs_reload(before: Workspace, after: Workspace, site_on_screen: str) -> bool:
    """Reconnecting costs every visible stream, so only a change to the site on screen earns it.

    Its cameras or AI connections changed, it was renamed or removed, or another site
    became the active one (a duplicate is selected straight away).
    """
    active = after.active_site
    if active is None or active.name != site_on_screen:
        return True
    return before.site(site_on_screen) != active
# Navigation action -> the command that carries it out. Adding one means adding a row.
SITE_COMMANDS = {
    "duplicate": site_commands.duplicate_site,
    "rename": site_commands.rename_site,
    "delete": site_commands.delete_site,
    "ai_feeds": site_commands.edit_site_ai_feeds,
    "add_camera": site_commands.add_camera,
}
CAMERA_COMMANDS = {
    "edit_camera": site_commands.edit_camera_at,
    "delete_camera": site_commands.delete_camera_at,
}


class MainWindow(QMainWindow):
    """Coordinates navigation, persistence, and player lifecycle without drawing video itself."""

    def __init__(self, workspace: Workspace, build_factory: FactoryBuilder,
                 save: WorkspaceSaver) -> None:
        super().__init__()
        self._workspace = workspace
        self._save = save
        self._page = 0
        self._active_site_name = workspace.active_site.name if workspace.active_site else ""
        self._translator = Translator(workspace.language)
        self._resource_monitor = ResourceMonitor()
        self._usage: ProcessUsage | None = None
        self._factory_builder = build_factory
        self._factory = self._create_factory(workspace.strict_sync)
        self._focused_camera: Camera | None = None
        self._page_before_focus = 0
        self._is_shutdown = False
        self._view = ViewMode()

        self.setWindowTitle(self._translator.t("app_title"))
        self.setMinimumSize(960, 600)
        self._restore_geometry(workspace.geometry)
        self._build_ui()
        self._grips = FramelessGrips(self)
        self._fitted_to_video = False
        self._apply_view_mode()
        self._reload_sites()
        self._resource_timer = QTimer(self)
        self._resource_timer.timeout.connect(self._sample_resources)
        self._resource_timer.start(2000)
        self._sample_resources()
        QShortcut(QKeySequence("F11"), self, activated=self._toggle_wall_fullscreen)
        QShortcut(QKeySequence("Escape"), self, activated=self._exit_immersive_mode)
        QShortcut(QKeySequence("Ctrl+B"), self, activated=self._toggle_sidebar)
        QShortcut(QKeySequence("PgUp"), self, activated=self._previous_page)
        QShortcut(QKeySequence("PgDown"), self, activated=self._next_page)
        QShortcut(QKeySequence("Ctrl+PgUp"), self, activated=lambda: self._step_site(-1))
        QShortcut(QKeySequence("Ctrl+PgDown"), self, activated=lambda: self._step_site(1))
        QShortcut(QKeySequence("F5"), self, activated=self._show_current_page)

    @property
    def _site(self) -> Site | None:
        return self._workspace.site(self._active_site_name) or self._workspace.active_site

    @property
    def _cameras(self) -> tuple[Camera, ...]:
        site = self._site
        return site.cameras if site else ()

    def _create_factory(self, strict_sync: bool) -> PlayerFactory:
        """Keep the normal wall available if the optional GStreamer runtime is absent."""
        try:
            factory = self._factory_builder(strict_sync)
            logger().info("playback backend=%s", "strict-timestamp-sync" if strict_sync else "vlc")
            return factory
        except PlaybackError as error:
            if strict_sync:
                logger().warning("strict sync unavailable; using VLC backend: %s", error)
                self._workspace = self._workspace.with_strict_sync(False)
            factory = self._factory_builder(False)
            logger().info("playback backend=vlc")
            return factory

    def _build_ui(self) -> None:
        splitter = QSplitter()
        splitter.setObjectName("mainSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        self._navigation = SiteNavigation(self._on_site_selected, self._open_settings,
                                          self._on_site_action, self._translator,
                                          self._on_camera_selected, self._on_sites_reordered,
                                          self._on_camera_action)
        splitter.addWidget(self._navigation)
        self._ai_panel = AiEventPanel(
            self._translator,
            on_event_shown=lambda camera_name, text: self._wall.show_ai_event(camera_name, text),
            on_camera_chosen=lambda camera: self._on_camera_selected(self._active_site_name, camera))
        splitter.addWidget(self._monitor_panel())
        splitter.addWidget(self._ai_panel)
        splitter.setSizes([self._workspace.sidebar_width, 1180, 300])
        # A wider or narrower window changes the wall only; the side panels keep their width.
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        self._splitter = splitter
        self.setCentralWidget(splitter)

    def _monitor_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("monitorPanel")
        layout_box = QVBoxLayout(panel)
        layout_box.setContentsMargins(0, 0, 0, 0)
        layout_box.setSpacing(0)
        self._control_bar_widget = self._control_bar()
        layout_box.addWidget(self._control_bar_widget)
        self._wall = WallView(self._factory, self._workspace.tiles_per_page,
                              on_solo=self._toggle_camera_focus,
                              on_health_change=self._refresh_status,
                              translator=self._translator,
                              on_stream_change=self._change_camera_stream)
        layout_box.addWidget(self._wall, 1)
        return panel

    def _toggle_wall_fullscreen(self) -> None:
        """Fullscreen the Qt shell, never the embedded VLC surface itself."""
        if self._view.fullscreen:
            self._exit_wall_fullscreen()
            return
        self._view = self._view.enter_fullscreen(self.isMaximized())
        self._apply_view_mode()
        self.showFullScreen()

    def _exit_wall_fullscreen(self) -> None:
        if not self._view.fullscreen:
            return
        was_maximized = self._view.was_maximized
        self._view = self._view.exit_fullscreen()
        self._apply_view_mode()
        if was_maximized:
            self.showMaximized()
        else:
            self.showNormal()

    def _toggle_window_maximized(self) -> None:
        """Fill the existing client area with video without changing the window state."""
        self._view = self._view.toggle_filled()
        self._apply_view_mode()
        self._maximize_button.setToolTip(self._translator.t(
            "maximize" if self._view.chrome_visible else "restore_window"))

    def _exit_immersive_mode(self) -> None:
        if self._view.fullscreen:
            self._exit_wall_fullscreen()
        elif self._focused_camera is not None:
            self._toggle_camera_focus(self._focused_camera)
        elif self._view.filled:
            self._toggle_window_maximized()

    def _apply_view_mode(self) -> None:
        """Bring every widget in line with the current mode. Safe to call repeatedly."""
        visible = self._view.chrome_visible
        if visible and not self._view.fullscreen:
            self._set_wall_frameless(False)
        self._navigation.setVisible(visible and self._workspace.sidebar_visible)
        self._control_bar_widget.setVisible(visible)
        self._refresh_ai_panel()
        self._wall.set_immersive(not visible)
        if not visible and not self._view.fullscreen:
            self._set_wall_frameless(self._view.filled)
        self._grips.set_visible(self._view.grips_visible)

    def _set_wall_frameless(self, frameless: bool) -> None:
        """Remove only the title-bar pixels; size and position stay operator-controlled."""
        if bool(self.windowFlags() & Qt.WindowType.FramelessWindowHint) == frameless:
            return
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, frameless)
        self.show()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._fitted_to_video:
            self._fitted_to_video = True
            # The grid has its real size only after this first show has been laid out.
            QTimer.singleShot(0, self._fit_to_video)

    def _fit_to_video(self) -> None:
        """Only at opening: size the window so each tile is 16:9; later resizes are the operator's."""
        surface = self._wall.video_surface_size()
        if surface is None or self.isMaximized() or self.isFullScreen():
            return
        available = self.screen().availableGeometry()
        frame_w = self.frameGeometry().width() - self.width()
        frame_h = self.frameGeometry().height() - self.height()
        width, height = layout.fit_window_to_video(
            (self.width(), self.height()), surface, layout.grid_shape(self._wall.tile_count),
            (self.minimumWidth(), self.minimumHeight()),
            (available.width() - frame_w, available.height() - frame_h))
        self.resize(width, height)
        # A taller window may now run off the screen; pull it back without moving it otherwise.
        frame = self.frameGeometry()
        x = min(frame.left(), available.right() - frame.width() + 1)
        y = min(frame.top(), available.bottom() - frame.height() + 1)
        self.move(max(x, available.left()), max(y, available.top()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._grips.relayout()

    def _control_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("controlBar")
        layout_box = QHBoxLayout(bar)
        layout_box.setContentsMargins(12, 8, 12, 8)
        layout_box.setSpacing(8)
        layout_box.addWidget(self._button("☰", self._translator.t("toggle_sidebar"),
                                          self._toggle_sidebar, "compactAction"))
        # Everything the operator reads lives in this one bar: where, how many are live,
        # and what it costs the PC. A separate header and status bar only took video space.
        self._site_title = QLabel()
        self._site_title.setObjectName("siteTitle")
        layout_box.addWidget(self._site_title)
        self._live_badge = QLabel()
        self._live_badge.setObjectName("liveBadge")
        layout_box.addWidget(self._live_badge)
        self._resource_status = QLabel()
        self._resource_status.setObjectName("resourceStatus")
        layout_box.addWidget(self._resource_status)
        layout_box.addStretch(1)
        layout_box.addWidget(self._button("‹", self._translator.t("previous"), self._previous_page, "pageControl"))
        self._page_label = QLabel()
        self._page_label.setObjectName("pageLabel")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_box.addWidget(self._page_label)
        layout_box.addWidget(self._button("›", self._translator.t("next"), self._next_page, "pageControl"))
        self._tiles_box = QSpinBox()
        self._tiles_box.setObjectName("tilesBox")
        self._tiles_box.setToolTip(self._translator.t("tiles_per_page"))
        # A number is all this needs: typing, the wheel and the arrow keys all change it,
        # so the spin buttons and the unit only cost toolbar width.
        self._tiles_box.setPrefix("▦ ")
        self._tiles_box.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._tiles_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tiles_box.setFixedWidth(64)
        self._tiles_box.setRange(1, TILES_LIMIT)
        self._tiles_box.setValue(self._workspace.tiles_per_page)
        # Typing "12" must not first reconnect a 1-tile page: apply on Enter, focus-out or arrows.
        self._tiles_box.setKeyboardTracking(False)
        self._tiles_box.valueChanged.connect(self._on_tiles_changed)
        layout_box.addWidget(self._tiles_box)
        self._language_box = QComboBox()
        self._language_box.setObjectName("languageBox")
        self._language_box.setToolTip(self._translator.t("language"))
        self._language_box.setMinimumWidth(100)
        for language, label in LANGUAGE_LABELS.items():
            self._language_box.addItem(label, language)
        self._language_box.setCurrentIndex(self._language_box.findData(self._translator.language))
        self._language_box.currentIndexChanged.connect(self._on_language_selected)
        layout_box.addWidget(self._language_box)
        self._maximize_button = self._icon_button(QStyle.StandardPixmap.SP_TitleBarMaxButton,
                                                  self._translator.t("maximize"),
                                                  self._toggle_window_maximized)
        layout_box.addWidget(self._maximize_button)
        self._sync_button = self._button(self._translator.t("sync_short"),
                                         self._translator.t("enable_strict_sync"),
                                         self._toggle_strict_sync, "syncAction")
        self._sync_button.setCheckable(True)
        self._sync_button.setChecked(self._workspace.strict_sync)
        self._refresh_sync_button()
        layout_box.addWidget(self._sync_button)
        self._ai_button = self._button(self._translator.t("ai_short"), self._translator.t("ai_events"),
                                       self._refresh_ai_panel)
        self._ai_button.setCheckable(True)
        self._ai_button.setChecked(True)
        self._ai_button.hide()
        layout_box.addWidget(self._ai_button)
        layout_box.addWidget(self._icon_button(QStyle.StandardPixmap.SP_BrowserReload,
                                               self._translator.t("reload_tip"),
                                               self._show_current_page))
        layout_box.addWidget(self._icon_button(QStyle.StandardPixmap.SP_FileDialogDetailedView,
                                               self._translator.t("logs"), self._show_logs))
        return bar

    @staticmethod
    def _button(text: str, tooltip: str, action: Callable[[], None],
                object_name: str = "") -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setObjectName(object_name)
        button.clicked.connect(action)
        return button

    @staticmethod
    def _icon_button(icon: QStyle.StandardPixmap, tooltip: str,
                     action: Callable[..., None]) -> QToolButton:
        """Use Qt's monochrome icons instead of emoji, whose Windows metrics vary by font."""
        button = QToolButton()
        button.setObjectName("compactAction")
        button.setIcon(button.style().standardIcon(icon))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        button.clicked.connect(action)
        return button

    def _reload_sites(self) -> None:
        self._exit_camera_focus_if_needed()
        active = self._workspace.active_site
        self._active_site_name = active.name if active else ""
        self._navigation.set_workspace(self._workspace)
        self._page = 0
        self._show_current_page()

    def _show_current_page(self) -> None:
        cameras = self._displayed_cameras
        self._page = layout.clamp_page(self._page, len(cameras), self._wall.tiles_per_page)
        self._wall.show_page(cameras, self._page)
        self._ai_panel.watch(self._site)
        self._refresh_ai_panel()
        self._refresh_status()

    def _refresh_ai_panel(self) -> None:
        """The panel and its toggle exist only for a site with an AI feed configured."""
        has_feed = self._ai_panel.has_feed
        self._ai_button.setVisible(has_feed)
        self._ai_panel.setVisible(has_feed and self._view.chrome_visible
                                  and self._ai_button.isChecked())

    def _refresh_status(self) -> None:
        total = len(self._displayed_cameras)
        pages = self._wall.page_count(total)
        visible = min(self._wall.tiles_per_page,
                      max(total - self._page * self._wall.tiles_per_page, 0))
        self._site_title.setText(self._active_site_name or self._translator.t("no_site"))
        self._live_badge.setText(self._translator.t("live", live=self._wall.playing_count, total=visible))
        self._page_label.setText(self._translator.t("page", current=self._page + 1, total=pages))
        self._show_resources()

    def _sample_resources(self) -> None:
        """Only the 2 s timer samples, so CPU is always averaged over the same interval.

        Sampling on every status refresh as well made the window — and the number — jump.
        """
        self._usage = self._resource_monitor.sample()
        self._show_resources()

    def _show_resources(self) -> None:
        """The bar says how much of the whole PC the wall uses; the detail waits in the tooltip."""
        usage = self._usage
        unknown = self._translator.t("usage_unknown")
        cpu = unknown
        if usage is not None and usage.cpu_percent is not None:
            share = usage.machine_percent if usage.machine_percent is not None else usage.cpu_percent
            cpu = f"{share:.0f}%"
        memory = (f"{usage.memory_mebibytes:.0f} MB"
                  if usage is not None and usage.memory_mebibytes is not None else unknown)
        self._resource_status.setText(self._translator.t("usage", cpu=cpu, memory=memory))
        players = self._wall.allocated_player_count
        if usage is not None and usage.cores_used is not None:
            tip = self._translator.t("usage_tip", players=players, cores=usage.cores_used,
                                     total=usage.core_count)
        else:
            tip = self._translator.t("players_tip", players=players)
        self._resource_status.setToolTip(tip)

    def _on_site_selected(self, site_name: str) -> None:
        """Choosing the site on screen again (e.g. arrowing back onto its row) restores the grid."""
        if not site_name:
            return
        self._exit_camera_focus_if_needed()
        if site_name == self._active_site_name:
            return
        self._active_site_name = site_name
        self._workspace = self._workspace.with_last_site(site_name)
        self._page = 0
        self._show_current_page()
        self._persist()

    def _on_camera_selected(self, site_name: str, camera: Camera) -> None:
        """Jump to one camera: switch site, turn to its page, then enlarge it.

        Choosing the camera that is already enlarged puts the grid back.
        """
        if self._focused_camera == camera and site_name == self._active_site_name:
            self._toggle_camera_focus(camera)
            return
        self._exit_camera_focus_if_needed()
        self._on_site_selected(site_name)
        cameras = self._cameras
        if camera not in cameras:
            return
        page = cameras.index(camera) // self._wall.tiles_per_page
        if page != self._page:
            self._page = page
            self._show_current_page()
        self._toggle_camera_focus(camera)

    def _on_sites_reordered(self, workspace: Workspace) -> None:
        """Persist a drag immediately; the wall only reloads when the order really changed."""
        if workspace == self._workspace:
            return
        self._workspace = workspace
        self._persist()
        self._reload_sites()

    def _on_site_action(self, action: str, site_name: str) -> None:
        """Route a navigation shortcut, keeping this window the only workspace owner.

        An empty site name means "the site on screen" (the sidebar's AI button).
        """
        site_name = site_name or self._active_site_name
        command = SITE_COMMANDS.get(action)
        if command is not None:
            self._apply_site_command(command(self, self._workspace, self._translator, site_name))

    def _on_camera_action(self, action: str, site_name: str, index: int) -> None:
        """Edit or delete one camera from the sidebar; an edited camera on screen reconnects alone."""
        command = CAMERA_COMMANDS.get(action)
        site = self._workspace.site(site_name)
        if command is None or site is None or not 0 <= index < len(site.cameras):
            return
        old = site.cameras[index]
        updated = command(self, self._workspace, self._translator, site_name, index)
        if updated is None:
            return
        before, self._workspace = self._workspace, updated
        self._persist()
        if action == "edit_camera" and site_name == self._active_site_name:
            self._show_replaced_camera(old, updated.site(site_name).cameras[index])
        else:
            self._apply_workspace_change(before)

    def _apply_site_command(self, updated: Workspace | None) -> None:
        """None means the operator cancelled, or the command refused the change."""
        if updated is None:
            return
        before, self._workspace = self._workspace, updated
        self._persist()
        self._apply_workspace_change(before)

    def _apply_workspace_change(self, before: Workspace) -> None:
        if wall_needs_reload(before, self._workspace, self._active_site_name):
            self._reload_sites()
        else:
            self._navigation.set_workspace(self._workspace)

    def _on_tiles_changed(self, tiles: int) -> None:
        """Only the page layout changes; the playback backend and its decoders stay."""
        if tiles == self._workspace.tiles_per_page:
            return
        self._exit_camera_focus_if_needed()
        self._wall.stop()
        self._workspace = self._workspace.with_tiles_per_page(tiles)
        self._wall.configure(self._factory, self._workspace.tiles_per_page)
        self._persist()
        logger().info("tiles per page=%d", self._workspace.tiles_per_page)
        self._page = 0
        self._show_current_page()

    def _on_language_selected(self, index: int) -> None:
        language = self._language_box.itemData(index)
        if language == self._translator.language:
            return
        self._workspace = self._workspace.with_language(str(language))
        self._translator = Translator(self._workspace.language)
        self._workspace = self._workspace.with_sidebar(self._sidebar_width(),
                                                       self._workspace.sidebar_visible)
        self._persist()
        self._wall.stop()
        self._ai_panel.stop()
        previous = self.takeCentralWidget()
        if previous is not None:
            previous.deleteLater()
        self.setWindowTitle(self._translator.t("app_title"))
        self._build_ui()
        self._grips.relayout()
        self._apply_view_mode()
        self._reload_sites()

    def _previous_page(self) -> None:
        self._page = max(0, self._page - 1)
        self._show_current_page()

    def _next_page(self) -> None:
        last_page = self._wall.page_count(len(self._displayed_cameras)) - 1
        self._page = min(last_page, self._page + 1)
        self._show_current_page()

    def _step_site(self, step: int) -> None:
        names = self._workspace.site_names
        if not names:
            return
        current = names.index(self._active_site_name) if self._active_site_name in names else 0
        self._on_site_selected(names[(current + step) % len(names)])
        self._navigation.set_workspace(self._workspace)

    def _sidebar_width(self) -> int:
        """The splitter knows the dragged width only while the sidebar is on screen."""
        if self._navigation.isVisible():
            return self._splitter.sizes()[0]
        return self._workspace.sidebar_width

    def _toggle_sidebar(self) -> None:
        self._workspace = self._workspace.with_sidebar(self._sidebar_width(),
                                                       not self._workspace.sidebar_visible)
        self._apply_view_mode()
        if self._workspace.sidebar_visible:
            sizes = self._splitter.sizes()
            spare = sizes[0] + sizes[1] - self._workspace.sidebar_width
            self._splitter.setSizes([self._workspace.sidebar_width, spare, *sizes[2:]])
        self._persist()

    def _show_logs(self) -> None:
        show_log_dialog(self, self._translator, self._cameras)

    def _toggle_strict_sync(self, enabled: bool) -> None:
        if not self._set_strict_sync(enabled):
            self._sync_button.setChecked(self._workspace.strict_sync)

    def _refresh_sync_button(self) -> None:
        self._sync_button.setToolTip(self._translator.t(
            "disable_strict_sync" if self._workspace.strict_sync else "enable_strict_sync"))

    def _set_strict_sync(self, enabled: bool) -> bool:
        """Atomically replace the wall backend after diagnostics approve its sources."""
        if enabled == self._workspace.strict_sync:
            return True
        try:
            new_factory = self._factory_builder(enabled)
        except PlaybackError as error:
            # A dialog the operator dismisses leaves no trace; the log has to keep one.
            logger().warning("strict sync refused: %s", error)
            QMessageBox.warning(self, self._translator.t("sync_diagnostics"), str(error))
            return False
        self._wall.stop()
        old_factory, self._factory = self._factory, new_factory
        self._wall.configure(new_factory, self._workspace.tiles_per_page)
        old_factory.shutdown()
        self._workspace = self._workspace.with_strict_sync(enabled)
        self._sync_button.setChecked(enabled)
        self._refresh_sync_button()
        self._persist()
        logger().info("strict timestamp sync %s", "enabled" if enabled else "disabled")
        self._show_current_page()
        return True

    def _change_camera_stream(self, camera: Camera, stream: int) -> None:
        """Persist a right-click stream choice and reconnect only that camera."""
        url = direct_url_with_stream(camera.url, stream)
        if url is None:
            return  # no recognisable stream marker: guessing the URL format is unsafe
        replacement = replace(camera, url=url)
        updated = self._workspace.with_camera_replaced(camera, replacement)
        if updated is self._workspace:
            return
        self._workspace = updated
        self._persist()
        self._show_replaced_camera(camera, replacement)

    def _show_replaced_camera(self, old: Camera, new: Camera) -> None:
        """One edited camera reconnects alone, unless strict sync forces the whole page."""
        if self._focused_camera == old:
            self._focused_camera = new
        self._navigation.set_workspace(self._workspace)
        if not self._wall.replace_camera(old, new):
            self._show_current_page()

    def _open_settings(self, site_name: str | None = None) -> None:
        before = self._workspace
        open_editor(self, self._workspace, self._on_workspace_edited, self._translator,
                    initial_site_name=site_name)
        self._apply_workspace_change(before)

    def _on_workspace_edited(self, workspace: Workspace) -> None:
        """Each settings action is saved at once; the wall waits until the dialog closes."""
        self._workspace = workspace
        self._persist()
        self._navigation.set_workspace(workspace)

    @property
    def _displayed_cameras(self) -> tuple[Camera, ...]:
        return (self._focused_camera,) if self._focused_camera is not None else self._cameras

    def _toggle_camera_focus(self, camera: Camera) -> None:
        """Reflow an existing tile; focus must never tear down a healthy RTSP session.

        Only the wall changes: navigation, toolbar and AI panel stay usable, so the
        enlarged camera can be compared with its results and left the same way it was entered.
        """
        if self._focused_camera == camera:
            self._wall.restore_grid()
            self._focused_camera = None
            self._page = self._page_before_focus
        else:
            if not self._wall.focus_camera(camera):
                return
            self._page_before_focus = self._page
            self._focused_camera = camera
            self._page = 0
        self._refresh_status()

    def _exit_camera_focus_if_needed(self) -> None:
        if self._focused_camera is not None:
            self._toggle_camera_focus(self._focused_camera)

    def _persist(self) -> None:
        try:
            self._save(self._workspace)
        except RuntimeError as error:
            QMessageBox.critical(self, self._translator.t("save_error"), str(error))

    def _restore_geometry(self, geometry: str) -> None:
        match = re.fullmatch(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", geometry)
        if match:
            width, height, x, y = map(int, match.groups())
            self.setGeometry(x, y, width, height)
        else:
            self.resize(1280, 800)

    def shutdown(self, persist: bool = True) -> None:
        """Release native resources once; dry-run callers can opt out of persistence."""
        if self._is_shutdown:
            return
        self._is_shutdown = True
        self._resource_timer.stop()
        if persist:
            self._workspace = self._workspace.with_geometry(
                f"{self.width()}x{self.height()}+{self.x()}+{self.y()}").with_sidebar(
                self._sidebar_width(), self._workspace.sidebar_visible)
            self._persist()
        self._ai_panel.stop()
        self._wall.stop()
        self._factory.shutdown()

    def closeEvent(self, event) -> None:
        """Never let a stuck native VLC decoder leave the operator to kill the process.

        libVLC normally tears down in a fraction of a second.  A broken RTSP source can
        instead block inside its native release call, where Python cannot cancel it.
        The watchdog is only a last resort: settings are persisted before native teardown
        begins, then Windows terminates the process if that teardown never returns.
        """
        watchdog = Timer(NATIVE_SHUTDOWN_DEADLINE_SECONDS, os._exit, args=(0,))
        watchdog.daemon = True
        watchdog.start()
        try:
            self.shutdown()
        finally:
            watchdog.cancel()
        event.accept()
