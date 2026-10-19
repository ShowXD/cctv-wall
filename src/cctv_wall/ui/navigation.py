"""Site navigation view.  It presents navigation only and delegates all decisions upward."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLabel, QMenu,
                               QPushButton, QTreeWidgetItem, QVBoxLayout)

from cctv_wall.i18n import Translator
from cctv_wall.models import Camera, Site, Workspace
from cctv_wall.ui.flat_tree import FlatTree

# (site name, camera index) — the camera index is None on a site row.
ItemReference = tuple[str, "int | None"]


def _reference(item: QTreeWidgetItem) -> ItemReference:
    return item.data(0, Qt.ItemDataRole.UserRole)


class _SiteTree(FlatTree):
    """Sites with their cameras, reorderable by drag inside one level only."""

    def __init__(self, on_reorder: Callable[[], None]) -> None:
        super().__init__()
        self._on_reorder = on_reorder
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDragDropOverwriteMode(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def dropEvent(self, event) -> None:
        # A camera dropped onto another site would silently move it between locations;
        # that belongs in the editor, where it can be reviewed before saving.
        if not self._is_same_level_reorder(event.position().toPoint()):
            event.ignore()
            return
        super().dropEvent(event)
        self._on_reorder()

    def _is_same_level_reorder(self, position) -> bool:
        source = self.currentItem()
        if source is None:
            return False
        if self.dropIndicatorPosition() == QAbstractItemView.DropIndicatorPosition.OnItem:
            return False
        target = self.itemAt(position)
        if target is None:
            return source.parent() is None
        return source.parent() is target.parent()


class SiteNavigation(QFrame):
    """Persistent, readable site selector with an explicit configuration entry point."""

    def __init__(self, on_site_selected: Callable[[str], None],
                 on_settings_requested: Callable[[], None],
                 on_site_action: Callable[[str, str], None], translator: Translator,
                 on_camera_selected: Callable[[str, Camera], None] | None = None,
                 on_reorder: Callable[[Workspace], None] | None = None) -> None:
        super().__init__()
        self.setObjectName("siteNavigation")
        self.setMinimumWidth(160)
        self._on_site_selected = on_site_selected
        self._translator = translator
        self._on_site_action = on_site_action
        self._on_camera_selected = on_camera_selected
        self._on_reorder = on_reorder
        self._workspace = Workspace()
        self._build_ui(on_settings_requested)

    def _build_ui(self, on_settings_requested: Callable[[], None]) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(12)
        product = QLabel("CCTV  WALL")
        product.setObjectName("productName")
        layout.addWidget(product)
        layout.addSpacing(6)
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
        self._sites = _SiteTree(self._apply_reorder)
        self._sites.setObjectName("siteList")
        self._sites.currentItemChanged.connect(self._item_changed)
        self._sites.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._sites.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._sites, 1)
        layout.addStretch(1)
        settings = QPushButton(self._translator.t("manage"))
        settings.setObjectName("settingsButton")
        settings.clicked.connect(on_settings_requested)
        layout.addWidget(settings)

    def set_workspace(self, workspace: Workspace) -> None:
        self._workspace = workspace
        current = workspace.active_site.name if workspace.active_site else ""
        collapsed = self._sites.collapsed_top_level_texts()
        self._sites.blockSignals(True)
        self._sites.clear()
        for site in workspace.sites:
            item = QTreeWidgetItem([site.name])
            item.setData(0, Qt.ItemDataRole.UserRole, (site.name, None))
            count = len(site.cameras)
            item.setToolTip(0, self._translator.t("camera" if count == 1 else "cameras",
                                                  count=count))
            self._sites.addTopLevelItem(item)
            for index, camera in enumerate(site.cameras):
                child = QTreeWidgetItem([camera.label])
                child.setData(0, Qt.ItemDataRole.UserRole, (site.name, index))
                child.setToolTip(0, camera.label)
                item.addChild(child)
            item.setExpanded(site.name not in collapsed)
            if site.name == current:
                self._sites.setCurrentItem(item)
        self._sites.blockSignals(False)
        self._count.setText(str(len(workspace.sites)))

    def _item_changed(self, current: QTreeWidgetItem | None,
                      _previous: QTreeWidgetItem | None) -> None:
        if current is None:
            return
        site_name, camera_index = _reference(current)
        if camera_index is None:
            self._on_site_selected(site_name)
            return
        camera = self._camera(site_name, camera_index)
        if camera is not None and self._on_camera_selected is not None:
            self._on_camera_selected(site_name, camera)

    def _camera(self, site_name: str, index: int) -> Camera | None:
        site = self._workspace.site(site_name)
        return site.cameras[index] if site and index < len(site.cameras) else None

    def _apply_reorder(self) -> None:
        if self._on_reorder is not None:
            self._on_reorder(self._reordered_workspace())

    def _reordered_workspace(self) -> Workspace:
        """Read the new order off the tree, keeping every camera's own settings."""
        sites: list[Site] = []
        for index in range(self._sites.topLevelItemCount()):
            item = self._sites.topLevelItem(index)
            site = self._workspace.site(_reference(item)[0])
            if site is None:
                continue
            cameras = [self._camera(*_reference(item.child(row)))
                       for row in range(item.childCount())]
            sites.append(site.with_cameras([c for c in cameras if c is not None]))
        return self._workspace.with_sites(sites)

    def _show_context_menu(self, position) -> None:
        item = self._sites.itemAt(position)
        if item is None:
            return
        self._sites.setCurrentItem(item)
        site_name, camera_index = _reference(item)
        menu = QMenu(self)
        menu.setMinimumWidth(200)
        self._add_action(menu, self._translator.t("watch_site"), "watch", site_name)
        if camera_index is None:
            menu.addSeparator()
            self._add_action(menu, self._translator.t("add_camera_action"), "add_camera", site_name)
            self._add_action(menu, self._translator.t("duplicate_site"), "duplicate", site_name)
            self._add_action(menu, self._translator.t("rename"), "rename", site_name)
            self._add_action(menu, self._translator.t("ai_feeds_action"), "ai_feeds", site_name)
            menu.addSeparator()
            self._add_action(menu, self._translator.t("delete_site_action"), "delete", site_name)
        else:
            self._add_action(menu, self._translator.t("edit_cameras"), "add_camera", site_name)
        menu.exec(self._sites.viewport().mapToGlobal(position))

    def _add_action(self, menu: QMenu, label: str, action: str, site_name: str) -> None:
        item = menu.addAction(label)
        item.triggered.connect(lambda _checked=False: self._on_site_action(action, site_name))
