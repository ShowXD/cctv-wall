"""A two-level tree that draws its own hierarchy inside each row.

The native Windows 11 style paints a selected row's background into the branch
(indentation) column as a separate rounded block, and no stylesheet rule reaches it.
Turning that column off and indenting/marking rows ourselves keeps one clean
selection shape in every style.
"""
from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QTreeWidget, QWidget

CHILD_INDENT = 22
ARROW_WIDTH = 28   # click area at the left of a top-level row that toggles it


class FlatTreeDelegate(QStyledItemDelegate):
    def __init__(self, tree: QTreeWidget) -> None:
        super().__init__(tree)
        self._tree = tree

    def initStyleOption(self, option: QStyleOptionViewItem,
                        index: QModelIndex | QPersistentModelIndex) -> None:
        super().initStyleOption(option, index)
        if index.parent().isValid():
            option.rect.adjust(CHILD_INDENT, 0, 0, 0)
        else:
            expanded = self._tree.isExpanded(index) and self._tree.model().hasChildren(index)
            arrow = "▾" if expanded else "▸"
            option.text = f"{arrow}  {option.text}"

    def updateEditorGeometry(self, editor: QWidget, option: QStyleOptionViewItem,
                             index: QModelIndex | QPersistentModelIndex) -> None:
        # Center the rename field inside the tall rows, aligned with the drawn text.
        rect = option.rect.adjusted(3, 0, -3, 0)
        if index.parent().isValid():
            rect.adjust(CHILD_INDENT, 0, 0, 0)
        height = min(30, max(1, rect.height() - 8))
        editor.setGeometry(rect.x(), rect.y() + (rect.height() - height) // 2, rect.width(), height)


class FlatTree(QTreeWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)
        self.setIndentation(0)
        self.setItemDelegate(FlatTreeDelegate(self))
        # The drawn arrow depends on the expanded state, so repaint when it changes.
        self.itemExpanded.connect(lambda _item: self.viewport().update())
        self.itemCollapsed.connect(lambda _item: self.viewport().update())

    def collapsed_top_level_texts(self) -> frozenset[str]:
        """Remember only what was collapsed, so a newly added row still opens after a rebuild."""
        items = (self.topLevelItem(index) for index in range(self.topLevelItemCount()))
        return frozenset(item.text(0) for item in items if not item.isExpanded())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        item = self.itemAt(event.position().toPoint())
        if (item is not None and item.parent() is None and item.childCount()
                and event.position().x() < ARROW_WIDTH):
            item.setExpanded(not item.isExpanded())
            event.accept()
            return
        super().mousePressEvent(event)
