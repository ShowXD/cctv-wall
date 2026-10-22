"""Settings dialog: sites and cameras.

Every change is held in a working copy until 套用 (apply) or 確認 (OK, apply and close);
取消, Esc and the title bar discard it all. Changed camera fields are listed before they are
applied. The wall reconnects once when the dialog closes, not on every edit.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable, Sequence

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel,
                               QMenu, QMessageBox, QPushButton, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QTreeWidgetItem, QVBoxLayout, QWidget)

from cctv_wall.event_log import logger
from cctv_wall.i18n import Translator
from cctv_wall.models import Camera, Site, Workspace
from cctv_wall.ui.camera_form import (CAMERA_FIELDS, FIELD_LABEL_KEYS, CameraForm, changed_fields,
                                      edit_camera)
from cctv_wall.ui.flat_tree import FlatTree
from cctv_wall.ui.site_commands import edit_site_ai_feeds

ROW_HEIGHT = 38
MARGIN = 16          # window edge and the gap between the two panes
GROUP_SPACING = 8    # between buttons of one group
PASSWORD_MASK = "●●●●"

# (site index, camera index) — the camera index is None on a site row.
Reference = tuple[int, "int | None"]


class WorkspaceEditor(QDialog):
    def __init__(self, parent: QWidget, workspace: Workspace,
                 on_change: Callable[[Workspace], None], translator: Translator,
                 initial_site_name: str | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._workspace = workspace     # the working copy
        self._applied = workspace       # what the rest of the app has
        self._on_change = on_change
        # The one camera whose fields are in the form; None when a site or several rows are selected.
        self._site_index: int | None = None
        self._camera_index: int | None = None
        # id(original camera) -> (that camera, edited fields). Keyed by identity, so a draft
        # follows its camera when cameras are moved; the tuple keeps the id from being reused.
        self._drafts: dict[int, tuple[Camera, dict[str, str]]] = {}
        self.setWindowTitle(translator.t("settings_title"))
        self.resize(900, 560)
        self._build_ui()
        self._reload_tree()
        names = workspace.site_names
        if initial_site_name in names:
            self._select([(names.index(initial_site_name), None)])
        elif names:
            self._select([(0, None)])

    # ---- layout -------------------------------------------------------------------------

    def _build_ui(self) -> None:
        # One margin around and between the two panes; tighter spacing only inside a group
        # of related buttons, a wider gap between groups.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        layout.setSpacing(MARGIN)
        body = QHBoxLayout()
        body.setSpacing(MARGIN)
        self._tree = FlatTree()
        # Shift+click selects a range and Ctrl+click toggles one row, like a file list.
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemChanged.connect(self._apply_inline_name)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_tree_menu)
        # An empty list has nothing to right-click on, so it offers the first site itself.
        self._add_site_button = QPushButton(self._translator.t("add_site"))
        self._add_site_button.clicked.connect(self._add_site)
        QVBoxLayout(self._tree.viewport()).addWidget(self._add_site_button, 0,
                                                     Qt.AlignmentFlag.AlignCenter)
        for keys, action in ((QKeySequence.StandardKey.Delete, self._delete_selected),
                             ("Alt+Up", lambda: self._move_selected(-1)),
                             ("Alt+Down", lambda: self._move_selected(1)),
                             ("Ctrl+N", self._new_camera)):
            shortcut = QShortcut(QKeySequence(keys), self._tree)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(action)
        sites_column = QVBoxLayout()
        sites_column.setSpacing(GROUP_SPACING)
        sites_column.addWidget(QLabel(self._translator.t("site_list")))
        sites_column.addWidget(self._tree, 1)
        hint = QLabel(self._translator.t("editor_hint"))
        hint.setObjectName("formHelp")
        hint.setWordWrap(True)
        sites_column.addWidget(hint)
        body.addLayout(sites_column, 1)

        self._heading = QLabel()
        self._pages = QStackedWidget()
        self._form = CameraForm(self._translator)
        self._form.submitted.connect(self._apply)
        # Tab walks the fields; Up/Down walk the cameras, the cursor staying in the same field.
        for key, step in (("Up", -1), ("Down", 1)):
            shortcut = QShortcut(QKeySequence(key), self._form)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda chosen=step: self._step_camera(chosen))
        form_page = QWidget()
        form_box = QVBoxLayout(form_page)
        form_box.setContentsMargins(0, 0, 0, 0)
        form_box.addWidget(self._form)
        form_box.addStretch(1)
        self._pages.addWidget(form_page)
        self._site_table = QTableWidget(0, len(CAMERA_FIELDS))
        self._site_table.setHorizontalHeaderLabels(
            [self._translator.t(FIELD_LABEL_KEYS[key]) for key in CAMERA_FIELDS])
        self._site_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._site_table.horizontalHeader().setStretchLastSection(True)
        self._site_table.verticalHeader().hide()
        self._site_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._site_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._site_table.cellDoubleClicked.connect(self._open_listed_camera)
        self._pages.addWidget(self._site_table)
        self._selection_note = QLabel()
        self._selection_note.setObjectName("formHelp")
        self._selection_note.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._selection_note.setWordWrap(True)
        self._pages.addWidget(self._selection_note)
        detail_column = QVBoxLayout()
        detail_column.setSpacing(GROUP_SPACING)
        # Its own heading keeps the details level with the site list.
        detail_column.addWidget(self._heading)
        detail_column.addWidget(self._pages, 1)
        body.addLayout(detail_column, 2)
        layout.addLayout(body, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(GROUP_SPACING)
        bottom.addStretch(1)
        for text, action in ((self._translator.t("confirm"), self._confirm),
                             (self._translator.t("apply"), self._apply),
                             (self._translator.t("cancel"), self.reject)):
            button = QPushButton(text)
            # Enter in a field already applies; a default button would act a second time.
            button.setAutoDefault(False)
            button.clicked.connect(action)
            bottom.addWidget(button)
        layout.addLayout(bottom)

    # ---- tree ---------------------------------------------------------------------------

    def _reload_tree(self) -> None:
        collapsed = self._tree.collapsed_top_level_texts()
        self._tree.blockSignals(True)
        self._tree.clear()
        for site_index, site in enumerate(self._workspace.sites):
            site_item = self._tree_item(site.name, (site_index, None))
            self._tree.addTopLevelItem(site_item)
            for camera_index, camera in enumerate(site.cameras):
                item = self._tree_item(camera.label, (site_index, camera_index))
                if id(camera) in self._drafts:
                    self._mark_draft(item, True)
                site_item.addChild(item)
            site_item.setExpanded(site.name not in collapsed)
        self._tree.blockSignals(False)
        self._add_site_button.setVisible(not self._workspace.sites)

    @staticmethod
    def _tree_item(text: str, reference: Reference) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setSizeHint(0, QSize(0, ROW_HEIGHT))
        item.setData(0, Qt.ItemDataRole.UserRole, reference)
        return item

    def _item(self, reference: Reference) -> QTreeWidgetItem | None:
        site_index, camera_index = reference
        item = self._tree.topLevelItem(site_index)
        if item is not None and camera_index is not None:
            item = item.child(camera_index)
        return item

    def _select(self, references: Sequence[Reference]) -> None:
        items = [item for item in map(self._item, references) if item is not None]
        if not items:
            self._on_selection_changed()
            return
        blocked = self._tree.blockSignals(True)
        self._tree.clearSelection()
        self._tree.setCurrentItem(items[0])
        for item in items:
            item.setSelected(True)
        self._tree.blockSignals(blocked)
        self._on_selection_changed()

    def _selected(self) -> list[Reference]:
        """In list order, which is the order a moved block keeps."""
        references = [item.data(0, Qt.ItemDataRole.UserRole) for item in self._tree.selectedItems()]
        return sorted(references, key=lambda ref: (ref[0], -1 if ref[1] is None else ref[1]))

    def _on_selection_changed(self) -> None:
        self._stash_form()
        selected = self._selected()
        self._site_index = self._camera_index = None
        if len(selected) == 1 and selected[0][1] is not None:
            self._site_index, self._camera_index = selected[0]
            camera = self._workspace.sites[self._site_index].cameras[self._camera_index]
            draft = self._drafts.get(id(camera))
            self._form.set_fields(draft[1] if draft else
                                  {key: getattr(camera, key) for key in CAMERA_FIELDS})
            self._heading.setText(self._translator.t("camera_details"))
            self._pages.setCurrentIndex(0)
        elif len(selected) == 1:
            self._show_site(selected[0][0])
        else:
            self._heading.setText(self._translator.t("selection"))
            self._selection_note.setText(self._translator.t("selected_items", count=len(selected))
                                         if selected else "")
            self._pages.setCurrentIndex(2)

    def _show_site(self, site_index: int) -> None:
        """A site's own row lists its cameras; editing happens on a camera's row."""
        site = self._workspace.sites[site_index]
        self._heading.setText(self._translator.t("site_cameras", site=site.name,
                                                 count=len(site.cameras)))
        self._site_table.setRowCount(len(site.cameras))
        for row, camera in enumerate(site.cameras):
            draft = self._drafts.get(id(camera))
            values = draft[1] if draft else {key: getattr(camera, key) for key in CAMERA_FIELDS}
            for column, key in enumerate(CAMERA_FIELDS):
                text = values[key].strip()
                if key == "password" and text:
                    text = PASSWORD_MASK   # the list is for checking, not for reading secrets
                self._site_table.setItem(row, column, QTableWidgetItem(text))
        self._site_table.setProperty("site_index", site_index)
        self._pages.setCurrentIndex(1)

    def _open_listed_camera(self, row: int, _column: int) -> None:
        site_index = self._site_table.property("site_index")
        self._tree.topLevelItem(site_index).setExpanded(True)
        self._select([(site_index, row)])

    def _step_camera(self, step: int) -> None:
        """Next or previous camera row in the list, passing over site rows."""
        item = self._tree.currentItem()
        while item is not None:
            item = self._tree.itemBelow(item) if step > 0 else self._tree.itemAbove(item)
            if item is not None and item.parent() is not None:
                self._select([item.data(0, Qt.ItemDataRole.UserRole)])
                return

    def _selected_camera(self) -> Camera | None:
        if self._site_index is None or self._camera_index is None:
            return None
        if not 0 <= self._site_index < len(self._workspace.sites):
            return None
        cameras = self._workspace.sites[self._site_index].cameras
        return cameras[self._camera_index] if 0 <= self._camera_index < len(cameras) else None

    def _stash_form(self) -> None:
        """Keep what was typed for the camera being left; unchanged fields drop the draft."""
        camera = self._selected_camera()
        if camera is None:
            return
        fields = self._form.fields()
        if changed_fields(camera, fields):
            self._drafts[id(camera)] = (camera, fields)
        else:
            self._drafts.pop(id(camera), None)
        item = self._item((self._site_index, self._camera_index))
        if item is not None:
            self._mark_draft(item, id(camera) in self._drafts)

    def _mark_draft(self, item: QTreeWidgetItem, unsaved: bool) -> None:
        # Any data change emits itemChanged, which would otherwise be read as an inline rename.
        blocked = self._tree.blockSignals(True)
        font = item.font(0)
        font.setItalic(unsaved)
        item.setFont(0, font)
        item.setToolTip(0, self._translator.t("unsaved_camera") if unsaved else "")
        self._tree.blockSignals(blocked)

    def _show_tree_menu(self, position) -> None:
        item = self._tree.itemAt(position)
        if item is not None and not item.isSelected():
            self._select([item.data(0, Qt.ItemDataRole.UserRole)])
        selected = self._selected()
        t = self._translator.t
        menu = QMenu(self)
        menu.setMinimumWidth(220)
        if item is not None:
            if len(selected) == 1 and selected[0][1] is None:
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

    # ---- changes to the working copy ------------------------------------------------------

    def _commit(self, build: Callable[[], Workspace], select: Sequence[Reference] = ()) -> bool:
        """Change the working copy; a rejected change leaves everything as it was."""
        self._stash_form()
        try:
            workspace = build()
        except ValueError as error:
            logger().warning("settings change refused: %s", error)
            self._form.show_error(str(error))
            return False
        self._form.show_error("")
        self._workspace = workspace
        # Drafts of cameras that no longer exist (deleted, or replaced by a rename) go too.
        alive = {id(camera) for site in workspace.sites for camera in site.cameras}
        self._drafts = {key: draft for key, draft in self._drafts.items() if key in alive}
        # The indices may point elsewhere in the new workspace: nothing to stash on reselect.
        self._site_index = self._camera_index = None
        self._reload_tree()
        self._select(select)
        return True

    def _with_site(self, index: int, site: Site) -> Workspace:
        return self._workspace.with_site(self._workspace.sites[index].name, site)

    def _with_cameras(self, site_index: int, cameras: Sequence[Camera]) -> Workspace:
        site = self._workspace.sites[site_index]
        return self._with_site(site_index, site.with_cameras(cameras))

    def _add_site(self) -> None:
        name = self._workspace.unique_site_name(self._translator.t("untitled_site"))
        index = len(self._workspace.sites)
        if self._commit(lambda: self._workspace.with_sites((*self._workspace.sites, Site(name))),
                        [(index, None)]):
            self._tree.editItem(self._tree.topLevelItem(index), 0)

    def _new_camera(self) -> None:
        """Fill in one camera in a small window; it joins the selected site's list."""
        selected = self._selected()
        if not selected:
            return
        site_index = selected[0][0]
        cameras = self._workspace.sites[site_index].cameras
        updated = edit_camera(self, self._translator, None,
                              lambda camera: self._with_cameras(site_index, (*cameras, camera)))
        if updated is not None:
            self._commit(lambda: updated, [(site_index, len(cameras))])

    def _delete_selected(self) -> None:
        """Delete every selected site and camera; nothing is final until it is applied."""
        selected = self._selected()
        if not selected:
            return
        sites = {site for site, camera in selected if camera is None}
        cameras = {ref for ref in selected if ref[1] is not None and ref[0] not in sites}

        def build() -> Workspace:
            kept = [site.with_cameras(camera for index, camera in enumerate(site.cameras)
                                      if (site_index, index) not in cameras)
                    for site_index, site in enumerate(self._workspace.sites)
                    if site_index not in sites]
            workspace = self._workspace.with_sites(kept)
            active = workspace.active_site   # the remembered site, or the first one left
            return workspace.with_last_site(active.name if active else "")

        # Select the site the first deleted row was in, or the nearest one left.
        left = len(self._workspace.sites) - len(sites)
        first = min(selected[0][0] - sum(1 for site in sites if site < selected[0][0]), left - 1)
        self._commit(build, [(first, None)] if left else [])

    def _can_move(self, step: int) -> bool:
        """A block moves when it is all sites, or all cameras of one site, and has room."""
        selected = self._selected()
        if not selected:
            return False
        if all(camera is None for _site, camera in selected):
            indices, count = [site for site, _camera in selected], len(self._workspace.sites)
        elif all(camera is not None for _site, camera in selected) and len({s for s, _c in selected}) == 1:
            indices = [camera for _site, camera in selected]
            count = len(self._workspace.sites[selected[0][0]].cameras)
        else:
            return False
        return 0 <= min(indices) + step and max(indices) + step < count

    def _move_selected(self, step: int) -> None:
        """List order is the order: sites order the sidebar, cameras order the wall's tiles."""
        if not self._can_move(step):
            return
        selected = self._selected()
        order = (lambda refs: refs) if step < 0 else reversed   # the leading edge moves first
        if selected[0][1] is None:
            sites = list(self._workspace.sites)
            for site_index, _camera in order(selected):
                sites[site_index], sites[site_index + step] = sites[site_index + step], sites[site_index]
            self._commit(lambda: self._workspace.with_sites(sites),
                         [(site + step, None) for site, _camera in selected])
            return
        site_index = selected[0][0]
        cameras = list(self._workspace.sites[site_index].cameras)
        for _site, index in order(selected):
            cameras[index], cameras[index + step] = cameras[index + step], cameras[index]
        self._commit(lambda: self._with_cameras(site_index, cameras),
                     [(site_index, index + step) for _site, index in selected])

    def _apply_inline_name(self, item: QTreeWidgetItem, _column: int) -> None:
        """F2 or double-click rename; an empty or taken site name is not applied."""
        site_index, camera_index = item.data(0, Qt.ItemDataRole.UserRole)
        name = item.text(0).strip()
        site = self._workspace.sites[site_index]
        if camera_index is None:
            if name == site.name:
                return
            if not name or self._workspace.site(name) is not None:
                self._reload_tree()
                self._select([(site_index, None)])
                return
            self._commit(lambda: self._with_site(site_index, replace(site, name=name)),
                         [(site_index, None)])
            return
        cameras = list(site.cameras)
        if name == cameras[camera_index].label:
            return   # the row shows the label; an unnamed camera must not take its URL as a name
        cameras[camera_index] = Camera.from_raw({**cameras[camera_index].as_dict(), "name": name})
        self._commit(lambda: self._with_cameras(site_index, cameras), [(site_index, camera_index)])

    def _edit_ai_feeds(self) -> None:
        selected = self._selected()
        if len(selected) != 1:
            return
        site_index = selected[0][0]
        updated = edit_site_ai_feeds(self, self._workspace, self._translator,
                                     self._workspace.sites[site_index].name)
        if updated is not None:
            self._commit(lambda: updated, [(site_index, None)])

    # ---- applying -----------------------------------------------------------------------

    def _changes_text(self) -> str:
        t = self._translator.t
        lines = []
        for camera, fields in self._drafts.values():
            parts = []
            for key in changed_fields(camera, fields):
                label = t(FIELD_LABEL_KEYS[key])
                # Only the name is shown in full: addresses and credentials stay off screen.
                parts.append(t("changed_value", field=label, old=camera.name, new=fields[key].strip())
                             if key == "name" else label)
            lines.append(t("change_line", camera=camera.label, fields=t("list_separator").join(parts)))
        return "\n".join(lines)

    def _apply_drafts(self) -> bool:
        """One change for every draft, so a rejected camera leaves all of them unapplied."""
        replacements: dict[int, Camera] = {}
        for key, (camera, fields) in self._drafts.items():
            try:
                replacements[key] = Camera.from_raw(fields)
            except ValueError as error:
                self._form.show_error(f"{camera.label}: {error}")
                return False

        def build() -> Workspace:
            return self._workspace.with_sites(
                site.with_cameras(replacements.get(id(c), c) for c in site.cameras)
                for site in self._workspace.sites)

        selected = self._selected()
        drafts = self._drafts
        self._drafts = {}
        if not self._commit(build, selected):
            self._drafts = drafts
            self._reload_tree()
            return False
        return True

    def _apply(self) -> bool:
        """套用: hand the working copy to the app; changed camera fields are listed first."""
        self._stash_form()
        if self._drafts:
            answer = QMessageBox.question(self, self._translator.t("save_changes"),
                                          self._translator.t("save_changes_confirm",
                                                             changes=self._changes_text()))
            if answer != QMessageBox.StandardButton.Yes or not self._apply_drafts():
                return False
        if self._workspace != self._applied:
            self._on_change(self._workspace)
            self._applied = self._workspace
        return True

    def _confirm(self) -> None:
        if self._apply():
            self.accept()


def open_editor(parent: QWidget, workspace: Workspace,
                on_change: Callable[[Workspace], None], translator: Translator,
                initial_site_name: str | None = None) -> None:
    editor = WorkspaceEditor(parent, workspace, on_change, translator, initial_site_name)
    editor.setModal(True)
    editor.exec()
