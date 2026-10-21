"""The camera fields, shared by the settings window and the single-camera dialog."""
from __future__ import annotations

from typing import Callable, Mapping

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from cctv_wall.event_log import logger
from cctv_wall.i18n import Translator
from cctv_wall.models import Camera, Workspace, split_credentials

CAMERA_FIELDS = ("name", "url", "user", "password")
FIELD_LABEL_KEYS = {"name": "name", "url": "direct_url", "user": "username", "password": "password"}


def changed_fields(camera: Camera, fields: Mapping[str, str]) -> list[str]:
    """Fields that differ once stripped, the way Camera.from_raw will read them."""
    return [key for key in CAMERA_FIELDS
            if fields.get(key, "").strip() != getattr(camera, key).strip()]


class CameraForm(QWidget):
    """Name, RTSP URL, user and password, with one line for what is wrong."""

    submitted = Signal()   # Enter pressed in any field

    def __init__(self, translator: Translator) -> None:
        super().__init__()
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._fields: dict[str, QLineEdit] = {}
        for key in CAMERA_FIELDS:
            field = QLineEdit()
            if key == "password":
                field.setEchoMode(QLineEdit.EchoMode.Password)
            if key == "url":
                field.setPlaceholderText("rtsp://192.168.1.10:554/stream1")
                # Connected before `submitted`: Enter must save the split fields, not the old ones.
                field.returnPressed.connect(self._move_credentials)
                field.editingFinished.connect(self._move_credentials)
            field.returnPressed.connect(self.submitted)
            self._fields[key] = field
            form.addRow(translator.t(FIELD_LABEL_KEYS[key]), field)
            if key == "url":
                hint = QLabel(translator.t("url_credentials_hint"))
                hint.setObjectName("formHelp")
                hint.setWordWrap(True)
                form.addRow("", hint)
        box.addLayout(form)
        self._error = QLabel()
        self._error.setProperty("invalid", True)
        self._error.setWordWrap(True)
        box.addWidget(self._error)

    def _move_credentials(self) -> None:
        """Show a pasted rtsp://user:pass@host/... split at once. Credentials just pasted are the
        ones meant, so they replace the fields (saving alone would keep the fields' old values)."""
        url, user, password = split_credentials(self._fields["url"].text().strip())
        if not user and not password:
            return
        self._fields["url"].setText(url)
        if user:
            self._fields["user"].setText(user)
        if password:
            self._fields["password"].setText(password)

    def set_camera(self, camera: Camera | None) -> None:
        self.set_fields({key: getattr(camera, key) for key in CAMERA_FIELDS} if camera else {})

    def set_fields(self, values: Mapping[str, str]) -> None:
        self._error.clear()
        for key, field in self._fields.items():
            field.setText(values.get(key, ""))

    def fields(self) -> dict[str, str]:
        return {key: field.text() for key, field in self._fields.items()}

    def read_camera(self) -> Camera | None:
        """The camera in the fields, or None after showing why it is not valid."""
        try:
            return Camera.from_raw(self.fields())
        except ValueError as error:
            self.show_error(str(error))
            return None

    def show_error(self, message: str) -> None:
        self._error.setText(message)

    def focus_name(self) -> None:
        self._fields["name"].setFocus()


class CameraDialog(QDialog):
    """Add or edit one camera; `build` turns it into the new workspace or raises ValueError."""

    def __init__(self, parent: QWidget, translator: Translator, camera: Camera | None,
                 build: Callable[[Camera], Workspace]) -> None:
        super().__init__(parent)
        self._build = build
        self.result_workspace: Workspace | None = None
        self.setWindowTitle(translator.t("add_camera" if camera is None else "edit_camera_title"))
        self.setMinimumWidth(520)
        box = QVBoxLayout(self)
        self._form = CameraForm(translator)
        self._form.set_camera(camera)
        self._form.submitted.connect(self._save)
        box.addWidget(self._form)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for text, action in ((translator.t("save_camera"), self._save),
                             (translator.t("cancel"), self.reject)):
            button = QPushButton(text)
            button.clicked.connect(action)
            buttons.addWidget(button)
        box.addLayout(buttons)
        self._form.focus_name()

    def _save(self) -> None:
        camera = self._form.read_camera()
        if camera is None:
            return
        try:
            self.result_workspace = self._build(camera)
        except ValueError as error:
            # e.g. a duplicate camera name on a site with AI connections
            logger().warning("camera change refused: %s", error)
            self._form.show_error(str(error))
            return
        self.accept()


def edit_camera(parent: QWidget, translator: Translator, camera: Camera | None,
                build: Callable[[Camera], Workspace]) -> Workspace | None:
    """None means cancelled."""
    dialog = CameraDialog(parent, translator, camera, build)
    dialog.setModal(True)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.result_workspace
