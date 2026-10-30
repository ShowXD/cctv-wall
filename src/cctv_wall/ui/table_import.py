"""Import cameras from an Excel/CSV sheet, with the operator naming each column, and export them back.

The commands have the site-command shape (parent, workspace, translator, site_name) -> Workspace | None,
so the window dispatches them from SITE_COMMANDS and owns saving and reloading.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from cctv_wall import camera_table, vendors
from cctv_wall.event_log import logger
from cctv_wall.i18n import Translator
from cctv_wall.models import Camera, Site, Workspace

PREVIEW_ROWS = 20
ERRORS_LISTED = 10
FIELD_LABEL_KEYS = {"site": "field_site", "name": "field_name", "url": "field_url",
                    "host": "field_host", "port": "field_port", "stream": "field_stream",
                    "user": "field_user", "password": "field_password"}
FILE_FILTER = "Excel / CSV (*.xlsx *.csv)"
IMPORT_VENDORS = tuple(vendor for vendor in vendors.VENDORS if vendor != vendors.CUSTOM_VENDOR)


class ImportDialog(QDialog):
    """A preview of the sheet with a field picker above every column."""

    def __init__(self, parent: QWidget, translator: Translator, workspace: Workspace,
                 path: str, sheets: Sequence[str], active_sheet: int, default_site: str) -> None:
        super().__init__(parent)
        self._translator = translator
        self._workspace = workspace
        self._path = path
        self._rows: list[list[str]] = []
        self._pickers: list[QComboBox] = []
        self.result_workspace: Workspace | None = None
        self.setWindowTitle(translator.t("import_title"))
        box = QVBoxLayout(self)
        help_label = QLabel(translator.t("import_help"))
        help_label.setObjectName("formHelp")
        help_label.setWordWrap(True)
        box.addWidget(help_label)

        form = QFormLayout()
        # CSV has no worksheets, so the picker only appears for a workbook.
        self._sheet = QComboBox()
        self._sheet.addItems(sheets)
        self._sheet.setCurrentIndex(active_sheet)
        self._sheet.activated.connect(self._sheet_chosen)
        if sheets:
            form.addRow(translator.t("import_sheet"), self._sheet)
        box.addLayout(form)
        self._table = QTableWidget()
        box.addWidget(self._table, 1)

        form = QFormLayout()
        self._header_rows = QSpinBox()
        self._header_rows.valueChanged.connect(self._refresh)
        form.addRow(translator.t("import_header_rows"), self._header_rows)
        self._vendor = QComboBox()
        self._vendor.addItems(IMPORT_VENDORS)
        self._vendor.activated.connect(self._refresh)
        form.addRow(translator.t("import_vendor"), self._vendor)
        self._site = QLineEdit(default_site)
        self._site.textChanged.connect(self._refresh)
        form.addRow(translator.t("import_default_site"), self._site)
        box.addLayout(form)
        self._summary = QLabel()
        box.addWidget(self._summary)

        buttons = QDialogButtonBox()
        self._ok: QPushButton = buttons.addButton(translator.t("import_ok"),
                                                  QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(translator.t("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._import)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        self.resize(900, 560)

    def load(self) -> bool:
        """Read the chosen worksheet (or the CSV) into the preview; False after explaining why not."""
        try:
            rows = camera_table.read_rows(self._path, self._sheet.currentText() or None)
        except (OSError, ValueError) as error:
            logger().warning("could not read %s: %s", self._path, error)
            QMessageBox.warning(self, self._translator.t("import_title"),
                                self._translator.t("import_read_error", error=error))
            return False
        self._rows = rows
        columns = max((len(row) for row in rows), default=0)
        guessed = camera_table.guess_mapping(rows[0]) if rows else {}
        shown = rows[:PREVIEW_ROWS + 1]
        # Row 0 holds the pickers; the sheet's own row numbers follow, so error messages match.
        self._table.clear()
        self._table.setRowCount(len(shown) + 1)
        self._table.setColumnCount(columns)
        self._table.setVerticalHeaderLabels(["", *(str(number) for number in range(1, len(shown) + 1))])
        self._pickers = []
        for column in range(columns):
            picker = QComboBox()
            picker.addItem(self._translator.t("import_skip"), "")
            for field in camera_table.FIELDS:
                picker.addItem(self._translator.t(FIELD_LABEL_KEYS[field]), field)
            chosen = next((field for field, index in guessed.items() if index == column), "")
            picker.setCurrentIndex(picker.findData(chosen))
            picker.activated.connect(self._field_chosen)
            self._table.setCellWidget(0, column, picker)
            self._pickers.append(picker)
        for row_number, row in enumerate(shown, start=1):
            for column, text in enumerate(row):
                self._table.setItem(row_number, column, QTableWidgetItem(text))
        self._table.resizeColumnsToContents()
        self._header_rows.blockSignals(True)
        self._header_rows.setRange(0, len(rows))
        self._header_rows.setValue(1 if guessed else 0)
        self._header_rows.blockSignals(False)
        self._refresh()
        return True

    def _sheet_chosen(self, _index: int) -> None:
        self.load()

    def _field_chosen(self, _index: int) -> None:
        """A field belongs to one column: choosing it here takes it away from the column that had it."""
        chosen = self.sender()
        field = chosen.currentData()
        if field:
            for picker in self._pickers:
                if picker is not chosen and picker.currentData() == field:
                    picker.setCurrentIndex(0)
        self._refresh()

    def mapping(self) -> dict[str, int]:
        return {picker.currentData(): column for column, picker in enumerate(self._pickers)
                if picker.currentData()}

    def parsed(self) -> tuple[list[tuple[str, Camera]], list[tuple[int, str]]]:
        skipped = self._header_rows.value()
        return camera_table.cameras_from_rows(self._rows[skipped:], self.mapping(),
                                              self._vendor.currentText(), self._site.text(),
                                              first_row=skipped + 1)

    def _refresh(self) -> None:
        mapping = self.mapping()
        self._vendor.setEnabled("host" in mapping and "url" not in mapping)
        self._site.setEnabled("site" not in mapping)
        cameras, errors = self.parsed()
        self._summary.setText(self._translator.t("import_summary", count=len(cameras),
                                                 errors=len(errors)))
        self._summary.setProperty("invalid", bool(errors))
        self._summary.style().polish(self._summary)
        self._summary.setToolTip("\n".join(self._translator.t("import_error_line", row=row, error=error)
                                           for row, error in errors[:ERRORS_LISTED]))
        self._ok.setEnabled(bool(cameras))

    def _import(self) -> None:
        cameras, _errors = self.parsed()
        try:
            updated, added = camera_table.merge_into(self._workspace, cameras)
        except ValueError as error:
            # e.g. a duplicate camera name on a site with AI connections
            logger().warning("camera import refused: %s", error)
            QMessageBox.warning(self, self._translator.t("import_title"), str(error))
            return
        if added < len(cameras):
            QMessageBox.information(self, self._translator.t("import_title"),
                                    self._translator.t("import_duplicates", added=added,
                                                       skipped=len(cameras) - added))
        self.result_workspace = updated if added else None
        self.accept()


def import_cameras(parent: QWidget, workspace: Workspace, translator: Translator,
                   site_name: str) -> Workspace | None:
    """Rows without a site column go to `site_name`, or to a new site when there is none."""
    path, _filter = QFileDialog.getOpenFileName(parent, translator.t("import_title"), "", FILE_FILTER)
    if not path:
        return None
    try:
        sheets, active_sheet = camera_table.sheet_names(path)
    except (OSError, ValueError) as error:
        logger().warning("could not read %s: %s", path, error)
        QMessageBox.warning(parent, translator.t("import_title"),
                            translator.t("import_read_error", error=error))
        return None
    default_site = (site_name if workspace.site(site_name) is not None
                    else workspace.unique_site_name(translator.t("untitled_site")))
    dialog = ImportDialog(parent, translator, workspace, path, sheets, active_sheet, default_site)
    dialog.setModal(True)
    if not dialog.load() or dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.result_workspace


def export_cameras(parent: QWidget, workspace: Workspace, translator: Translator,
                   site_name: str) -> None:
    """Export one site's cameras; the workspace never changes, so this always returns None."""
    site = workspace.site(site_name)
    if site is not None:
        _export(parent, translator, (site,), site.name)


def export_all_cameras(parent: QWidget, workspace: Workspace, translator: Translator,
                       site_name: str) -> None:
    _export(parent, translator, workspace.sites, translator.t("export_all_file_name"))


def _export(parent: QWidget, translator: Translator, sites: Iterable[Site], file_name: str) -> None:
    answer = QMessageBox.question(parent, translator.t("export_title"),
                                  translator.t("export_credentials_confirm"),
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No)
    include_credentials = answer == QMessageBox.StandardButton.Yes
    path, _filter = QFileDialog.getSaveFileName(parent, translator.t("export_title"),
                                                f"{file_name}.xlsx", "Excel (*.xlsx);;CSV (*.csv)")
    if not path:
        return
    fields = camera_table.EXPORT_FIELDS if include_credentials else camera_table.EXPORT_FIELDS[:3]
    header = [translator.t(FIELD_LABEL_KEYS[field]) for field in fields]
    try:
        camera_table.write_rows(path, [header, *camera_table.table_rows(sites, include_credentials)])
    except OSError as error:
        logger().warning("could not write %s: %s", path, error)
        QMessageBox.warning(parent, translator.t("export_title"),
                            translator.t("export_write_error", error=error))
