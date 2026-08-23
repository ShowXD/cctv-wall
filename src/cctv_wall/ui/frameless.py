"""Drag and resize strips for a borderless wall window.

Embedded native video swallows mouse events, so the window edges are covered by
Qt-owned widgets that move or resize the window themselves.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

RESIZE_BORDER = 6
_RESIZE_STRIP = 3


def _cursor_for(edges: Qt.Edges) -> Qt.CursorShape:
    horizontal = bool(edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge))
    vertical = bool(edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge))
    if horizontal and vertical:
        opposite = bool(edges & Qt.Edge.TopEdge) == bool(edges & Qt.Edge.LeftEdge)
        return Qt.CursorShape.SizeFDiagCursor if opposite else Qt.CursorShape.SizeBDiagCursor
    if horizontal:
        return Qt.CursorShape.SizeHorCursor
    if vertical:
        return Qt.CursorShape.SizeVerCursor
    return Qt.CursorShape.SizeAllCursor


class _Grip(QWidget):
    """One transparent strip that reports its gesture to the owning set."""

    def __init__(self, window: QWidget, owner: "FramelessGrips", edges: Qt.Edges) -> None:
        super().__init__(window)
        self._owner = owner
        self._edges = edges
        self.setStyleSheet("background: transparent;")
        self.setCursor(_cursor_for(edges))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner.begin(self._edges, event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._owner.drag_to(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner.end()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class FramelessGrips:
    """The nine strips around a window: one to move it, eight to resize it."""

    def __init__(self, window: QWidget) -> None:
        self._window = window
        self._move = _Grip(window, self, Qt.Edges())
        self._edges = tuple(_Grip(window, self, edges) for edges in (
            Qt.Edge.TopEdge, Qt.Edge.BottomEdge, Qt.Edge.LeftEdge, Qt.Edge.RightEdge,
            Qt.Edge.TopEdge | Qt.Edge.LeftEdge, Qt.Edge.TopEdge | Qt.Edge.RightEdge,
            Qt.Edge.BottomEdge | Qt.Edge.LeftEdge, Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
        ))
        self._origin: QPoint | None = None
        self._geometry: QRect | None = None
        self._dragging = Qt.Edges()
        self.relayout()
        self.set_visible(False)

    def relayout(self) -> None:
        border, strip = RESIZE_BORDER, _RESIZE_STRIP
        width, height = self._window.width(), self._window.height()
        span, column = max(0, width - border * 2), max(0, height - border * 2)
        far_x, far_y = max(0, width - border), max(0, height - border)
        # The outer strip resizes and the one just inside it drags; overlapping them
        # would let the resize edge swallow the move gesture.
        self._move.setGeometry(border, strip, span, border)
        for grip, rectangle in zip(self._edges, (
            (border, 0, span, strip), (border, far_y, span, border),
            (0, border, border, column), (far_x, border, border, column),
            (0, 0, border, border), (far_x, 0, border, border),
            (0, far_y, border, border), (far_x, far_y, border, border),
        )):
            grip.setGeometry(*rectangle)
        for grip in self._all:
            grip.raise_()

    def set_visible(self, visible: bool) -> None:
        for grip in self._all:
            grip.setVisible(visible)

    def begin(self, edges: Qt.Edges, position: QPoint) -> None:
        self._origin = position
        self._geometry = self._window.geometry()
        self._dragging = edges

    def drag_to(self, position: QPoint) -> None:
        if self._origin is None or self._geometry is None:
            return
        delta = position - self._origin
        original = self._geometry
        if not self._dragging:
            self._window.move(original.topLeft() + delta)
            return
        left, top = original.left(), original.top()
        right, bottom = original.right(), original.bottom()
        least_width, least_height = self._window.minimumWidth(), self._window.minimumHeight()
        if self._dragging & Qt.Edge.LeftEdge:
            left = min(left + delta.x(), right - least_width + 1)
        if self._dragging & Qt.Edge.RightEdge:
            right = max(right + delta.x(), left + least_width - 1)
        if self._dragging & Qt.Edge.TopEdge:
            top = min(top + delta.y(), bottom - least_height + 1)
        if self._dragging & Qt.Edge.BottomEdge:
            bottom = max(bottom + delta.y(), top + least_height - 1)
        self._window.setGeometry(left, top, right - left + 1, bottom - top + 1)

    def end(self) -> None:
        self._origin = None
        self._geometry = None

    @property
    def _all(self) -> tuple[_Grip, ...]:
        return (self._move, *self._edges)
