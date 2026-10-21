"""Settings dialog: sites and cameras.

Adding, deleting, moving and renaming are written to the workspace at once through
`on_change`. Edits to a camera's fields are drafts: switching to another camera keeps
them, and Save applies every draft after listing what changed. The wall reconnects
once when the dialog closes, not on every edit.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from cctv_wall.event_log import logger
from cctv_wall.i18n import Translator
from cctv_wall.models import Camera, Site, Workspace
from cctv_wall.ui.camera_form import FIELD_LABEL_KEYS, CameraForm, changed_fields
from cctv_wall.ui.site_commands import edit_site_ai_feeds
from cctv_wall.ui.flat_tree import FlatTree

ROW_HEIGHT = 38
MARGIN = 16          # window edge and the gap between the two panes
GROUP_SPACING = 8    # between buttons of one group


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
        # id(original camera) -> (that camera, edited fields). Keyed by identity, so a draft
        # follows its camera when cameras are moved; the tuple keeps the id from being reused.
        self._drafts: dict[int, tuple[Camera, dict[str, str]]] = {}
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
        # One margin around and between the two panes; tighter spacing only inside a group
        # of related buttons, a wider gap between groups.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        layout.setSpacing(MARGIN)
        body = QHBoxLayout()
        body.setSpacing(MARGIN)
        self._tree = FlatTree()
        self._tree.itemSelectionChanged.connect(self._on_tree_select)
        self._tree.itemChanged.connect(self._apply_inline_name)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_tree_menu)
        # An empty list has nothing to right-click on, so it offers the first site itself.
        self._add_site_button = QPushButton(self._translator.t("add_site"))
        self._add_site_button.clicked.connect(self._add_site)
        QVBoxLayout(self._tree.viewport()).addWidget(self._add_site_button, 0,
                                                     Qt.AlignmentFlag.AlignCenter)
        sites_column = QVBoxLayout()
        sites_column.setSpacing(GROUP_SPACING)
        sites_column.addWidget(QLabel(self._translator.t("site_list")))
        sites_column.addWidget(self._tree, 1)
        body.addLayout(sites_column, 1)
        self._form = CameraForm(self._translator)
        self._form.submitted.connect(self._save_camera)
        # Tab walks the fields; Up/Down walk the cameras, the cursor staying in the same field.
        for key, step in (("Up", -1), ("Down", 1)):
            shortcut = QShortcut(QKeySequence(key), self._form)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda chosen=step: self._step_camera(chosen))
        form_column = QVBoxLayout()
        form_column.setSpacing(GROUP_SPACING)
        # Its own heading keeps the fields level with the site list.
        form_column.addWidget(QLabel(self._translator.t("camera_details")))
        form_column.addWidget(self._form)
        form_column.addStretch(1)
        body.addLayout(form_column, 2)
        layout.addLayout(body, 1)

        # No Close button: every action is already saved, and the title bar closes the dialog.
        bottom = QHBoxLayout()
        bottom.setSpacing(GROUP_SPACING)
        bottom.addStretch(1)
        self._new_button = QPushButton(self._translator.t("add"))
        self._new_button.clicked.connect(self._new_camera)
        self._delete_button = QPushButton(self._translator.t("delete"))
        self._delete_button.clicked.connect(self._delete_selected)
        self._save_button = QPushButton(self._translator.t("save_camera"))
        self._save_button.clicked.connect(self._save_camera)
        for button in (self._new_button, self._delete_button, self._save_button):
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
        self._stash_form()
        self._site_index, self._camera_index = item.data(0, Qt.ItemDataRole.UserRole)
        if self._camera_index is None:
            self._fill_form(None)
        else:
            camera = self._site.cameras[self._camera_index]
            draft = self._drafts.get(id(camera))
            if draft is None:
                self._fill_form(camera)
            else:
                self._form.set_fields(draft[1])
        self._refresh_buttons()

    def _step_camera(self, step: int) -> None:
        """Next or previous camera row in the list, passing over site rows."""
        item = self._tree.currentItem()
        while item is not None:
            item = self._tree.itemBelow(item) if step > 0 else self._tree.itemAbove(item)
            if item is not None and item.parent() is not None:
                self._tree.setCurrentItem(item)
                return

    def _selected_camera(self) -> Camera | None:
        if self._site_index is None or self._camera_index is None:
            return None
        if not 0 <= self._site_index < len(self._workspace.sites):
            return None
        cameras = self._site.cameras
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
        item = self._tree.topLevelItem(self._site_index)
        item = item.child(self._camera_index) if item is not None else None
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
        self._stash_form()
        try:
            workspace = build()
        except ValueError as error:
            logger().warning("settings change refused: %s", error)
            self._form.show_error(str(error))
            return False
        self._form.show_error("")
        self._workspace = workspace
        self._on_change(workspace)
        # Drafts of cameras that no longer exist (deleted, or replaced by a rename) go too.
        alive = {id(camera) for site in workspace.sites for camera in site.cameras}
        self._drafts = {key: draft for key, draft in self._drafts.items() if key in alive}
        # The indices may point elsewhere in the new workspace: nothing to stash on reselect.
        self._site_index = self._camera_index = None
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
        self._form.focus_name()
        self._refresh_buttons()

    def _save_camera(self) -> None:
        """Save: add the new camera being typed, or apply every camera draft after confirming."""
        if self._site_index is None:
            return
        if self._camera_index is None and any(text.strip() for text in self._form.fields().values()):
            camera = self._form.read_camera()
            if camera is None:
                return
            site_index = self._site_index
            cameras = [*self._site.cameras, camera]
            if not self._commit(lambda: self._with_cameras(site_index, cameras),
                                (site_index, len(cameras) - 1)):
                return
        self._stash_form()
        if not self._drafts:
            return
        answer = QMessageBox.question(self, self._translator.t("save_changes"),
                                      self._translator.t("save_changes_confirm", changes=self._changes_text()))
        if answer == QMessageBox.StandardButton.Yes:
            self._apply_drafts()

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
        """One commit for every draft, so a rejected camera leaves all of them unsaved."""
        selected = self._site_index, self._camera_index
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

        drafts = self._drafts
        self._drafts = {}
        if not self._commit(build, selected if selected[0] is not None else None):
            self._drafts = drafts
            self._reload_tree()
            return False
        return True

    def reject(self) -> None:
        """Closing with unsaved camera edits asks first; Esc and the title bar both land here."""
        self._stash_form()
        if self._drafts:
            answer = QMessageBox.question(
                self, self._translator.t("save_changes"),
                self._translator.t("unsaved_changes", changes=self._changes_text()),
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel:
                return
            if answer == QMessageBox.StandardButton.Save and not self._apply_drafts():
                return
        super().reject()

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
        if name == cameras[camera_index].label:
            return   # the row shows the label; an unnamed camera must not take its URL as a name
        cameras[camera_index] = Camera.from_raw({**cameras[camera_index].as_dict(), "name": name})
        self._commit(lambda: self._with_cameras(site_index, cameras), (site_index, camera_index))

    def _edit_ai_feeds(self) -> None:
        if self._site_index is None:
            return
        site_index = self._site_index
        updated = edit_site_ai_feeds(self, self._workspace, self._translator, self._site.name)
        if updated is not None:
            self._commit(lambda: updated, (site_index, None))

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
        self._form.set_camera(camera)

    def _refresh_buttons(self) -> None:
        has_site = self._site_index is not None
        for widget in (self._new_button, self._save_button, self._delete_button, self._form):
            widget.setEnabled(has_site)


def open_editor(parent: QWidget, workspace: Workspace,
                on_change: Callable[[Workspace], None], translator: Translator,
                initial_site_name: str | None = None) -> None:
    editor = WorkspaceEditor(parent, workspace, on_change, translator, initial_site_name)
    editor.setModal(True)
    editor.exec()
