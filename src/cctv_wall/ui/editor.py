"""Settings dialog: sites and cameras.

There is no draft: every action is written to the workspace at once through
`on_change`. The wall reconnects once when the dialog closes, not on every edit.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QMessageBox, QPushButton, QSplitter, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from cctv_wall.event_log import logger
from cctv_wall.i18n import Translator
from cctv_wall.models import Camera, Site, Workspace
from cctv_wall.ui.ai_feed_editor import edit_ai_feeds
from cctv_wall.ui.flat_tree import FlatTree

CAMERA_FIELDS = ("name", "url", "user", "password")
FIELD_LABEL_KEYS = {"name": "name", "url": "direct_url", "user": "username", "password": "password"}
ROW_HEIGHT = 38


class WorkspaceEditor(QDialog):
    def __init__(self, parent: QWidget, workspace: Workspace,
                 on_change: Callable[[Workspace], None], translator: Translator,
                 initial_site_name: str | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._workspace = workspace
        self._on_change = on_change
        self._site_index: int | None = None
        self._camera_index: int | None = None   # None with a site selected = a new camera
        self._fields: dict[str, QLineEdit] = {}
        self.setWindowTitle(translator.t("settings_title"))
        self.resize(900, 560)
        self._build_ui()
        self._reload_tree()
        names = workspace.site_names
        if initial_site_name in names:
            self._select(names.index(initial_site_name))
        elif names:
            self._select(0)
        self._refresh_buttons()

    # ---- layout -------------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        splitter = QSplitter()
        self._tree = FlatTree()
        self._tree.itemSelectionChanged.connect(self._on_tree_select)
        self._tree.itemChanged.connect(self._apply_inline_name)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_tree_menu)
        splitter.addWidget(self._tree)
        splitter.addWidget(self._camera_panel())
        splitter.setSizes([320, 580])
        layout.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        close = QPushButton(self._translator.t("close"))
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        layout.addLayout(bottom)

    def _camera_panel(self) -> QWidget:
        panel = QWidget()
        box = QVBoxLayout(panel)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for key in CAMERA_FIELDS:
            field = QLineEdit()
            if key == "password":
                field.setEchoMode(QLineEdit.EchoMode.Password)
            if key == "url":
                field.setPlaceholderText("rtsp://192.168.1.10:554/stream1")
            field.returnPressed.connect(self._save_camera)
            self._fields[key] = field
            form.addRow(self._translator.t(FIELD_LABEL_KEYS[key]), field)
        box.addLayout(form)
        self._error = QLabel()
        self._error.setProperty("invalid", True)
        self._error.setWordWrap(True)
        box.addWidget(self._error)
        buttons = QHBoxLayout()
        self._new_button = QPushButton(self._translator.t("add_camera"))
        self._new_button.clicked.connect(self._new_camera)
        self._save_button = QPushButton(self._translator.t("save_camera"))
        self._save_button.clicked.connect(self._save_camera)
        self._delete_button = QPushButton(self._translator.t("delete"))
        self._delete_button.clicked.connect(self._delete_selected)
        for button in (self._new_button, self._save_button, self._delete_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        box.addLayout(buttons)
        box.addStretch(1)
        return panel

    # ---- tree ---------------------------------------------------------------------------

    def _reload_tree(self) -> None:
        collapsed = self._tree.collapsed_top_level_texts()
        self._tree.blockSignals(True)
        self._tree.clear()
        for site_index, site in enumerate(self._workspace.sites):
            site_item = self._tree_item(site.name, (site_index, None))
            self._tree.addTopLevelItem(site_item)
            for camera_index, camera in enumerate(site.cameras):
                site_item.addChild(self._tree_item(camera.label, (site_index, camera_index)))
            site_item.setExpanded(site.name not in collapsed)
        self._tree.blockSignals(False)

    @staticmethod
    def _tree_item(text: str, reference: tuple[int, int | None]) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setSizeHint(0, QSize(0, ROW_HEIGHT))
        item.setData(0, Qt.ItemDataRole.UserRole, reference)
        return item

    def _select(self, site_index: int, camera_index: int | None = None) -> None:
        item = self._tree.topLevelItem(site_index)
        if item is not None and camera_index is not None:
            item = item.child(camera_index)
        if item is not None:
            self._tree.setCurrentItem(item)

    def _on_tree_select(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        self._site_index, self._camera_index = item.data(0, Qt.ItemDataRole.UserRole)
        if self._camera_index is None:
            self._fill_form(None)
        else:
            self._fill_form(self._site.cameras[self._camera_index])
        self._refresh_buttons()

    def _show_tree_menu(self, position) -> None:
        item = self._tree.itemAt(position)
        if item is not None:
            self._tree.setCurrentItem(item)
        t = self._translator.t
        menu = QMenu(self)
        menu.setMinimumWidth(220)
        if item is not None:
            if self._camera_index is None:
                menu.addAction(t("add_camera"), self._new_camera)
                menu.addAction(t("rename_site"), lambda: self._tree.editItem(item, 0))
                menu.addAction(t("ai_feeds_action"), self._edit_ai_feeds)
            for label, offset in ((t("move_up"), -1), (t("move_down"), 1)):
                action = menu.addAction(label, lambda step=offset: self._move_selected(step))
                action.setEnabled(self._can_move(offset))
            menu.addAction(t("delete"), self._delete_selected)
            menu.addSeparator()
        menu.addAction(t("add_site"), self._add_site)
        menu.exec(self._tree.viewport().mapToGlobal(position))

    # ---- saving -------------------------------------------------------------------------

    @property
    def _site(self) -> Site:
        assert self._site_index is not None
        return self._workspace.sites[self._site_index]

    def _commit(self, build: Callable[[], Workspace],
                select: tuple[int, int | None] | None = None) -> bool:
        """Validate, store and announce one change; a rejected change leaves everything as it was."""
        try:
            workspace = build()
        except ValueError as error:
            logger().warning("settings change refused: %s", error)
            self._error.setText(str(error))
            return False
        self._error.clear()
        self._workspace = workspace
        self._on_change(workspace)
        self._reload_tree()
        if select is not None:
            self._select(*select)
        self._refresh_buttons()
        return True

    def _with_site(self, index: int, site: Site) -> Workspace:
        sites = list(self._workspace.sites)
        sites[index] = site
        return self._workspace.with_sites(sites)

    def _with_cameras(self, site_index: int, cameras: list[Camera]) -> Workspace:
        site = self._workspace.sites[site_index]
        return self._with_site(site_index, site.with_cameras(cameras))

    def _add_site(self) -> None:
        name = self._workspace.unique_site_name(self._translator.t("untitled_site"))
        index = len(self._workspace.sites)
        if self._commit(lambda: self._workspace.with_sites((*self._workspace.sites, Site(name))),
                        (index, None)):
            self._tree.editItem(self._tree.topLevelItem(index), 0)

    def _new_camera(self) -> None:
        """Clear the form for a new camera on the selected site; Save adds it."""
        if self._site_index is None:
            return
        self._select(self._site_index)
        self._camera_index = None
        self._fill_form(None)
        self._fields["name"].setFocus()
        self._refresh_buttons()

    def _save_camera(self) -> None:
        if self._site_index is None:
            return
        try:
            camera = Camera.from_raw({key: field.text() for key, field in self._fields.items()})
        except ValueError as error:
            self._error.setText(str(error))
            return
        site_index = self._site_index
        cameras = list(self._site.cameras)
        if self._camera_index is None:
            cameras.append(camera)
            index = len(cameras) - 1
        else:
            cameras[self._camera_index] = camera
            index = self._camera_index
        if self._commit(lambda: self._with_cameras(site_index, cameras), (site_index, index)):
            self._fill_form(camera)   # shows the URL with any pasted credentials moved out

    def _delete_selected(self) -> None:
        if self._site_index is None:
            return
        site_index = self._site_index
        if self._camera_index is None:
            answer = QMessageBox.question(self, self._translator.t("delete_site"),
                                          self._translator.t("delete_site_confirm", name=self._site.name))
            if answer != QMessageBox.StandardButton.Yes:
                return
            remaining = self._workspace.with_sites(
                s for i, s in enumerate(self._workspace.sites) if i != site_index)
            active = remaining.active_site
            self._site_index = self._camera_index = None
            self._fill_form(None)
            self._commit(lambda: remaining.with_last_site(active.name if active else ""))
            return
        camera_index = self._camera_index
        cameras = [c for i, c in enumerate(self._site.cameras) if i != camera_index]
        self._commit(lambda: self._with_cameras(site_index, cameras), (site_index, None))

    def _apply_inline_name(self, item: QTreeWidgetItem, _column: int) -> None:
        """Double-click rename is saved at once; an empty or taken site name is not applied."""
        site_index, camera_index = item.data(0, Qt.ItemDataRole.UserRole)
        name = item.text(0).strip()
        site = self._workspace.sites[site_index]
        if camera_index is None:
            if name == site.name:
                return
            if not name or self._workspace.site(name) is not None:
                self._reload_tree()
                self._select(site_index)
                return
            renamed = self._with_site(site_index, replace(site, name=name))
            if self._workspace.last_site == site.name:
                renamed = renamed.with_last_site(name)   # keep watching the same place
            self._commit(lambda: renamed, (site_index, None))
            return
        cameras = list(site.cameras)
        cameras[camera_index] = Camera.from_raw({**cameras[camera_index].as_dict(), "name": name})
        self._commit(lambda: self._with_cameras(site_index, cameras), (site_index, camera_index))

    def _edit_ai_feeds(self) -> None:
        if self._site_index is None:
            return
        site, site_index = self._site, self._site_index
        feeds = edit_ai_feeds(self, self._translator, site.name, site.cameras, site.ai_feeds)
        if feeds is not None:
            self._commit(lambda: self._with_site(site_index, replace(site, ai_feeds=feeds)),
                         (site_index, None))

    def _can_move(self, offset: int) -> bool:
        if self._site_index is None:
            return False
        if self._camera_index is None:
            return 0 <= self._site_index + offset < len(self._workspace.sites)
        return 0 <= self._camera_index + offset < len(self._site.cameras)

    def _move_selected(self, offset: int) -> None:
        """排序就是清單順序：地點順序決定側欄排列，攝影機順序決定影像牆格子順序。"""
        if not self._can_move(offset):
            return
        site_index = self._site_index
        if self._camera_index is None:
            sites = list(self._workspace.sites)
            target = site_index + offset
            sites[site_index], sites[target] = sites[target], sites[site_index]
            self._commit(lambda: self._workspace.with_sites(sites), (target, None))
            return
        cameras = list(self._site.cameras)
        index, target = self._camera_index, self._camera_index + offset
        cameras[index], cameras[target] = cameras[target], cameras[index]
        self._commit(lambda: self._with_cameras(site_index, cameras), (site_index, target))

    # ---- form ---------------------------------------------------------------------------

    def _fill_form(self, camera: Camera | None) -> None:
        self._error.clear()
        for key, field in self._fields.items():
            field.setText(getattr(camera, key) if camera is not None else "")

    def _refresh_buttons(self) -> None:
        has_site = self._site_index is not None
        for widget in (self._new_button, self._save_button, self._delete_button,
                       *self._fields.values()):
            widget.setEnabled(has_site)


def open_editor(parent: QWidget, workspace: Workspace,
                on_change: Callable[[Workspace], None], translator: Translator,
                initial_site_name: str | None = None) -> None:
    editor = WorkspaceEditor(parent, workspace, on_change, translator, initial_site_name)
    editor.setModal(True)
    editor.exec()
