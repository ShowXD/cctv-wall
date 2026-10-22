"""Site navigation view.  It presents navigation only and delegates all decisions upward."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLabel, QMenu,
                               QPushButton, QTreeWidgetItem, QVBoxLayout)

from cctv_wall.i18n import Translator
from cctv_wall.models import Camera, Workspace
from cctv_wall.ui.flat_tree import FlatTree

# (site name, camera index) — the camera index is None on a site row.
ItemReference = tuple[str, "int | None"]


# Every site in its new place, each with its cameras listed by their present index. Only the
# order travels: the list's copy of the workspace can be older than the window's (the site on
# screen, a stream switched from a tile), and handing the whole copy back would undo those.
Order = tuple[tuple[str, tuple[int, ...]], ...]


def apply_order(workspace: Workspace, order: Order) -> Workspace | None:
    """The workspace in this order with every other setting untouched; None when the order no
    longer fits it."""
    sites = []
    for name, indices in order:
        site = workspace.site(name)
        if site is None or sorted(indices) != list(range(len(site.cameras))):
            return None
        sites.append(site.with_cameras([site.cameras[index] for index in indices]))
    return workspace.with_sites(sites) if len(sites) == len(workspace.sites) else None


def _reference(item: QTreeWidgetItem) -> ItemReference:
    return item.data(0, Qt.ItemDataRole.UserRole)


def _camera_rows(item: QTreeWidgetItem) -> list[QTreeWidgetItem]:
    """The camera itself, or every camera of a site row."""
    if item.parent() is not None:
        return [item]
    return [item.child(index) for index in range(item.childCount())]


class _SiteTree(FlatTree):
    """Sites with their cameras, reorderable by drag inside one level only."""

    def __init__(self, on_reorder: Callable[[], None],
                 on_reselect: Callable[[QTreeWidgetItem], None],
                 on_pick: Callable[[QTreeWidgetItem], None],
                 on_pick_range: Callable[[QTreeWidgetItem, QTreeWidgetItem], None]) -> None:
        super().__init__()
        self._on_reorder = on_reorder
        self._on_reselect = on_reselect
        self._on_pick = on_pick
        self._on_pick_range = on_pick_range
        self._pressed_current: QTreeWidgetItem | None = None
        # Where a Shift+click range starts: the row clicked last, with or without Ctrl.
        self._anchor: QTreeWidgetItem | None = None
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDragDropOverwriteMode(False)
        # Extended only so that several picked cameras can show as selected at once; picking
        # itself is handled in mousePressEvent, and a plain click still selects a single row.
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        modifiers = event.modifiers()
        if item is not None and event.button() == Qt.MouseButton.LeftButton:
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                self._on_pick_range(self._anchor or self.currentItem() or item, item)
                event.accept()
                return
            self._anchor = item
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                self._on_pick(item)
                event.accept()
                return
        self._pressed_current = item if item is not None and item is self.currentItem() else None
        super().mousePressEvent(event)

    def clear(self) -> None:
        self._anchor = None   # its row is about to be deleted
        super().clear()

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
                 on_reorder: Callable[[Order], None],
                 on_camera_action: Callable[[str, str, int], None],
                 on_cameras_picked: Callable[[tuple[tuple[str, int], ...]], None],
                 on_delete: Callable[[tuple[str, ...], tuple[ItemReference, ...]], None]
                 = lambda _sites, _cameras: None) -> None:
        super().__init__()
        self._on_delete = on_delete
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
                                self._pick, self._pick_range)
        self._sites.setObjectName("siteList")
        self._sites.currentItemChanged.connect(self._item_changed)
        self._sites.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._sites.customContextMenuRequested.connect(self._show_context_menu)
        # Bound methods, not lambdas holding self: see ai_feed_editor._CodePicker.
        for keys, action in (("Delete", self._delete_selected), ("Alt+Up", self._move_up),
                             ("Alt+Down", self._move_down)):
            shortcut = QShortcut(QKeySequence(keys), self._sites)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(action)
        layout.addWidget(self._sites, 1)
        # Two plain entries instead of one "manage" button: someone looking for the AI
        # connections should not have to guess that they live behind a right-click.
        settings = QPushButton(self._translator.t("manage"))
        settings.setObjectName("settingsButton")
        settings.clicked.connect(on_settings_requested)
        layout.addWidget(settings)
        self._ai_button = QPushButton(self._translator.t("ai_feeds_button"))
        self._ai_button.setObjectName("settingsButton")
        self._ai_button.clicked.connect(self._edit_ai_feeds)
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
        """Ctrl+click: toggle one camera, or every camera of a site, in the selection; it may
        span several sites. Only selects — the right-click menu plays them together."""
        cameras = _camera_rows(item)
        adding = not all(row.isSelected() for row in cameras)
        for row in self._sites.selectedItems():
            if row.parent() is None:
                row.setSelected(False)   # a site row is a place, not a camera to watch
        for row in cameras:
            row.setSelected(adding)

    def _pick_range(self, anchor: QTreeWidgetItem, item: QTreeWidgetItem) -> None:
        """Shift+click: every camera from the anchor row to this one, in list order. A site row
        brings all its cameras when it is an end of the range or collapsed (its cameras out of
        sight); an expanded one in between adds only its camera rows that lie in the range."""
        rows = [row for index in range(self._sites.topLevelItemCount())
                for site in (self._sites.topLevelItem(index),)
                for row in (site, *(site.child(child) for child in range(site.childCount())))]
        first, last = sorted((rows.index(anchor), rows.index(item)))
        self._sites.clearSelection()
        for row in rows[first:last + 1]:
            whole_site = row in (anchor, item) or not row.isExpanded()
            for camera in _camera_rows(row) if row.parent() is not None or whole_site else ():
                camera.setSelected(True)

    def _selected_cameras(self) -> tuple[ItemReference, ...]:
        picked = sorted((i for i in self._sites.selectedItems() if i.parent() is not None),
                        key=lambda i: (self._sites.indexOfTopLevelItem(i.parent()), _reference(i)[1]))
        return tuple(_reference(i) for i in picked)

    def _targets(self) -> tuple[tuple[str, ...], tuple[ItemReference, ...]]:
        """(sites, cameras) that Del and Alt+arrows act on: the selected cameras, else the
        current row. Ctrl on a site row selects its cameras, so sites go one at a time."""
        cameras = self._selected_cameras()
        current = self._sites.currentItem()
        if cameras or current is None:
            return (), cameras
        site_name, index = _reference(current)
        return ((site_name,), ()) if index is None else ((), ((site_name, index),))

    def _delete_selected(self) -> None:
        sites, cameras = self._targets()
        if sites or cameras:
            self._on_delete(sites, cameras)   # asked to confirm, and saved, by the window

    def _edit_ai_feeds(self) -> None:
        self._on_site_action("ai_feeds", "")   # "" = the site on screen

    def _move_up(self) -> None:
        self._move_selected(-1)

    def _move_down(self) -> None:
        self._move_selected(1)

    def _move_selected(self, step: int) -> None:
        """Alt+Up/Down: a site, or a block of cameras of one site, one row up or down. Saved at
        once like a drag; the moved rows stay selected so the key can be pressed again."""
        sites, cameras = self._targets()
        order = [(site.name, tuple(range(len(site.cameras)))) for site in self._workspace.sites]
        if sites:
            index = self._workspace.site_names.index(sites[0])
            if not 0 <= index + step < len(order):
                return
            order[index], order[index + step] = order[index + step], order[index]
            self._on_reorder(tuple(order))
            self._select_rows({(sites[0], None)})
            return
        if not cameras or len({site_name for site_name, _index in cameras}) != 1:
            return   # cameras only move inside their own site; that belongs in the editor
        site_name = cameras[0][0]
        position = self._workspace.site_names.index(site_name)
        indices = [index for _site_name, index in cameras]
        moved = list(order[position][1])
        if indices[0] + step < 0 or indices[-1] + step >= len(moved):
            return
        # The leading edge swaps first, so the block slides by one without reordering itself.
        for index in reversed(indices) if step > 0 else indices:
            moved[index], moved[index + step] = moved[index + step], moved[index]
        order[position] = (site_name, tuple(moved))
        self._on_reorder(tuple(order))
        self._select_rows({(site_name, index + step) for index in indices})

    def _select_rows(self, references: set[ItemReference]) -> None:
        """Select rows of the rebuilt tree quietly: selecting is not choosing what to watch."""
        blocked = self._sites.blockSignals(True)
        self._sites.clearSelection()
        for index in range(self._sites.topLevelItemCount()):
            site = self._sites.topLevelItem(index)
            for row in (site, *(site.child(child) for child in range(site.childCount()))):
                if tuple(_reference(row)) in references:
                    if row.parent() is None:
                        self._sites.setCurrentItem(row)
                    row.setSelected(True)
        self._sites.blockSignals(blocked)

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
        """Read the dragged order off the tree: each row still carries its original index."""
        self._on_reorder(tuple(
            (_reference(site)[0], tuple(_reference(site.child(row))[1] for row in range(site.childCount())))
            for site in map(self._sites.topLevelItem, range(self._sites.topLevelItemCount()))))

    def _show_context_menu(self, position) -> None:
        item = self._sites.itemAt(position)
        if item is None:
            self._show_list_menu(position)
            return
        selected = self._selected_cameras()
        together = len(selected) > 1 and item.isSelected()
        if not together:
            self._sites.setCurrentItem(item)
        site_name, camera_index = _reference(item)
        # Parented to the top-level window: libvlc makes this panel a native child, and a
        # popup with a native child as its transient parent triggers a Qt warning.
        menu = QMenu(self.window())
        menu.setMinimumWidth(200)
        # A click already watches a site or enlarges a camera, so the menu only edits — or,
        # on a selection of several cameras, plays them together.
        if together:
            play = menu.addAction(self._translator.t("play_together", count=len(selected)))
            play.triggered.connect(lambda _checked=False: self._on_cameras_picked(selected))
        elif camera_index is None:
            self._add_action(menu, self._translator.t("add_camera_action"), "add_camera", site_name)
            self._add_action(menu, self._translator.t("duplicate_site"), "duplicate", site_name)
            self._add_action(menu, self._translator.t("rename"), "rename", site_name)
            self._add_action(menu, self._translator.t("ai_feeds_action"), "ai_feeds", site_name)
            self._add_action(menu, self._translator.t("import_cameras"), "import_cameras", site_name)
            self._add_action(menu, self._translator.t("export_cameras"), "export_cameras", site_name)
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

    def _show_list_menu(self, position) -> None:
        """Below the last row: import into the site on screen (or a new one), or export every site."""
        menu = QMenu(self.window())
        menu.setMinimumWidth(200)
        self._add_action(menu, self._translator.t("import_cameras"), "import_cameras", "")
        self._add_action(menu, self._translator.t("export_all_cameras"), "export_all_cameras", "")
        menu.exec(self._sites.viewport().mapToGlobal(position))
        menu.deleteLater()

    def _add_action(self, menu: QMenu, label: str, action: str, site_name: str) -> None:
        item = menu.addAction(label)
        item.triggered.connect(lambda _checked=False: self._on_site_action(action, site_name))
