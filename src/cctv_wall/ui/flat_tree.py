"""A two-level tree that draws its own hierarchy inside each row.

The native Windows 11 style paints a selected row's background into the branch
(indentation) column as a separate rounded block, and no stylesheet rule reaches it.
Turning that column off and indenting/marking rows ourselves keeps one clean
selection shape in every style.
"""
from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex
from PySide6.QtGui import QKeySequence, QMouseEvent, QShortcut
from PySide6.QtWidgets import (QStyledItemDelegate, QStyleOptionViewItem, QToolButton, QTreeWidget,
                               QTreeWidgetItem, QWidget)

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
        # The drawn arrow depends on the expanded state, so repaint when it changes. Bound
        # methods, not lambdas holding self: see ai_feed_editor._CodePicker.
        self.itemExpanded.connect(self._repaint_arrows)
        self.itemCollapsed.connect(self._repaint_arrows)

    def _repaint_arrows(self, _item: QTreeWidgetItem) -> None:
        self.viewport().update()

    def fold_all(self, expanded: bool) -> None:
        """Open or close every top-level row. Signals stay blocked: collapsing a site moves the
        current row from a hidden camera to its site, which the side list would read as the
        operator picking that site and change what the wall shows."""
        self.blockSignals(True)
        if expanded:
            self.expandAll()
        else:
            self.collapseAll()
        self.blockSignals(False)
        self.viewport().update()

    def collapse_all(self) -> None:
        self.fold_all(False)

    def expand_all(self) -> None:
        self.fold_all(True)

    def toggle_fold(self) -> None:
        """Close everything when any row is open, otherwise open everything."""
        items = (self.topLevelItem(index) for index in range(self.topLevelItemCount()))
        self.fold_all(not any(item.isExpanded() for item in items))

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


def fold_button(tree: FlatTree, tooltip: str, owner: QWidget) -> QToolButton:
    """A small button that collapses or opens every row, plus Ctrl+Shift+Left / Right anywhere
    in the window that holds `owner` (the side list is rarely focused while watching the wall)."""
    button = QToolButton()
    button.setObjectName("foldButton")
    button.setText("⇕")
    button.setToolTip(tooltip)
    button.setAutoRaise(True)
    button.clicked.connect(tree.toggle_fold)
    for keys, action in (("Ctrl+Shift+Left", tree.collapse_all), ("Ctrl+Shift+Right", tree.expand_all)):
        shortcut = QShortcut(QKeySequence(keys), owner)
        shortcut.activated.connect(action)
    return button
