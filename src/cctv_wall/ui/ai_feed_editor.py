"""Dialog for a site's AI connections: address, delay and alignment, camera mapping with
per-camera filters, the result lines under each tile, and the message format."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton,
                               QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from cctv_wall.ai_feed import (ALIGN_AI_TIME, ALIGN_RECEIVED, DEFAULT_CAMERA_KEY, DEFAULT_DELAY_MS,
                               DEFAULT_TIME_KEY, MAX_DELAY_MS, AiFeedConfig)
from cctv_wall.event_log import logger
from cctv_wall.i18n import Translator
from cctv_wall.models import Camera, Site
from cctv_wall.ui.ai_panel import short_camera_name

# Message-format settings change per project, not per site visit, so they stay as
# JSON text instead of a widget for every option.
ADVANCED_KEYS = ("camera_key", "time_key", "skip", "skip_empty", "labels")


@dataclass(slots=True)
class FeedForm:
    """What the dialog holds for one connection while it is being edited."""

    host: str = ""
    port: str = ""
    delay_ms: int = DEFAULT_DELAY_MS
    mapping: list[tuple[str, str]] = field(default_factory=list)   # (AI id, camera name)
    advanced: str = ""
    tile_key: str = ""
    tile_values: list[str] = field(default_factory=list)
    align: str = ALIGN_AI_TIME   # new connections; a stored one without "align" keeps "received"
    filters: dict[str, tuple[str, list[str]]] = field(default_factory=dict)  # AI id -> (field, codes)

    @classmethod
    def from_config(cls, config: AiFeedConfig) -> "FeedForm":
        raw = config.as_dict()
        return cls(config.host, str(config.port), config.delay_ms, list(config.cameras),
                   _advanced_text({key: raw[key] for key in ADVANCED_KEYS if key in raw}),
                   config.tile_key, list(config.tile_values), config.align,
                   {source: (field_name, list(values))
                    for source, field_name, values in config.camera_filters})

    def copy_format(self) -> "FeedForm":
        """A new connection usually speaks the same format as the one beside it."""
        return FeedForm(delay_ms=self.delay_ms, advanced=self.advanced, tile_key=self.tile_key,
                        tile_values=list(self.tile_values), align=self.align)


def _advanced_text(values: dict[str, Any]) -> str:
    return json.dumps(values, ensure_ascii=False, indent=2)


def label_fields(advanced: str) -> dict[str, list[tuple[str, str]]] | None:
    """The labelled fields of a message format and their (code, text) pairs, in the order typed;
    None while the text is not a valid JSON object, so a half-typed edit keeps the old choices."""
    try:
        values = json.loads(advanced) if advanced.strip() else {}
    except ValueError:
        return None
    labels = values.get("labels") if isinstance(values, dict) else None
    if not isinstance(labels, dict):
        return None if not isinstance(values, dict) else {}
    return {str(name): [(str(code), str(text)) for code, text in codes.items()]
            for name, codes in labels.items() if isinstance(codes, dict)}


def default_advanced() -> str:
    return _advanced_text({"camera_key": DEFAULT_CAMERA_KEY, "time_key": DEFAULT_TIME_KEY})


def config_from_form(form: FeedForm) -> AiFeedConfig:
    """Validate one connection; ValueError messages name the field the operator must fix."""
    try:
        advanced = json.loads(form.advanced) if form.advanced.strip() else {}
    except ValueError as error:
        raise ValueError(f"advanced settings are not valid JSON: {error}") from error
    if not isinstance(advanced, dict):
        raise ValueError("advanced settings must be a JSON object")
    unknown = sorted(set(advanced) - set(ADVANCED_KEYS))
    if unknown:
        raise ValueError(f"unknown advanced setting(s): {', '.join(unknown)}")
    cameras: dict[str, str] = {}
    for source, camera in form.mapping:
        source, camera = source.strip(), camera.strip()
        if not source and not camera:
            continue
        if not source or not camera:
            raise ValueError("every camera mapping row needs both an AI id and a camera")
        if source in cameras:
            raise ValueError(f"AI id {source!r} is mapped twice")
        cameras[source] = camera
    filters = {source: {field_name: values} for source, (field_name, values) in form.filters.items()
               if source in cameras}
    return AiFeedConfig.from_raw({**advanced, "host": form.host, "port": form.port,
                                  "delay_ms": form.delay_ms, "cameras": cameras,
                                  "tile_key": form.tile_key, "tile_values": form.tile_values,
                                  "align": form.align, "camera_filters": filters})


def feeds_from_forms(site_name: str, cameras: Iterable[Camera],
                     forms: Sequence[FeedForm]) -> tuple[AiFeedConfig, ...]:
    """Build every connection, then let Site apply the cross-connection rules."""
    feeds = []
    for index, form in enumerate(forms, start=1):
        try:
            feeds.append(config_from_form(form))
        except ValueError as error:
            raise ValueError(f"#{index} {form.host}: {error}") from error
    Site(site_name, tuple(cameras), tuple(feeds))
    return tuple(feeds)


CHECK_ROOM = 44   # check box, its gap and the item padding, in pixels


class _CodePicker(QWidget):
    """A field and the codes ticked under it, both offered from the message format's labels."""

    def __init__(self, translator: Translator, none_text: str, help_text: str,
                 beside_key: QWidget | None = None) -> None:
        """With beside_key the picker spans a wide row: that widget sits at the end of the field
        row and the codes flow side by side, wrapping to the width."""
        super().__init__()
        self._none_text = none_text
        self._fields: dict[str, list[tuple[str, str]]] = {}
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel(translator.t("ai_tile_key")))
        self._key = QComboBox()
        self._key.currentIndexChanged.connect(lambda _index: self._show_values(self.values()))
        key_row.addWidget(self._key, 0 if beside_key else 1)
        if beside_key:
            key_row.addStretch(1)
            key_row.addWidget(beside_key)
        box.addLayout(key_row)
        help_label = QLabel(help_text)
        help_label.setObjectName("formHelp")
        help_label.setWordWrap(True)
        box.addWidget(help_label)
        self._values = QListWidget()
        if beside_key:
            self._values.setFlow(QListWidget.Flow.LeftToRight)
            self._values.setWrapping(True)
            self._values.setResizeMode(QListWidget.ResizeMode.Adjust)
            self._values.setSpacing(4)
            self._values.setTextElideMode(Qt.TextElideMode.ElideNone)
            self._values.setMaximumHeight(100)   # two or three wrapped rows of kinds
        box.addWidget(self._values)

    def set_fields(self, fields: dict[str, list[tuple[str, str]]]) -> None:
        """New choices from the message format; keeps the current field and ticks where they remain."""
        self._fields = fields
        self.set_choice(self.key(), self.values())

    def set_choice(self, key: str, values: Sequence[str]) -> None:
        self._key.blockSignals(True)
        self._key.clear()
        self._key.addItem(self._none_text, "")
        for name in self._fields:
            self._key.addItem(name, name)
        self._key.setCurrentIndex(max(self._key.findData(key), 0))
        self._key.blockSignals(False)
        self._show_values(values)

    def _show_values(self, checked: Sequence[str]) -> None:
        self._values.clear()
        for code, text in self._fields.get(self.key(), []):
            label = f"{text}  ({code})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, code)
            if self._values.isWrapping():
                # Side by side, the view sizes an item by its text alone and leaves out the
                # style sheet's check box, so the text would be cut short.
                metrics = self._values.fontMetrics()
                item.setSizeHint(QSize(metrics.horizontalAdvance(label) + CHECK_ROOM,
                                       metrics.height() + 10))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if code in checked else Qt.CheckState.Unchecked)
            self._values.addItem(item)
        self._values.setEnabled(bool(self.key()))

    def key(self) -> str:
        return self._key.currentData() or ""

    def values(self) -> list[str]:
        """In the order the format lists them, which is the order of the lines under a tile."""
        return [self._values.item(row).data(Qt.ItemDataRole.UserRole)
                for row in range(self._values.count())
                if self._values.item(row).checkState() == Qt.CheckState.Checked]


