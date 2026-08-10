"""Persistent, bounded diagnostic log shared by the GUI and playback layer."""
from __future__ import annotations

import logging
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from cctv_wall.repository import default_config_path

LOGGER_NAME = "cctv_wall"
IN_MEMORY_LIMIT = 1_000


class _LiveLogBuffer(QObject):
    """Small, thread-safe-by-signal mirror of the persistent diagnostic log."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._lines: deque[str] = deque(maxlen=IN_MEMORY_LIMIT)

    def append(self, line: str) -> None:
        self._lines.append(line)
        self.changed.emit()

    def text(self) -> str:
        return "\n".join(self._lines)


_live_buffer = _LiveLogBuffer()


class _GuiLogHandler(logging.Handler):
    """Feeds records to the in-app viewer without exposing URLs or credentials."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _live_buffer.append(self.format(record))
        except (RuntimeError, ValueError):
            # Logging is diagnostic only.  In particular, shutdown must never fail because
            # Qt has already destroyed the receiver.
            pass


def path() -> Path:
    return default_config_path().with_name("cctv-wall.log")


def configure() -> Path:
    target = path()
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(target, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        except OSError:
            # A read-only config directory must not prevent live monitoring.  The GUI
            # buffer remains available and is intentionally preferable to a crash.
            pass
        gui_handler = _GuiLogHandler()
        gui_handler.setFormatter(formatter)
        logger.addHandler(gui_handler)
        logger.setLevel(logging.INFO)
    return target


def logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def live_text() -> str:
    """The bounded in-memory log shown by the GUI, without a disk round-trip."""
    return _live_buffer.text()


def live_buffer() -> _LiveLogBuffer:
    """Expose change notifications to presentation code, not the mutable storage."""
    return _live_buffer
