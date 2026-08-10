"""Live in-app diagnostics: event records and RTSP timestamp capability checks."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from cctv_wall.event_log import live_buffer, live_text, logger
from cctv_wall.i18n import Translator
from cctv_wall.models import Camera
from cctv_wall.sync_probe import SyncProbeResult, probe_rtsp
from cctv_wall.urls import build_url


class _SyncProbeWorker(QThread):
    """Runs network I/O outside Qt's event loop and only exposes safe result text."""

    progress = Signal(str)
    completed = Signal(object)

    def __init__(self, cameras: tuple[Camera, ...]) -> None:
        super().__init__()
        self._cameras = cameras

    def run(self) -> None:
        results: list[SyncProbeResult] = []
        for index, camera in enumerate(self._cameras, start=1):
            if self.isInterruptionRequested():
                break
            label = camera.name or f"Camera {index}"
            self.progress.emit(f"{index}/{len(self._cameras)}  {label}")
            try:
                result = probe_rtsp(label, build_url(camera))
                results.append(result)
                logger().info("sync diagnostic camera=%s eligible=%s sender_reports=%d%s",
                              label, result.can_strictly_sync, result.sender_reports,
                              f" error={result.error}" if result.error else "")
            except (OSError, ValueError) as error:
                # build_url is normally already validated. Keep a malformed entry from
                # preventing the remaining cameras from being diagnosed.
                results.append(SyncProbeResult(label, rtsp=False, error=str(error)))
        self.completed.emit(results)


def show_log_dialog(parent: QWidget, translator: Translator, cameras: tuple[Camera, ...]) -> None:
    """Show current-session logs immediately, plus an on-demand read-only sync probe."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(translator.t("diagnostics"))
    dialog.resize(860, 540)
    layout = QVBoxLayout(dialog)
    tabs = QTabWidget()
    layout.addWidget(tabs)

    log_page = QWidget()
    log_layout = QVBoxLayout(log_page)
    viewer = QPlainTextEdit()
    viewer.setReadOnly(True)
    viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    log_layout.addWidget(viewer)
    tabs.addTab(log_page, translator.t("logs"))

    def refresh_log() -> None:
        # ``changed`` can already be queued when the modal dialog is being destroyed.
        # Never let that harmless race print a PySide traceback after the window closed.
        try:
            current = live_text()
            if viewer.toPlainText() == current:
                return
            viewer.setPlainText(current or translator.t("no_events"))
            viewer.moveCursor(QTextCursor.MoveOperation.End)
        except RuntimeError:
            return

    buffer = live_buffer()
    buffer.changed.connect(refresh_log)

    def disconnect_live_log(*_unused: object) -> None:
        try:
            buffer.changed.disconnect(refresh_log)
        except (RuntimeError, TypeError):
            pass

    dialog.finished.connect(disconnect_live_log)
    refresh_log()

    sync_page = QWidget()
    sync_layout = QVBoxLayout(sync_page)
    description = QLabel(translator.t("sync_probe_help"))
    description.setWordWrap(True)
    sync_layout.addWidget(description)
    sync_output = QPlainTextEdit()
    sync_output.setReadOnly(True)
    sync_output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    sync_layout.addWidget(sync_output)
    run_probe = QPushButton(translator.t("run_sync_probe"))
    sync_layout.addWidget(run_probe)
    tabs.addTab(sync_page, translator.t("sync_diagnostics"))

    worker: _SyncProbeWorker | None = None

    def report_progress(message: str) -> None:
        sync_output.setPlainText(translator.t("sync_probe_running", camera=message))

    def report_complete(results: list[SyncProbeResult]) -> None:
        sync_output.setPlainText(_format_sync_results(results, translator))
        run_probe.setEnabled(True)
        run_probe.setText(translator.t("run_sync_probe"))

    def clear_worker() -> None:
        nonlocal worker
        worker = None

    def start_probe() -> None:
        nonlocal worker
        if worker is not None:
            return
        run_probe.setEnabled(False)
        run_probe.setText(translator.t("sync_probe_running_button"))
        worker = _SyncProbeWorker(cameras)
        worker.progress.connect(report_progress)
        worker.completed.connect(report_complete)
        worker.finished.connect(clear_worker)
        worker.start()

    run_probe.clicked.connect(start_probe)

    buttons = QHBoxLayout()
    buttons.addStretch(1)
    close_button = QPushButton(translator.t("close"))
    close_button.clicked.connect(dialog.accept)
    buttons.addWidget(close_button)
    layout.addLayout(buttons)
    dialog.exec()
    if worker is not None:
        # One in-flight socket read can take at most SOCKET_TIMEOUT_SECONDS. Waiting here
        # only protects Qt from destroying a live QThread when the dialog is closed.
        worker.requestInterruption()
        worker.wait(4_000)


def _format_sync_results(results: list[SyncProbeResult], translator: Translator) -> str:
    if not results:
        return translator.t("no_cameras")
    lines = [translator.t("sync_probe_result_heading"), ""]
    ready = 0
    for result in results:
        if result.can_strictly_sync:
            ready += 1
            state = translator.t("sync_ready")
        elif result.error:
            state = translator.t("sync_probe_error", error=result.error)
        else:
            state = translator.t("sync_unavailable")
        details = []
        if result.codec:
            details.append(result.codec)
        if result.clock_rate:
            details.append(f"{result.clock_rate} Hz")
        if result.sender_reports:
            details.append(translator.t("sender_reports", count=result.sender_reports))
        lines.append(f"{result.camera_label}\n  {state}" +
                     (f"\n  {' · '.join(details)}" if details else ""))
    lines.extend(("", translator.t("sync_probe_summary", ready=ready, total=len(results))))
    return "\n".join(lines)
