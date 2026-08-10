"""Modal Qt editor for a disposable workspace draft."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field, replace
from typing import Callable
from urllib.parse import unquote, urlsplit

from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QMenu, QSplitter, QTreeWidget, QTreeWidgetItem,
                               QToolButton, QVBoxLayout, QWidget, QSizePolicy, QScrollArea,
                               QStyledItemDelegate)

from cctv_wall import quality as quality_module
from cctv_wall import vendors
from cctv_wall.i18n import Translator
from cctv_wall.models import MAX_STREAM, MIN_STREAM, Camera, Site, Workspace
from cctv_wall.urls import display_url

PRIMARY_TEXT_FIELDS = ("name", "url")
ADVANCED_TEXT_FIELDS = ("host", "port", "user", "password", "path_template")
TEXT_FIELDS = PRIMARY_TEXT_FIELDS + ADVANCED_TEXT_FIELDS
CHOICE_FIELDS = (
    ("vendor", vendors.VENDORS),
    ("stream", tuple(str(value) for value in range(MIN_STREAM, MAX_STREAM + 1))),
    ("quality", quality_module.QUALITIES),
)
FIELD_LABEL_KEYS = {
    "name": "name", "host": "host", "port": "port", "user": "username",
    "password": "password", "path_template": "custom_path", "url": "direct_url",
    "vendor": "vendor", "stream": "stream", "quality": "quality",
}


@dataclass(slots=True)
class _SiteDraft:
    """A site being edited. Mutable on purpose: it is thrown away unless Save is pressed."""

    name: str
    cameras: list[Camera] = field(default_factory=list)


class _CenteredTreeEditorDelegate(QStyledItemDelegate):
    """Keep the temporary rename field centered inside the taller tree rows."""

    def updateEditorGeometry(self, editor: QWidget, option, index) -> None:
        rect = option.rect.adjusted(3, 0, -3, 0)
        height = min(30, max(1, rect.height() - 8))
        editor.setGeometry(rect.x(), rect.y() + (rect.height() - height) // 2,
                           rect.width(), height)


class WorkspaceEditor(QDialog):
    """Edits a mutable draft and publishes a new immutable workspace only on Save."""

    def __init__(self, parent: QWidget, workspace: Workspace,
                 on_save: Callable[[Workspace], None], translator: Translator,
                 initial_site_name: str | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setWindowTitle(translator.t("settings_title"))
        self.resize(1000, 620)
        self._workspace = workspace
        self._on_save = on_save
        self._draft = [_SiteDraft(site.name, list(site.cameras)) for site in workspace.sites]
        self._selected_site: int | None = None
        self._selected_camera: int | None = None
        self._new_camera_dirty = False
        self._fields: dict[str, QLineEdit | QComboBox] = {}
        self._build_ui()
        self._reload_tree()
        self._clear_form()
        if initial_site_name:
            site_index = next((index for index, site in enumerate(self._draft)
                               if site.name == initial_site_name), None)
            if site_index is not None:
                self._select(site_index)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        title = QLabel(self._translator.t("settings_heading"))
        title.setObjectName("dialogTitle")
        title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(title)
        description = QLabel(self._translator.t("settings_help"))
        description.setObjectName("dialogDescription")
        description.setWordWrap(True)
        description.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(description)
        splitter = QSplitter()
        splitter.addWidget(self._tree_panel())
        splitter.addWidget(self._form_panel())
        splitter.setSizes([300, 700])
        layout.addWidget(splitter, 1)

    def _tree_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setItemDelegate(_CenteredTreeEditorDelegate(self._tree))
        self._tree.itemSelectionChanged.connect(self._on_tree_select)
        self._tree.itemDoubleClicked.connect(self._rename_double_clicked)
        self._tree.itemChanged.connect(self._apply_inline_name)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_tree_menu)
        layout.addWidget(self._tree)
        return panel

    def _form_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        primary = QGroupBox(self._translator.t("basic_settings"))
        primary.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        primary_form = QFormLayout(primary)
        primary_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for key in PRIMARY_TEXT_FIELDS:
            self._add_text_row(primary_form, key)
        layout.addWidget(primary)

        self._advanced_toggle = QToolButton()
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._advanced_toggle.toggled.connect(self._set_advanced_visible)
        layout.addWidget(self._advanced_toggle)

        self._advanced_container = QWidget()
        advanced_layout = QVBoxLayout(self._advanced_container)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        connection = QGroupBox(self._translator.t("connection"))
        form = QFormLayout(connection)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for key in ADVANCED_TEXT_FIELDS:
            self._add_text_row(form, key)
        advanced_layout.addWidget(connection)
        streaming = QGroupBox(self._translator.t("stream_selection"))
        stream_form = QFormLayout(streaming)
        stream_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for key, values in CHOICE_FIELDS:
            field = QComboBox()
            field.addItems(values)
            field.currentTextChanged.connect(self._refresh_preview)
            field.activated.connect(self._mark_new_camera_dirty)
            self._fields[key] = field
            stream_form.addRow(self._translator.t(FIELD_LABEL_KEYS[key]), field)
        advanced_layout.addWidget(streaming)
        next_ip = QPushButton(self._translator.t("next_ip"))
        next_ip.clicked.connect(self._increment_ip)
        advanced_layout.addWidget(next_ip, 0, Qt.AlignmentFlag.AlignLeft)
        self._advanced_scroll = QScrollArea()
        self._advanced_scroll.setWidgetResizable(True)
        self._advanced_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._advanced_scroll.setMaximumHeight(310)
        self._advanced_scroll.setWidget(self._advanced_container)
        layout.addWidget(self._advanced_scroll)
        self._set_advanced_visible(False)
        preview_title = QLabel(self._translator.t("url_preview"))
        preview_title.setObjectName("controlLabel")
        preview_title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(preview_title)
        self._preview = QLabel()
        self._preview.setWordWrap(True)
        self._preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._preview.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._preview)
        help_text = QLabel(self._translator.t("stream_help"))
        help_text.setObjectName("formHelp")
        help_text.setWordWrap(True)
        help_text.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(help_text)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for text, action in ((self._translator.t("save_add_another"), self._apply_and_add_another),
                             (self._translator.t("save"), self._save),
                             (self._translator.t("cancel"), self.reject)):
            button = QPushButton(text)
            button.clicked.connect(action)
            buttons.addWidget(button)
        layout.addStretch(1)
        layout.addLayout(buttons)
        return panel

    def _add_text_row(self, form: QFormLayout, key: str) -> None:
        """Add one field while keeping the direct source picker in the primary section."""
        field = QLineEdit()
        if key == "password":
            field.setEchoMode(QLineEdit.EchoMode.Password)
        field.textChanged.connect(self._refresh_preview)
        field.textEdited.connect(self._mark_new_camera_dirty)
        if key == "url":
            field.textEdited.connect(self._extract_connection_from_source)
        self._fields[key] = field
        if key != "url":
            form.addRow(self._translator.t(FIELD_LABEL_KEYS[key]), field)
            return
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(field)
        browse = QPushButton(self._translator.t("browse"))
        browse.clicked.connect(self._browse)
        row_layout.addWidget(browse)
        form.addRow(self._translator.t(FIELD_LABEL_KEYS[key]), row)

    def _extract_connection_from_source(self, source: str) -> None:
        """Copy credentials and endpoint details out of a pasted RTSP-style URL.

        The source stays untouched: it remains the authoritative playback URL, while
        the extracted values make future cameras and advanced edits less repetitive.
        """
        try:
            parsed = urlsplit(source.strip())
            host = parsed.hostname
            port = parsed.port
        except ValueError:
            return
        if not host:
            return

        self._set_field(self._fields["host"], host)
        if port is not None:
            self._set_field(self._fields["port"], str(port))
        if parsed.username is not None:
            self._set_field(self._fields["user"], unquote(parsed.username))
        if parsed.password is not None:
            self._set_field(self._fields["password"], unquote(parsed.password))
        self._set_advanced_visible(True)

    def _set_advanced_visible(self, visible: bool) -> None:
        self._advanced_scroll.setVisible(visible)
        self._advanced_toggle.blockSignals(True)
        self._advanced_toggle.setChecked(visible)
        self._advanced_toggle.setText(self._translator.t(
            "advanced_connection_hide" if visible else "advanced_connection_show"))
        self._advanced_toggle.blockSignals(False)
        if self.isVisible():
            QTimer.singleShot(0, self._fit_height_to_contents)

    def _fit_height_to_contents(self) -> None:
        """Discard the splitter's expanded size hint when the advanced section closes."""
        if not self._advanced_scroll.isVisible():
            self.resize(self.width(), 620)

    def _reload_tree(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        for site_index, site in enumerate(self._draft):
            site_item = QTreeWidgetItem([site.name])
            site_item.setFlags(site_item.flags() | Qt.ItemFlag.ItemIsEditable)
            site_item.setSizeHint(0, QSize(0, 38))
            site_item.setData(0, Qt.ItemDataRole.UserRole, (site_index, None))
            self._tree.addTopLevelItem(site_item)
            for camera_index, camera in enumerate(site.cameras):
                camera_item = QTreeWidgetItem([camera.label])
                camera_item.setFlags(camera_item.flags() | Qt.ItemFlag.ItemIsEditable)
                camera_item.setSizeHint(0, QSize(0, 38))
                camera_item.setData(0, Qt.ItemDataRole.UserRole, (site_index, camera_index))
                site_item.addChild(camera_item)
            site_item.setExpanded(True)
        self._tree.blockSignals(False)

    def _on_tree_select(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        self._selected_site, self._selected_camera = item.data(0, Qt.ItemDataRole.UserRole)
        if self._selected_camera is None:
            self._clear_form()
            return
        camera = self._draft[self._selected_site].cameras[self._selected_camera]
        for key, field in self._fields.items():
            self._set_field(field, str(getattr(camera, key)))
        self._set_advanced_visible(not bool(camera.url))

    def _show_tree_menu(self, position) -> None:
        """Keep hierarchy management at the point of selection instead of scattering buttons."""
        item = self._tree.itemAt(position)
        if item is not None:
            self._tree.setCurrentItem(item)
        menu = QMenu(self)
        menu.setMinimumWidth(240)
        if item is None:
            menu.addAction(self._translator.t("add_site"), self._add_site)
        elif self._selected_camera is None:
            menu.addAction(self._translator.t("add_camera"), self._add_camera)
            menu.addAction(self._translator.t("duplicate_selected"), self._duplicate_selected)
            menu.addAction(self._translator.t("rename_site"), self._rename_selected_site)
            self._add_move_actions(menu)
            menu.addSeparator()
            menu.addAction(self._translator.t("delete"), self._delete_selected)
        else:
            menu.addAction(self._translator.t("duplicate_selected"), self._duplicate_selected)
            self._add_move_actions(menu)
            menu.addSeparator()
            menu.addAction(self._translator.t("delete"), self._delete_selected)
        menu.exec(self._tree.viewport().mapToGlobal(position))

    def _add_move_actions(self, menu: QMenu) -> None:
        """排序就是清單順序，所以搬移動作對地點與攝影機是同一段程式。"""
        for label, offset in ((self._translator.t("move_up"), -1),
                              (self._translator.t("move_down"), 1)):
            action = menu.addAction(
                label, lambda checked=False, step=offset: self._move_selected(step))
            action.setEnabled(self._can_move(offset))

    def _selected_row(self) -> tuple[int, list] | None:
        """目前選到的位置與它所屬的清單；未選任何項目時回傳 None。"""
        if self._selected_site is None:
            return None
        if self._selected_camera is None:
            return self._selected_site, self._draft
        return self._selected_camera, self._draft[self._selected_site].cameras

    def _can_move(self, offset: int) -> bool:
        row = self._selected_row()
        return row is not None and 0 <= row[0] + offset < len(row[1])

    def _move_selected(self, offset: int) -> None:
        """在同一層內上下搬移。地點順序決定側欄排列，攝影機順序決定影像牆格子順序。"""
        row = self._selected_row()
        if row is None or not self._can_move(offset):
            return
        index, items = row
        target = index + offset
        items[index], items[target] = items[target], items[index]
        if self._selected_camera is None:
            self._selected_site = target
        else:
            self._selected_camera = target
        self._reload_tree()
        self._select(self._selected_site, self._selected_camera)

    @staticmethod
    def _set_field(field: QLineEdit | QComboBox, value: str) -> None:
        field.blockSignals(True)
        if isinstance(field, QLineEdit):
            field.setText(value)
        else:
            field.setCurrentText(value)
        field.blockSignals(False)

    def _clear_form(self) -> None:
        self._new_camera_dirty = False
        self._set_advanced_visible(False)
        # A placeholder host only satisfies Camera's "url or host" rule; the port, stream
        # and quality defaults are what this form actually needs to show.
        defaults = Camera(host="0.0.0.0")
        for key, field in self._fields.items():
            blank = key in TEXT_FIELDS and key != "port"
            self._set_field(field, "" if blank else str(getattr(defaults, key)))
        self._refresh_preview()

    def _form_value(self, key: str) -> str:
        field = self._fields[key]
        return field.text() if isinstance(field, QLineEdit) else field.currentText()

    def _camera_from_form(self) -> Camera:
        return Camera.from_raw({key: self._form_value(key) for key in self._fields})

    def _refresh_preview(self) -> None:
        try:
            self._preview.setText(display_url(self._camera_from_form()))
            self._preview.setProperty("invalid", False)
        except ValueError as error:
            self._preview.setText(str(error))
            self._preview.setProperty("invalid", True)
        self._preview.style().unpolish(self._preview)
        self._preview.style().polish(self._preview)

    def _select(self, site_index: int, camera_index: int | None = None) -> None:
        parent = self._tree.topLevelItem(site_index)
        item = parent if camera_index is None else parent.child(camera_index)
        self._tree.setCurrentItem(item)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self._translator.t("video_file"),
            filter="Video (*.mp4 *.mkv *.avi *.mov *.ts *.m3u8);;All files (*)")
        if path:
            self._set_field(self._fields["url"], path)
            self._mark_new_camera_dirty()
            self._refresh_preview()

    def _add_site(self) -> None:
        """Create a uniquely named row, then let the user name it in the tree."""
        name = self._unique_site_name(self._translator.t("untitled_site"))
        self._draft.append(_SiteDraft(name))
        self._reload_tree()
        site_index = len(self._draft) - 1
        self._select(site_index)
        self._begin_inline_rename(self._tree.topLevelItem(site_index))

    def _unique_site_name(self, base: str) -> str:
        """`base`, or `base 2`, `base 3`… — site names identify a place, so they must differ."""
        names = {site.name for site in self._draft}
        if base not in names:
            return base
        number = 2
        while f"{base} {number}" in names:
            number += 1
        return f"{base} {number}"

    def _add_camera(self) -> None:
        if self._selected_site is None:
            QMessageBox.information(self, self._translator.t("add_camera"), self._translator.t("select_site"))
            return
        self._selected_camera = None
        self._select(self._selected_site)
        self._clear_form()
        self._preview.setText(self._translator.t("fill_camera"))

    def _apply_and_add_another(self) -> None:
        """Add this camera to the draft and immediately prepare the next one on this site."""
        if not self._apply():
            return
        assert self._selected_site is not None and self._selected_camera is not None
        self._prepare_next_camera(self._draft[self._selected_site].cameras[self._selected_camera])

    def _prepare_next_camera(self, source: Camera) -> None:
        """Carry over reusable connection choices, never a duplicate display name or URL."""
        self._selected_camera = None
        self._select(self._selected_site)
        for key, field in self._fields.items():
            value = "" if key in {"name", "url"} else str(getattr(source, key))
            self._set_field(field, value)
        self._new_camera_dirty = False
        self._set_advanced_visible(True)
        self._refresh_preview()

    def _rename_selected_site(self) -> None:
        if self._selected_site is None:
            return
        item = self._tree.topLevelItem(self._selected_site)
        self._begin_inline_rename(item)

    def _rename_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Use the natural double-click gesture for the one field that identifies a tree item."""
        self._begin_inline_rename(item)

    def _begin_inline_rename(self, item: QTreeWidgetItem) -> None:
        self._tree.setCurrentItem(item)
        self._tree.editItem(item, 0)

    def _apply_inline_name(self, item: QTreeWidgetItem, _column: int) -> None:
        site_index, camera_index = item.data(0, Qt.ItemDataRole.UserRole)
        name = item.text(0).strip()
        if camera_index is None:
            duplicate = any(index != site_index and site.name == name
                            for index, site in enumerate(self._draft))
            if not name or duplicate:
                self._restore_tree_text(item, self._draft[site_index].name)
                return
            self._draft[site_index].name = name
            return
        cameras = self._draft[site_index].cameras
        source = cameras[camera_index]
        cameras[camera_index] = replace(source, name=name)

    def _restore_tree_text(self, item: QTreeWidgetItem, text: str) -> None:
        self._tree.blockSignals(True)
        item.setText(0, text)
        self._tree.blockSignals(False)

    def _duplicate_selected(self) -> None:
        """Copy a whole site or one camera according to the current tree selection."""
        if self._selected_site is None:
            QMessageBox.information(self, self._translator.t("duplicate_selected"),
                                    self._translator.t("select_item"))
            return
        if self._selected_camera is None:
            source = self._draft[self._selected_site]
            name = self._unique_site_name(f"{source.name} {self._translator.t('copy_suffix')}")
            self._draft.append(_SiteDraft(name, list(source.cameras)))
            self._reload_tree()
            self._select(len(self._draft) - 1)
            return
        cameras = self._draft[self._selected_site].cameras
        source = cameras[self._selected_camera]
        copied = replace(source, name=f"{source.label} {self._translator.t('copy_suffix')}")
        cameras.append(copied)
        self._selected_camera = len(cameras) - 1
        self._reload_tree()
        self._select(self._selected_site, self._selected_camera)

    def _increment_ip(self) -> None:
        """Advance an IPv4/IPv6 address in the form without touching its other fields."""
        try:
            advanced = ipaddress.ip_address(self._form_value("host").strip()) + 1
        except ValueError:
            QMessageBox.warning(self, self._translator.t("next_ip"), self._translator.t("invalid_ip"))
            return
        self._set_field(self._fields["host"], str(advanced))
        self._mark_new_camera_dirty()
        self._refresh_preview()

    def _delete_selected(self) -> None:
        if self._selected_site is None:
            return
        site = self._draft[self._selected_site]
        if self._selected_camera is None:
            answer = QMessageBox.question(self, self._translator.t("delete_site"),
                                          self._translator.t("delete_site_confirm", name=site.name))
            if answer != QMessageBox.StandardButton.Yes:
                return
            del self._draft[self._selected_site]
        else:
            del site.cameras[self._selected_camera]
        self._selected_site = self._selected_camera = None
        self._reload_tree()
        self._clear_form()

    def _apply(self) -> bool:
        if self._selected_site is None:
            QMessageBox.information(self, self._translator.t("apply_title"), self._translator.t("select_site"))
            return False
        try:
            camera = self._camera_from_form()
        except ValueError as error:
            QMessageBox.critical(self, self._translator.t("invalid_camera"), str(error))
            return False
        cameras = self._draft[self._selected_site].cameras
        if self._selected_camera is None:
            cameras.append(camera)
            self._selected_camera = len(cameras) - 1
        else:
            cameras[self._selected_camera] = camera
        self._reload_tree()
        self._select(self._selected_site, self._selected_camera)
        self._new_camera_dirty = False
        return True

    def _save(self) -> None:
        if self._has_camera_form() and not self._apply():
            return
        try:
            sites = tuple(Site(name=site.name, cameras=tuple(site.cameras))
                          for site in self._draft)
        except ValueError as error:
            QMessageBox.critical(self, self._translator.t("cannot_save"), str(error))
            return
        self._on_save(self._workspace.with_sites(sites))
        self.accept()

    def _has_camera_form(self) -> bool:
        """A selected camera is always saved; a new one needs a source before it is created."""
        if self._selected_camera is not None:
            return True
        return (self._new_camera_dirty and self._selected_site is not None
                and bool(self._form_value("host").strip() or self._form_value("url").strip()))

    def _mark_new_camera_dirty(self, *_unused: object) -> None:
        if self._selected_camera is None:
            self._new_camera_dirty = True


def open_editor(parent: QWidget, workspace: Workspace,
                on_save: Callable[[Workspace], None], translator: Translator,
                initial_site_name: str | None = None) -> WorkspaceEditor:
    editor = WorkspaceEditor(parent, workspace, on_save, translator, initial_site_name)
    editor.setModal(True)
    editor.exec()
    return editor
