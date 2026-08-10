"""A small, responsive startup window shown while the monitoring wall is prepared."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QProgressBar, QVBoxLayout


class StartupProgress(QDialog):
    """Show meaningful startup stages after the frozen executable has unpacked.

    PyInstaller owns the period before Python starts, so it can only show its own
    native splash while a one-file executable is unpacked.  This widget takes over
    as soon as Qt is available and keeps the user informed about application work.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CCTV Wall")
        self.setObjectName("startupProgress")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setModal(False)
        self.setFixedSize(390, 158)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(9)

        title = QLabel("CCTV WALL")
        title.setObjectName("startupTitle")
        layout.addWidget(title)

        self._status = QLabel()
        self._status.setObjectName("startupStatus")
        layout.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setObjectName("startupBar")
        self._progress.setRange(0, 100)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(9)
        layout.addWidget(self._progress)

    def set_progress(self, value: int, message: str) -> None:
        """Update the visible stage immediately, even before the event loop starts."""
        self._status.setText(message)
        self._progress.setValue(value)
        self.repaint()
        QApplication.processEvents()

    def show_at_center(self) -> None:
        """Show above the native unpacking splash and centre on the active display."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            self.move(screen.availableGeometry().center() - self.rect().center())
        self.show()
        QApplication.processEvents()

    def dismiss(self) -> None:
        """Remove the window synchronously before the main event loop takes over."""
        # `close()` alone can be deferred while QApplication is transitioning into
        # exec(), particularly for a frameless always-on-top tool window on Windows.
        self.hide()
        self.close()
        QApplication.processEvents()
        self.deleteLater()