class _FilterButton(QPushButton):
    """One mapping row's camera filter, (field, codes) or None, shown as the kinds it keeps."""

    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        self.rule: tuple[str, list[str]] | None = None

    def show_rule(self, fields: dict[str, list[tuple[str, str]]]) -> None:
        """Codes read as their label text; the format's labels may have changed since."""
        if not self.rule:
            self.setText(self._translator.t("ai_filter_all"))
            self.setToolTip("")
            return
        field_name, values = self.rule
        names = dict(fields.get(field_name, []))
        shown = self._translator.t("list_separator").join(names.get(code, code) for code in values)
        self.setText(shown)
        self.setToolTip(self._translator.t("ai_filter_summary", field=field_name, values=shown))


class AiFeedsDialog(QDialog):
    """Edits a copy; the caller receives new configs only when OK passes validation."""

    def __init__(self, parent: QWidget, translator: Translator, site_name: str,
                 cameras: Sequence[Camera], feeds: Sequence[AiFeedConfig]) -> None:
        super().__init__(parent)
        self._translator = translator
        self._site_name = site_name
        self._cameras = tuple(cameras)
        # Results reach a tile by the camera's label, so unnamed cameras can be mapped too.
        self._camera_names = [camera.label for camera in self._cameras]
        self._forms = [FeedForm.from_config(feed) for feed in feeds]
        self._current: int | None = None
        self.result_feeds: tuple[AiFeedConfig, ...] | None = None
        self.tile_rows_for_all_sites: tuple[str, tuple[str, ...]] | None = None
        self.setWindowTitle(self._translator.t("ai_feeds_title", site=site_name))
        self.resize(1000, 820)
        self._build_ui()
        self._reload_list(0 if self._forms else None)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        help_text = QLabel(self._translator.t("ai_feeds_help"))
        help_text.setObjectName("dialogDescription")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        splitter = QSplitter()
        left = QWidget()
        left_box = QVBoxLayout(left)
        left_box.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._select)
        left_box.addWidget(self._list, 1)
        for text, action in ((self._translator.t("ai_add_feed"), self._add_feed),
                             (self._translator.t("ai_remove_feed"), self._remove_feed)):
            button = QPushButton(text)
            button.clicked.connect(action)
            left_box.addWidget(button)
        splitter.addWidget(left)
        self._form_panel = self._build_form()
        splitter.addWidget(self._form_panel)
        splitter.setSizes([170, 830])   # a site has one or two connections; the form needs the room
        layout.addWidget(splitter, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for text, action in ((self._translator.t("ai_ok"), self._accept),
                             (self._translator.t("cancel"), self.reject)):
            button = QPushButton(text)
            button.clicked.connect(action)
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def _build_form(self) -> QWidget:
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 0, 0)
        basic = QGroupBox(self._translator.t("connection"))
        form = QFormLayout(basic)
        self._host = QLineEdit()
        self._host.textEdited.connect(self._refresh_current_label)
        self._port = QLineEdit()
        self._port.setPlaceholderText(self._translator.t("port"))
        self._port.setMaximumWidth(90)
        self._port.textEdited.connect(self._refresh_current_label)
        address = QHBoxLayout()
        address.addWidget(self._host, 1)
        address.addWidget(QLabel(":"))
        address.addWidget(self._port)
        self._delay = QSpinBox()
        self._delay.setRange(0, MAX_DELAY_MS)
        self._delay.setSingleStep(100)
        self._delay.setSuffix(" ms")
        self._delay.setToolTip(self._translator.t("ai_delay_help"))
        # The style sheet flattens the box but cannot draw its spin arrows, so they would fall
        # back to bevelled native ones; flat buttons beside it match the rest of the dialog.
        self._delay.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        delay = QHBoxLayout()
        delay.addWidget(self._delay, 1)
        for text, step in (("−", self._delay.stepDown), ("＋", self._delay.stepUp)):
            button = QPushButton(text)
            button.setFixedWidth(40)
            button.clicked.connect(step)
            delay.addWidget(button)
        form.addRow(self._translator.t("ai_host"), address)
        form.addRow(self._translator.t("ai_delay"), delay)
        self._align = QComboBox()
        self._align.addItem(self._translator.t("ai_align_ai_time"), ALIGN_AI_TIME)
        self._align.addItem(self._translator.t("ai_align_received"), ALIGN_RECEIVED)
        self._align.setToolTip(self._translator.t("ai_delay_help"))
        form.addRow(self._translator.t("ai_align"), self._align)

        mapping = QGroupBox(self._translator.t("ai_camera_map"))
        mapping_box = QVBoxLayout(mapping)
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels([self._translator.t("ai_source_id"),
                                               self._translator.t("ai_camera"),
                                               self._translator.t("ai_filter")])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().hide()
        self._table.setMinimumHeight(140)   # header + four mappings without scrolling
        mapping_box.addWidget(self._table)
        row_buttons = QHBoxLayout()
        for text, action in ((self._translator.t("ai_add_row"), self._add_empty_row),
                             (self._translator.t("ai_remove_row"), self._remove_row)):
            button = QPushButton(text)
            button.clicked.connect(action)
            row_buttons.addWidget(button)
        row_buttons.addStretch(1)
        mapping_box.addLayout(row_buttons)

        advanced = QGroupBox(self._translator.t("ai_advanced"))
        advanced_box = QVBoxLayout(advanced)
        advanced_help = QLabel(self._translator.t("ai_advanced_help"))
        advanced_help.setObjectName("formHelp")
        advanced_help.setWordWrap(True)
        advanced_box.addWidget(advanced_help)
        self._advanced = QPlainTextEdit()
        self._advanced.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._advanced.textChanged.connect(self._refresh_tile_keys)
        advanced_box.addWidget(self._advanced)

        tiles = QGroupBox(self._translator.t("ai_tile_rows"))
        tiles_box = QVBoxLayout(tiles)
        self._tile_all_sites = QCheckBox(self._translator.t("ai_tile_all_sites"))
        self._tile_rows = _CodePicker(self._translator, self._translator.t("ai_tile_none"),
                                      self._translator.t("ai_tile_help"), self._tile_all_sites)
        tiles_box.addWidget(self._tile_rows)
        # The address and the mapping are both a few short rows, so they share one row; the
        # kinds get the full width and the message format takes what height is left.
        top = QHBoxLayout()
        top.addWidget(basic, 1)
        top.addWidget(mapping, 1)
        box.addLayout(top)
        box.addWidget(tiles)
        box.addWidget(advanced, 1)
        self._label_fields: dict[str, list[tuple[str, str]]] = {}
        return panel

    def _refresh_tile_keys(self) -> None:
        """The field choices follow the labels typed in the message format."""
        fields = label_fields(self._advanced.toPlainText())
        if fields is None:
            return   # mid-edit, not valid JSON yet: keep what is offered
        self._label_fields = fields
        self._tile_rows.set_fields(fields)
        for row in range(self._table.rowCount()):
            self._table.cellWidget(row, 2).show_rule(fields)

    def _edit_filter(self, button: _FilterButton) -> None:
        row = next(row for row in range(self._table.rowCount())
                   if self._table.cellWidget(row, 2) is button)
        camera = self._table.cellWidget(row, 1).currentText() or self._table.item(row, 0).text()
        dialog = QDialog(self)
        dialog.setWindowTitle(self._translator.t("ai_filter_title", camera=camera))
        box = QVBoxLayout(dialog)
        picker = _CodePicker(self._translator, self._translator.t("ai_filter_all"),
                             self._translator.t("ai_filter_help"))
        picker.set_fields(self._label_fields)
        picker.set_choice(*(button.rule or ("", [])))
        box.addWidget(picker)
        buttons = QDialogButtonBox()
        buttons.addButton(self._translator.t("ai_ok"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self._translator.t("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        box.addWidget(buttons)
        dialog.resize(420, 420)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        # Nothing ticked keeps every result: a filter that lets nothing through is never wanted.
        button.rule = (picker.key(), picker.values()) if picker.key() and picker.values() else None
        button.show_rule(self._label_fields)

    def _feed_label(self, host: str, port: str) -> str:
        return f"{host}:{port}" if host else self._translator.t("ai_new_feed")

    def _reload_list(self, select: int | None) -> None:
        self._current = None
        self._list.blockSignals(True)
        self._list.clear()
        for form in self._forms:
            self._list.addItem(self._feed_label(form.host, form.port))
        self._list.blockSignals(False)
        self._form_panel.setEnabled(select is not None)
        if select is not None:
            self._list.setCurrentRow(select)   # emits currentRowChanged -> _select

    def _select(self, row: int) -> None:
        self._store_current()
        if not 0 <= row < len(self._forms):
            return
        self._current = row
        form = self._forms[row]
        self._host.setText(form.host)
        self._port.setText(form.port)
        self._delay.setValue(form.delay_ms)
        self._align.setCurrentIndex(max(self._align.findData(form.align), 0))
        self._table.setRowCount(0)
        for source, camera in form.mapping:
            self._add_row(source, camera)
        self._advanced.setPlainText(form.advanced)
        for row, (source, _camera) in enumerate(form.mapping):
            self._table.cellWidget(row, 2).rule = form.filters.get(source)
        self._refresh_tile_keys()
        self._tile_rows.set_choice(form.tile_key, form.tile_values)

    def _store_current(self) -> None:
        if self._current is None:
            return
        rows = []
        filters = {}
        for row in range(self._table.rowCount()):
            combo = self._table.cellWidget(row, 1)
            source = self._table.item(row, 0).text()
            rows.append((source, (combo.currentData() or "") if isinstance(combo, QComboBox) else ""))
            if self._table.cellWidget(row, 2).rule:
                filters[source.strip()] = self._table.cellWidget(row, 2).rule
        tile_key = self._tile_rows.key()
        self._forms[self._current] = FeedForm(self._host.text().strip(), self._port.text().strip(),
                                              self._delay.value(), rows,
                                              self._advanced.toPlainText(), tile_key,
                                              self._tile_rows.values() if tile_key else [],
                                              self._align.currentData() or ALIGN_AI_TIME, filters)

    def _refresh_current_label(self) -> None:
        if self._current is not None:
            self._list.item(self._current).setText(
                self._feed_label(self._host.text().strip(), self._port.text().strip()))

    def _add_row(self, source: str, camera: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(source))
        combo = QComboBox()
        labels = list(self._camera_names)
        if camera and camera not in labels:
            labels.append(camera)   # keep a mapping to a renamed camera visible, not dropped
        # An unnamed camera's label is its whole URL; the host is what fits and tells them apart.
        for label in labels:
            combo.addItem(short_camera_name(label), label)
            combo.setItemData(combo.count() - 1, label, Qt.ItemDataRole.ToolTipRole)
        combo.setCurrentIndex(labels.index(camera) if camera else -1)
        self._table.setCellWidget(row, 1, combo)
        button = _FilterButton(self._translator)
        button.show_rule(self._label_fields)
        button.clicked.connect(lambda _checked=False, b=button: self._edit_filter(b))
        self._table.setCellWidget(row, 2, button)

    def _add_empty_row(self) -> None:
        """Preselect the first camera that no connection has claimed yet."""
        self._store_current()
        used = {camera for form in self._forms for _source, camera in form.mapping}
        self._add_row("", next((name for name in self._camera_names if name not in used), ""))
        self._table.editItem(self._table.item(self._table.rowCount() - 1, 0))

    def _remove_row(self) -> None:
        if self._table.currentRow() >= 0:
            self._table.removeRow(self._table.currentRow())

    def _add_feed(self) -> None:
        self._store_current()
        template = self._forms[self._current] if self._current is not None else None
        self._forms.append(template.copy_format() if template is not None
                           else FeedForm(advanced=default_advanced()))
        self._reload_list(len(self._forms) - 1)

    def _remove_feed(self) -> None:
        if self._current is None:
            return
        removed = self._current
        self._current = None   # its widgets are stale; do not store them back
        del self._forms[removed]
        self._reload_list(min(removed, len(self._forms) - 1) if self._forms else None)

    def _accept(self) -> None:
        self._store_current()
        if self._current is not None and self._tile_all_sites.isChecked():
            chosen = self._forms[self._current]
            for form in self._forms:
                form.tile_key, form.tile_values = chosen.tile_key, list(chosen.tile_values)
            self.tile_rows_for_all_sites = (chosen.tile_key, tuple(chosen.tile_values))
        try:
            self.result_feeds = feeds_from_forms(self._site_name, self._cameras, self._forms)
        except ValueError as error:
            # A dismissed dialog leaves no trace; the log keeps one.
            logger().warning("ai feeds for site=%s refused: %s", self._site_name, error)
            QMessageBox.critical(self, self._translator.t("ai_feeds_invalid"), str(error))
            return
        self.accept()


def edit_ai_feeds(parent: QWidget, translator: Translator, site_name: str,
                  cameras: Sequence[Camera], feeds: Sequence[AiFeedConfig],
                  ) -> tuple[tuple[AiFeedConfig, ...], tuple[str, tuple[str, ...]] | None] | None:
    """None means cancelled; an empty tuple of feeds means every connection was removed. The
    second item is the (field, codes) under each tile to copy to every other site, if asked."""
    dialog = AiFeedsDialog(parent, translator, site_name, cameras, feeds)
    dialog.setModal(True)
    if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_feeds is None:
        return None
    return dialog.result_feeds, dialog.tile_rows_for_all_sites
