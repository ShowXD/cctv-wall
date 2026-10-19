"""Dialog for a site's AI result connections: address, camera mapping, message format."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QMessageBox, QPlainTextEdit, QPushButton,
                               QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from cctv_wall.ai_feed import (DEFAULT_CAMERA_KEY, DEFAULT_DELAY_MS, DEFAULT_TIME_KEY, MAX_DELAY_MS,
                               AiFeedConfig)
from cctv_wall.event_log import logger
from cctv_wall.i18n import Translator
from cctv_wall.models import Camera, Site

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

    @classmethod
    def from_config(cls, config: AiFeedConfig) -> "FeedForm":
        raw = config.as_dict()
        return cls(config.host, str(config.port), config.delay_ms, list(config.cameras),
                   _advanced_text({key: raw[key] for key in ADVANCED_KEYS if key in raw}))

    def copy_format(self) -> "FeedForm":
        """A new connection usually speaks the same format as the one beside it."""
        return FeedForm(delay_ms=self.delay_ms, advanced=self.advanced)


def _advanced_text(values: dict[str, Any]) -> str:
    return json.dumps(values, ensure_ascii=False, indent=2)


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
    return AiFeedConfig.from_raw({**advanced, "host": form.host, "port": form.port,
                                  "delay_ms": form.delay_ms, "cameras": cameras})


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
        self.setWindowTitle(self._translator.t("ai_feeds_title", site=site_name))
        self.resize(900, 760)
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
        splitter.setSizes([220, 680])
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
        form.addRow(self._translator.t("ai_host"), address)
        form.addRow(self._translator.t("ai_delay"), self._delay)
        box.addWidget(basic)

        mapping = QGroupBox(self._translator.t("ai_camera_map"))
        mapping_box = QVBoxLayout(mapping)
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels([self._translator.t("ai_source_id"),
                                               self._translator.t("ai_camera")])
        self._table.horizontalHeader().setStretchLastSection(True)
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
        box.addWidget(mapping, 2)

        advanced = QGroupBox(self._translator.t("ai_advanced"))
        advanced_box = QVBoxLayout(advanced)
        advanced_help = QLabel(self._translator.t("ai_advanced_help"))
        advanced_help.setObjectName("formHelp")
        advanced_help.setWordWrap(True)
        advanced_box.addWidget(advanced_help)
        self._advanced = QPlainTextEdit()
        self._advanced.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        advanced_box.addWidget(self._advanced)
        box.addWidget(advanced, 1)
        return panel

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
        self._table.setRowCount(0)
        for source, camera in form.mapping:
            self._add_row(source, camera)
        self._advanced.setPlainText(form.advanced)

    def _store_current(self) -> None:
        if self._current is None:
            return
        rows = []
        for row in range(self._table.rowCount()):
            combo = self._table.cellWidget(row, 1)
            rows.append((self._table.item(row, 0).text(),
                         combo.currentText() if isinstance(combo, QComboBox) else ""))
        self._forms[self._current] = FeedForm(self._host.text().strip(), self._port.text().strip(),
                                              self._delay.value(), rows,
                                              self._advanced.toPlainText())

    def _refresh_current_label(self) -> None:
        if self._current is not None:
            self._list.item(self._current).setText(
                self._feed_label(self._host.text().strip(), self._port.text().strip()))

    def _add_row(self, source: str, camera: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(source))
        combo = QComboBox()
        names = list(self._camera_names)
        if camera and camera not in names:
            names.append(camera)   # keep a mapping to a renamed camera visible, not dropped
        combo.addItems(names)
        combo.setCurrentIndex(names.index(camera) if camera else -1)
        self._table.setCellWidget(row, 1, combo)

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
        try:
            self.result_feeds = feeds_from_forms(self._site_name, self._cameras, self._forms)
        except ValueError as error:
            # A dismissed dialog leaves no trace; the log keeps one.
            logger().warning("ai feeds for site=%s refused: %s", self._site_name, error)
            QMessageBox.critical(self, self._translator.t("ai_feeds_invalid"), str(error))
            return
        self.accept()


def edit_ai_feeds(parent: QWidget, translator: Translator, site_name: str,
                  cameras: Sequence[Camera],
                  feeds: Sequence[AiFeedConfig]) -> tuple[AiFeedConfig, ...] | None:
    """None means cancelled; an empty tuple means every connection was removed."""
    dialog = AiFeedsDialog(parent, translator, site_name, cameras, feeds)
    dialog.setModal(True)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.result_feeds
