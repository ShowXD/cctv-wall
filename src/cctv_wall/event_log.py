"""Persistent, bounded diagnostic log shared by the GUI and playback layer.

Kept free of Qt so the playback and AI-feed modules can log without loading it; the
in-app viewer subscribes with add_listener and moves lines onto its own thread.
"""
from __future__ import annotations

import logging
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

from cctv_wall.repository import default_config_path

LOGGER_NAME = "cctv_wall"
IN_MEMORY_LIMIT = 1_000


class _MemoryHandler(logging.Handler):
    """Keeps the last lines for the in-app viewer and tells listeners about each new one.

    Records arrive on whichever thread logged them, so listeners must be thread-safe.
    Nothing here redacts: callers log Camera.label or redact() URLs themselves.
    """

    def __init__(self) -> None:
        super().__init__()
        self.lines: deque[str] = deque(maxlen=IN_MEMORY_LIMIT)
        self.listeners: list[Callable[[str], None]] = []

    def emit(self, record: logging.LogRecord) -> None:
        line = self.format(record)
        self.lines.append(line)
        for listener in tuple(self.listeners):
            try:
                listener(line)
            except RuntimeError:
                # Logging is diagnostic only; a viewer Qt already destroyed must not fail
                # the code that logged, least of all during shutdown.
                pass


_memory = _MemoryHandler()


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
            # A read-only config directory must not prevent live monitoring; the in-app
            # log still works.
            pass
        _memory.setFormatter(formatter)
        logger.addHandler(_memory)
        logger.setLevel(logging.INFO)
    return target


def logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def live_text() -> str:
    """The bounded in-memory log shown by the GUI, without a disk round-trip."""
    return "\n".join(_memory.lines)


def add_listener(listener: Callable[[str], None]) -> None:
    _memory.listeners.append(listener)


def remove_listener(listener: Callable[[str], None]) -> None:
    if listener in _memory.listeners:
        _memory.listeners.remove(listener)
