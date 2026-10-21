"""The bar above the wall: where the operator is, what is live, what it costs, and the controls."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QActionGroup, QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QMenu, QSpinBox, QStyle,
                               QToolButton, QWidget)

from cctv_wall.i18n import LANGUAGE_LABELS, Translator
from cctv_wall.models import TILES_LIMIT, Workspace
from cctv_wall.resources import ProcessUsage
from cctv_wall.ui.theme import painted_icon

# A grey that reads on both themes; Qt's standard title-bar icons are white, and the ◐
# character renders tiny in Segoe UI.
ICON_COLOUR = QColor("#7f93ab")
ICON_SIZE = 36


def _outline(painter: QPainter) -> None:
    painter.setPen(QPen(ICON_COLOUR, 3))
    painter.setBrush(ICON_COLOUR)


def _draw_theme(painter: QPainter) -> None:
    _outline(painter)
    painter.drawPie(4, 4, 28, 28, 90 * 16, 180 * 16)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(4, 4, 28, 28)


def _draw_fill(painter: QPainter) -> None:
    """Four corners pointing outwards: video takes the whole window."""
    _outline(painter)
    for x, y, dx, dy in ((5, 5, 1, 1), (31, 5, -1, 1), (5, 31, 1, -1), (31, 31, -1, -1)):
        painter.drawLine(x, y, x + 9 * dx, y)
        painter.drawLine(x, y, x, y + 9 * dy)


class ControlBar(QFrame):
    """Shows state it is given and reports clicks; the main window owns every decision.

    Everything the operator reads lives in this one bar: where, how many are live, and what
    it costs the PC. A separate header and status bar only took video space.
    """

    def __init__(self, translator: Translator, workspace: Workspace, menu_parent: QWidget, *,
                 on_toggle_sidebar: Callable[[], None], on_previous_page: Callable[[], None],
                 on_next_page: Callable[[], None], on_tiles_changed: Callable[[int], None],
                 on_language: Callable[[str], None], on_theme: Callable[[str], None],
                 on_fill: Callable[[], None], on_strict_sync: Callable[[bool], None],
                 on_ai_panel: Callable[[], None], on_reload: Callable[[], None],
                 on_logs: Callable[[], None]) -> None:
        super().__init__()
        self._translator = translator
        self.setObjectName("controlBar")
        box = QHBoxLayout(self)
        box.setContentsMargins(12, 8, 12, 8)
        box.setSpacing(8)
        box.addWidget(self._button("☰", translator.t("toggle_sidebar"), on_toggle_sidebar,
                                   "compactAction"))
        self._site_title = QLabel()
        self._site_title.setObjectName("siteTitle")
        box.addWidget(self._site_title)
        self._live_badge = QLabel()
        self._live_badge.setObjectName("liveBadge")
        box.addWidget(self._live_badge)
        self._resource_status = QLabel()
        self._resource_status.setObjectName("resourceStatus")
        box.addWidget(self._resource_status)
        box.addStretch(1)
        box.addWidget(self._button("‹", translator.t("previous"), on_previous_page, "pageControl"))
        self._page_label = QLabel()
        self._page_label.setObjectName("pageLabel")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(self._page_label)
        box.addWidget(self._button("›", translator.t("next"), on_next_page, "pageControl"))
        box.addWidget(self._tiles_box(workspace.tiles_per_page, on_tiles_changed))
        box.addWidget(self._language_box(on_language))
        box.addWidget(self._theme_button(workspace.theme, menu_parent, on_theme))
        self._fill_button = self._icon_button(painted_icon(ICON_SIZE, _draw_fill),
                                              translator.t("maximize"), on_fill)
        box.addWidget(self._fill_button)
        self._sync_button = self._button(translator.t("sync_short"), "", on_strict_sync, "syncAction")
        self._sync_button.setCheckable(True)
        self.set_sync(workspace.strict_sync)
        box.addWidget(self._sync_button)
        self._ai_button = self._button(f"● {translator.t('ai_short')}", translator.t("ai_events"),
                                       on_ai_panel)
        self._ai_button.setCheckable(True)
        self._ai_button.setChecked(True)
        self._ai_button.hide()
        box.addWidget(self._ai_button)
        box.addWidget(self._icon_button(QStyle.StandardPixmap.SP_BrowserReload,
                                        translator.t("reload_tip"), on_reload))
        box.addWidget(self._icon_button(QStyle.StandardPixmap.SP_FileDialogDetailedView,
                                        translator.t("logs"), on_logs))

    @staticmethod
    def _button(text: str, tooltip: str, action: Callable[..., None],
                object_name: str = "") -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setObjectName(object_name)
        button.clicked.connect(action)
        return button

    @staticmethod
    def _icon_button(icon: QIcon | QStyle.StandardPixmap, tooltip: str,
                     action: Callable[[], None]) -> QToolButton:
        """Monochrome icons instead of emoji, whose Windows metrics vary by font."""
        button = QToolButton()
        button.setObjectName("compactAction")
        button.setIcon(icon if isinstance(icon, QIcon) else button.style().standardIcon(icon))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        button.clicked.connect(action)
        return button

    def _tiles_box(self, tiles: int, on_change: Callable[[int], None]) -> QSpinBox:
        box = QSpinBox()
        box.setObjectName("tilesBox")
        box.setToolTip(self._translator.t("tiles_per_page"))
        # A number is all this needs: typing, the wheel and the arrow keys all change it,
        # so the spin buttons and the unit only cost toolbar width.
        box.setPrefix("▦ ")
        box.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setFixedWidth(64)
        box.setRange(1, TILES_LIMIT)
        box.setValue(tiles)
        # Typing "12" must not first reconnect a 1-tile page: apply on Enter, focus-out or arrows.
        box.setKeyboardTracking(False)
        box.valueChanged.connect(on_change)
        return box

    def _language_box(self, on_change: Callable[[str], None]) -> QComboBox:
        box = QComboBox()
        box.setObjectName("languageBox")
        box.setToolTip(self._translator.t("language"))
        for language, label in LANGUAGE_LABELS.items():
            box.addItem(label, language)
        box.setCurrentIndex(box.findData(self._translator.language))
        box.currentIndexChanged.connect(lambda index: on_change(str(box.itemData(index))))
        return box

    def _theme_button(self, theme: str, menu_parent: QWidget,
                      on_change: Callable[[str], None]) -> QToolButton:
        """Follow Windows, or force dark or light; only colours change, so no camera reconnects."""
        button = QToolButton()
        button.setObjectName("compactAction")
        button.setIcon(painted_icon(ICON_SIZE, _draw_theme))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(self._translator.t("appearance"))
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        # Parented to the window, not the bar: libvlc makes the bar a native child, and a popup
        # with a native child as its transient parent triggers a Qt warning.
        menu = QMenu(menu_parent)
        button.destroyed.connect(menu.deleteLater)   # a language change rebuilds the bar
        group = QActionGroup(menu)
        for choice, label in (("system", self._translator.t("theme_system")),
                              ("dark", self._translator.t("theme_dark")),
                              ("light", self._translator.t("theme_light"))):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(choice == theme)
            action.triggered.connect(lambda _checked=False, chosen=choice: on_change(chosen))
            group.addAction(action)
        button.setMenu(menu)
        return button

    def show_status(self, site_name: str, live: int, visible: int, page: int, pages: int) -> None:
        self._site_title.setText(site_name or self._translator.t("no_site"))
        self._live_badge.setText(self._translator.t("live", live=live, total=visible))
        self._page_label.setText(self._translator.t("page", current=page + 1, total=pages))

    def show_resources(self, usage: ProcessUsage | None, players: int) -> None:
        """How much of the whole PC the wall uses; the detail waits in the tooltip."""
        unknown = self._translator.t("usage_unknown")
        cpu = unknown
        if usage is not None and usage.cpu_percent is not None:
            share = usage.machine_percent if usage.machine_percent is not None else usage.cpu_percent
            cpu = f"{share:.0f}%"
        memory = (f"{usage.memory_mebibytes:.0f} MB"
                  if usage is not None and usage.memory_mebibytes is not None else unknown)
        self._resource_status.setText(self._translator.t("usage", cpu=cpu, memory=memory))
        if usage is not None and usage.cores_used is not None:
            tip = self._translator.t("usage_tip", players=players, cores=usage.cores_used,
                                     total=usage.core_count)
        else:
            tip = self._translator.t("players_tip", players=players)
        self._resource_status.setToolTip(tip)

    def set_filled(self, filled: bool) -> None:
        self._fill_button.setToolTip(self._translator.t("restore_window" if filled else "maximize"))

    def set_sync(self, enabled: bool) -> None:
        self._sync_button.setChecked(enabled)
        self._sync_button.setToolTip(self._translator.t(
            "disable_strict_sync" if enabled else "enable_strict_sync"))

    def set_ai_available(self, available: bool) -> None:
        self._ai_button.setVisible(available)

    @property
    def ai_panel_wanted(self) -> bool:
        return self._ai_button.isChecked()

    def show_ai_connection(self, connected: int, total: int) -> None:
        """The AI button's dot is green only when every connection of the site is up."""
        state = "connected" if total and connected == total else "partial" if connected else "down"
        if self._ai_button.property("feed") != state:   # repolishing re-applies the style sheet
            self._ai_button.setProperty("feed", state)
            self._ai_button.style().unpolish(self._ai_button)
            self._ai_button.style().polish(self._ai_button)
        self._ai_button.setToolTip(self._translator.t("ai_connections_tip", connected=connected,
                                                      total=total))
