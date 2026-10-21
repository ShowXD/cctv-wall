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

    def __init__(self, on_reorder: Callable[[], None],
                 on_reselect: Callable[[QTreeWidgetItem], None],
                 on_pick: Callable[[QTreeWidgetItem], None]) -> None:
        super().__init__()
        self._on_reorder = on_reorder
        self._on_reselect = on_reselect
        self._on_pick = on_pick
        self._pressed_current: QTreeWidgetItem | None = None
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDragDropOverwriteMode(False)
        # Extended only so that several picked cameras can show as selected at once; picking
        # itself is handled in mousePressEvent, and a plain click still selects a single row.
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        picking = event.modifiers() & (Qt.KeyboardModifier.ControlModifier
                                       | Qt.KeyboardModifier.ShiftModifier)
        if (picking and item is not None and item.parent() is not None
                and event.button() == Qt.MouseButton.LeftButton):
            self._on_pick(item)   # Ctrl/Shift+click a camera: add it to, or drop it from, the pick
            event.accept()
            return
        self._pressed_current = item if item is not None and item is self.currentItem() else None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        # currentItemChanged stays silent when the selected row is clicked again, so that
        # click — "put the enlarged camera back" — is reported here. Acting on release, and
        # only on the same row, keeps a drag that starts on the selected row from firing it.
        super().mouseReleaseEvent(event)
        item = self.itemAt(event.position().toPoint())
        if (item is not None and item is self._pressed_current
                and event.button() == Qt.MouseButton.LeftButton):
            self._on_reselect(item)
        self._pressed_current = None

    def dropEvent(self, event) -> None:
        # A camera dropped onto another site would silently move it between locations;
        # that belongs in the editor, where it can be reviewed before saving. Several picked
        # cameras are a viewing choice, not something to drag.
        if (len(self.selectedItems()) > 1
                or not self._is_same_level_reorder(event.position().toPoint())):
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
                 on_camera_selected: Callable[[str, Camera], None],
                 on_reorder: Callable[[Workspace], None],
                 on_camera_action: Callable[[str, str, int], None],
                 on_cameras_picked: Callable[[tuple[tuple[str, int], ...]], None]) -> None:
        super().__init__()
        self.setObjectName("siteNavigation")
        self.setMinimumWidth(160)
        self._on_site_selected = on_site_selected
        self._on_camera_action = on_camera_action
        self._on_cameras_picked = on_cameras_picked
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
        self._sites = _SiteTree(self._apply_reorder, lambda item: self._item_changed(item, item),
                                self._pick)
        self._sites.setObjectName("siteList")
        self._sites.currentItemChanged.connect(self._item_changed)
        self._sites.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._sites.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._sites, 1)
        # Two plain entries instead of one "manage" button: someone looking for the AI
        # connections should not have to guess that they live behind a right-click.
        settings = QPushButton(self._translator.t("manage"))
        settings.setObjectName("settingsButton")
        settings.clicked.connect(on_settings_requested)
        layout.addWidget(settings)
        self._ai_button = QPushButton(self._translator.t("ai_feeds_button"))
        self._ai_button.setObjectName("settingsButton")
        self._ai_button.clicked.connect(lambda: self._on_site_action("ai_feeds", ""))
        layout.addWidget(self._ai_button)

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
        self._ai_button.setEnabled(bool(workspace.sites))

    def _item_changed(self, current: QTreeWidgetItem | None,
                      _previous: QTreeWidgetItem | None) -> None:
        if current is None:
            return
        site_name, camera_index = _reference(current)
        if camera_index is None:
            self._on_site_selected(site_name)
            return
        camera = self._camera(site_name, camera_index)
        if camera is not None:
            self._on_camera_selected(site_name, camera)

    def _pick(self, item: QTreeWidgetItem) -> None:
        """Toggle one camera in the set to watch; the set may span several sites."""
        selected = self._sites.selectedItems()
        for other in selected:
            if other.parent() is None:
                other.setSelected(False)   # a site row is a place, not a camera to watch
        item.setSelected(item not in selected)
        picked = sorted(self._sites.selectedItems(),
                        key=lambda i: (self._sites.indexOfTopLevelItem(i.parent()), _reference(i)[1]))
        self._on_cameras_picked(tuple(_reference(i) for i in picked))

    def clear_picks(self) -> None:
        """The wall shows the whole site again, so its row is the one selected; the next
        Ctrl+click starts a new pick."""
        current = self._sites.currentItem()
        site_row = current.parent() or current if current is not None else None
        blocked = self._sites.blockSignals(True)
        self._sites.clearSelection()
        if site_row is not None:
            self._sites.setCurrentItem(site_row)
        self._sites.blockSignals(blocked)

    def _camera(self, site_name: str, index: int) -> Camera | None:
        site = self._workspace.site(site_name)
        return site.cameras[index] if site and index < len(site.cameras) else None

    def _apply_reorder(self) -> None:
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
        # Parented to the top-level window: libvlc makes this panel a native child, and a
        # popup with a native child as its transient parent triggers a Qt warning.
        menu = QMenu(self.window())
        menu.setMinimumWidth(200)
        # A click already watches a site or enlarges a camera, so the menu only edits.
        if camera_index is None:
            self._add_action(menu, self._translator.t("add_camera_action"), "add_camera", site_name)
            self._add_action(menu, self._translator.t("duplicate_site"), "duplicate", site_name)
            self._add_action(menu, self._translator.t("rename"), "rename", site_name)
            self._add_action(menu, self._translator.t("ai_feeds_action"), "ai_feeds", site_name)
            menu.addSeparator()
            self._add_action(menu, self._translator.t("delete_site_action"), "delete", site_name)
        else:
            for text, action in ((self._translator.t("edit_camera"), "edit_camera"),
                                 (self._translator.t("delete_camera"), "delete_camera")):
                item = menu.addAction(text)
                item.triggered.connect(lambda _checked=False, chosen=action:
                                       self._on_camera_action(chosen, site_name, camera_index))
        menu.exec(self._sites.viewport().mapToGlobal(position))
        menu.deleteLater()

    def _add_action(self, menu: QMenu, label: str, action: str, site_name: str) -> None:
        item = menu.addAction(label)
        item.triggered.connect(lambda _checked=False: self._on_site_action(action, site_name))
