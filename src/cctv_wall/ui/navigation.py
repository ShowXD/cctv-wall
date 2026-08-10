"""Site navigation view.  It presents navigation only and delegates all decisions upward."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMenu, QPushButton, QVBoxLayout, QWidget)

from cctv_wall.i18n import Translator
from cctv_wall.models import Workspace


class SiteNavigation(QFrame):
    """Persistent, readable site selector with an explicit configuration entry point."""

    def __init__(self, on_site_selected: Callable[[str], None],
                 on_settings_requested: Callable[[], None],
                 on_site_action: Callable[[str, str], None], translator: Translator) -> None:
        super().__init__()
        self.setObjectName("siteNavigation")
        self.setMinimumWidth(196)
        self.setMaximumWidth(260)
        self._on_site_selected = on_site_selected
        self._translator = translator
        self._on_site_action = on_site_action
        self._build_ui(on_settings_requested)

    def _build_ui(self, on_settings_requested: Callable[[], None]) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(12)
        product = QLabel("CCTV  WALL")
        product.setObjectName("productName")
        layout.addWidget(product)
        subtitle = QLabel(self._translator.t("product_subtitle"))
        subtitle.setObjectName("productSubtitle")
        layout.addWidget(subtitle)
        layout.addSpacing(18)
        section = QHBoxLayout()
        label = QLabel(self._translator.t("sites"))
        label.setObjectName("navigationLabel")
        section.addWidget(label)
        section.addStretch(1)
        self._count = QLabel("0")
        self._count.setObjectName("countBadge")
        self._count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        section.addWidget(self._count)
        layout.addLayout(section)
        self._sites = QListWidget()
        self._sites.setObjectName("siteList")
        self._sites.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._sites.currentItemChanged.connect(self._site_changed)
        self._sites.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._sites.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._sites, 1)
        layout.addStretch(1)
        settings = QPushButton(self._translator.t("manage"))
        settings.setObjectName("settingsButton")
        settings.clicked.connect(on_settings_requested)
        layout.addWidget(settings)

    def set_workspace(self, workspace: Workspace) -> None:
        current = workspace.active_site.name if workspace.active_site else ""
        self._sites.blockSignals(True)
        self._sites.clear()
        for site in workspace.sites:
            item = QListWidgetItem(site.name)
            item.setData(Qt.ItemDataRole.UserRole, site.name)
            count = len(site.cameras)
            item.setToolTip(self._translator.t("camera" if count == 1 else "cameras",
                                               count=count))
            self._sites.addItem(item)
            if site.name == current:
                self._sites.setCurrentItem(item)
        self._sites.blockSignals(False)
        self._count.setText(str(len(workspace.sites)))

    def _site_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is not None:
            self._on_site_selected(str(current.data(Qt.ItemDataRole.UserRole)))

    def _show_context_menu(self, position) -> None:
        item = self._sites.itemAt(position)
        if item is None:
            return
        site_name = str(item.data(Qt.ItemDataRole.UserRole))
        menu = QMenu(self)
        self._add_action(menu, self._translator.t("watch_site"), "watch", site_name)
        menu.addSeparator()
        self._add_action(menu, self._translator.t("add_camera_action"), "add_camera", site_name)
        self._add_action(menu, self._translator.t("duplicate_site"), "duplicate", site_name)
        self._add_action(menu, self._translator.t("rename"), "rename", site_name)
        menu.addSeparator()
        self._add_action(menu, self._translator.t("delete_site_action"), "delete", site_name)
        menu.exec(self._sites.viewport().mapToGlobal(position))

    def _add_action(self, menu: QMenu, label: str, action: str, site_name: str) -> None:
        item = menu.addAction(label)
        item.triggered.connect(lambda _checked=False: self._on_site_action(action, site_name))
