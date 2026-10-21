"""One restrained visual system for the monitoring workspace and its dialogs."""

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPalette, QPixmap

DARK_APPLICATION_STYLE = """
* { font-family: "Segoe UI", "Microsoft JhengHei UI", "Noto Sans", sans-serif; font-size: 11pt; }
QMainWindow, QDialog { background: #10151f; color: #edf2f8; }
QSplitter::handle { background: #202938; width: 1px; }

QFrame#siteNavigation { background: #151c28; border: 0; }
QLabel#productName { color: #f5f8fc; font-size: 16pt; font-weight: 750; letter-spacing: 2px; }
QLabel#eyebrow, QLabel#navigationLabel, QLabel#controlLabel {
    color: #7f91aa; font-size: 9pt; font-weight: 700; letter-spacing: 1.2px;
}
QLabel#countBadge { color: #a8b8cd; background: #253247; border-radius: 9px; padding: 1px 7px; }
QTreeWidget#siteList { background: transparent; color: #cdd8e7; border: 0; outline: 0; padding: 0; }
QTreeWidget#siteList::item { border-radius: 7px; padding: 9px 8px; margin: 1px 0; }
QTreeWidget#siteList::item:hover { background: #202c3d; color: #ffffff; }
QTreeWidget#siteList::item:selected { background: #244f76; color: #ffffff; font-weight: 650; }
QPushButton#settingsButton { text-align: left; background: #202c3d; color: #e9f1fb; }
QPushButton#settingsButton:hover { background: #2b3c53; }

QWidget#monitorPanel { background: #10151f; }
QLabel#siteTitle { color: #f7f9fc; font-size: 13pt; font-weight: 700; padding: 0 4px; }
QLabel#resourceStatus { color: #8fa0b7; font-size: 9pt; }
QLabel#liveBadge { color: #78dfad; background: #173a32; border: 1px solid #256047; border-radius: 10px; padding: 4px 9px; font-size: 9pt; font-weight: 700; }
QFrame#controlBar { background: #151c28; border-bottom: 1px solid #202a38; }
QLabel#pageLabel { color: #d7e0eb; min-width: 80px; font-weight: 600; }
QSpinBox#tilesBox { padding: 7px 4px; font-weight: 600; }
QComboBox#languageBox { min-width: 100px; }

QFrame#videoTile { background: #090d14; border: 1px solid #263449; border-radius: 5px; }
QFrame#videoTile:hover { border-color: #4a91c7; }
QWidget#videoSurface, QWidget#focusedSurface { background: #030508; }
QLabel#tileNotice { color: #f3c977; background: #2a2114; padding: 8px 10px; font-size: 10pt; }
QLabel#tileNotice[level='error'] { color: #ff9d9d; background: #321b21; }
QLabel#tileNotice[level='sync'] { color: #9cc7ff; background: #17243a; }
QLabel#tileAi { color: #a9d4ff; background: #13202f; padding: 3px 8px; font-size: 9pt; }
QListWidget#aiEventList { font-size: 9pt; }
QWidget#emptyWall { background: #111924; border: 1px dashed #34445a; border-radius: 10px; }
QLabel#emptyWallTitle { color: #e9eff8; font-size: 16pt; font-weight: 650; }
QLabel#emptyWallDetail { color: #8fa0b7; font-size: 11pt; }

QToolButton, QPushButton { background: #253246; color: #eaf1f9; border: 1px solid #354861; border-radius: 6px; padding: 7px 11px; font-weight: 600; }
QToolButton:hover, QPushButton:hover { background: #30425a; border-color: #4c6d8c; }
QToolButton:checked { background: #6e3f35; border-color: #b86d56; color: #fff7f4; }
QToolButton[feed='connected'], QToolButton[feed='connected']:checked { color: #3fb950; }
QToolButton[feed='partial'], QToolButton[feed='partial']:checked, QToolButton[feed='down'], QToolButton[feed='down']:checked { color: #e3b341; }
QToolButton#pageControl { font-size: 16pt; min-width: 48px; min-height: 40px; padding: 0; }
QToolButton#compactAction { min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px; padding: 0; }
QToolButton#compactAction::menu-indicator { image: none; width: 0px; }
QToolButton#syncAction { min-width: 56px; max-width: 56px; min-height: 40px; max-height: 40px; padding: 0; }
QComboBox, QLineEdit, QSpinBox, QTreeWidget { background: #182231; color: #ebf1f9; border: 1px solid #354861; border-radius: 6px; padding: 7px; selection-background-color: #285a85; }
QListWidget, QTableWidget, QPlainTextEdit { background: #182231; color: #ebf1f9; border: 1px solid #354861; border-radius: 6px; selection-background-color: #285a85; selection-color: #ffffff; }
QTableWidget { gridline-color: #2d3d52; }
QListWidget::indicator, QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #5a7594; border-radius: 3px; background: #101924; }
QListWidget::indicator:checked, QCheckBox::indicator:checked { background: #4493f8; border-color: #4493f8; }
QHeaderView::section { background: #1d2a3b; color: #cbd7e7; border: 0; border-right: 1px solid #2d3d52; border-bottom: 1px solid #2d3d52; padding: 5px 8px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #3a4d66; border-radius: 3px; min-height: 32px; }
QScrollBar::handle:horizontal { background: #3a4d66; border-radius: 3px; min-width: 32px; }
QScrollBar::handle:hover { background: #5a7594; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QComboBox:hover, QLineEdit:hover, QSpinBox:hover { border-color: #4c6d8c; }
QComboBox::drop-down { border: 0; width: 24px; }
QTreeWidget { outline: 0; }
QTreeWidget::item { padding: 5px 8px; border: 0; }
QTreeWidget::item:hover:!selected { background: #202c3d; border: 0; }
QTreeWidget::item:selected, QTreeWidget::item:selected:active, QTreeWidget::item:selected:!active { background: #285a85; color: #ffffff; border: 0; outline: 0; }
QTreeWidget::branch:!has-children, QTreeWidget::branch:!has-children:hover { background: transparent; border-image: none; }
QTreeWidget QLineEdit { min-height: 0; margin: 0; padding: 1px 7px; border: 1px solid #5b9ed0; border-radius: 4px; background: #101924; }
QLabel#formHelp { color: #8b9bb0; line-height: 1.4; }
QLabel[invalid='true'] { color: #ff9d9d; }
QLabel#dialogTitle { color: #f5f8fc; font-size: 17pt; font-weight: 700; padding: 3px 2px 0; }
QLabel#dialogDescription { color: #8fa0b7; font-size: 11pt; padding: 0 2px 8px; }
QGroupBox { color: #cbd7e7; border: 1px solid #2d3d52; border-radius: 7px; margin-top: 12px; padding: 12px 8px 7px; font-weight: 650; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #9eb2c9; }
QMenu { background: #1c2635; color: #edf3fb; border: 1px solid #40536b; border-radius: 7px; padding: 7px; }
QMenu::item { padding: 9px 28px 9px 13px; border-radius: 4px; min-height: 20px; }
QMenu::item:selected { background: #2c618e; }
QMenu::separator { height: 1px; background: #38485d; margin: 6px 8px; }
QDialog#startupProgress { background: #151c28; border: 1px solid #354861; border-radius: 10px; }
QLabel#startupTitle { color: #f5f8fc; font-size: 16pt; font-weight: 750; letter-spacing: 2px; }
QLabel#startupStatus { color: #aabbd0; font-size: 10pt; }
QProgressBar#startupBar { background: #273548; border: 0; border-radius: 4px; }
QProgressBar#startupBar::chunk { background: #3b9bca; border-radius: 4px; }
"""

LIGHT_APPLICATION_STYLE = """
* { font-family: "Segoe UI", "Microsoft JhengHei UI", "Noto Sans", sans-serif; font-size: 11pt; }
QMainWindow, QDialog { background: #f4f7fb; color: #172235; }
QSplitter::handle { background: #d4dce7; width: 1px; }
QFrame#siteNavigation { background: #ffffff; border: 0; }
QLabel#productName { color: #13243b; font-size: 16pt; font-weight: 750; letter-spacing: 2px; }
QLabel#eyebrow, QLabel#navigationLabel, QLabel#controlLabel { color: #667992; font-size: 9pt; font-weight: 700; letter-spacing: 1.2px; }
QLabel#countBadge { color: #40546d; background: #e8eef5; border-radius: 9px; padding: 1px 7px; }
QTreeWidget#siteList { background: transparent; color: #34475f; border: 0; outline: 0; padding: 0; }
QTreeWidget#siteList::item { border-radius: 7px; padding: 9px 8px; margin: 1px 0; }
QTreeWidget#siteList::item:hover { background: #eaf2fa; color: #102d4c; }
QTreeWidget#siteList::item:selected { background: #cfe4f7; color: #123b60; font-weight: 650; }
QPushButton#settingsButton { text-align: left; background: #edf3f8; color: #1d3e60; border-color: #c7d6e5; }
QPushButton#settingsButton:hover { background: #dceaf5; }
QWidget#monitorPanel { background: #f4f7fb; }
QLabel#siteTitle { color: #13243b; font-size: 13pt; font-weight: 700; padding: 0 4px; }
QLabel#resourceStatus { color: #64758c; font-size: 9pt; }
QLabel#liveBadge { color: #14733e; background: #e2f5e9; border: 1px solid #a9d9b8; border-radius: 10px; padding: 4px 9px; font-size: 9pt; font-weight: 700; }
QFrame#controlBar { background: #ffffff; border-bottom: 1px solid #dbe3ed; }
QLabel#pageLabel { color: #354962; min-width: 80px; font-weight: 600; }
QSpinBox#tilesBox { padding: 7px 4px; font-weight: 600; }
QComboBox#languageBox { min-width: 100px; }
QFrame#videoTile { background: #ffffff; border: 1px solid #bdcad9; border-radius: 5px; }
QFrame#videoTile:hover { border-color: #3c85bd; }
QWidget#videoSurface, QWidget#focusedSurface { background: #030508; }
QLabel#tileNotice { color: #a33333; background: #fff0f0; padding: 8px 10px; font-size: 10pt; }
QLabel#tileNotice[level='error'] { color: #a33333; background: #fff0f0; }
QLabel#tileNotice[level='sync'] { color: #1d4f91; background: #eaf2ff; }
QLabel#tileAi { color: #1d4f80; background: #e8f1fa; padding: 3px 8px; font-size: 9pt; }
QListWidget#aiEventList { font-size: 9pt; }
QWidget#emptyWall { background: #ffffff; border: 1px dashed #adbdcf; border-radius: 10px; }
QLabel#emptyWallTitle { color: #24384e; font-size: 16pt; font-weight: 650; }
QLabel#emptyWallDetail { color: #6a7e96; font-size: 11pt; }
QToolButton, QPushButton { background: #edf3f8; color: #1d3e60; border: 1px solid #c7d6e5; border-radius: 6px; padding: 7px 11px; font-weight: 600; }
QToolButton:hover, QPushButton:hover { background: #dceaf5; border-color: #8eafcb; }
QToolButton:checked { background: #ffe1d5; border-color: #d89b80; color: #78351f; }
QToolButton[feed='connected'], QToolButton[feed='connected']:checked { color: #1a7f37; }
QToolButton[feed='partial'], QToolButton[feed='partial']:checked, QToolButton[feed='down'], QToolButton[feed='down']:checked { color: #9a6700; }
QToolButton#pageControl { font-size: 16pt; min-width: 48px; min-height: 40px; padding: 0; }
QToolButton#compactAction { min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px; padding: 0; }
QToolButton#compactAction::menu-indicator { image: none; width: 0px; }
QToolButton#syncAction { min-width: 56px; max-width: 56px; min-height: 40px; max-height: 40px; padding: 0; }
QComboBox, QLineEdit, QSpinBox, QTreeWidget { background: #ffffff; color: #1e3047; border: 1px solid #bdcad9; border-radius: 6px; padding: 7px; selection-background-color: #cfe4f7; }
QListWidget, QTableWidget, QPlainTextEdit { background: #ffffff; color: #1e3047; border: 1px solid #bdcad9; border-radius: 6px; selection-background-color: #cfe4f7; selection-color: #123b60; }
QTableWidget { gridline-color: #dbe3ed; }
QListWidget::indicator, QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #8fa3b8; border-radius: 3px; background: #ffffff; }
QListWidget::indicator:checked, QCheckBox::indicator:checked { background: #2f6fbf; border-color: #2f6fbf; }
QHeaderView::section { background: #eef3f8; color: #344b65; border: 0; border-right: 1px solid #dbe3ed; border-bottom: 1px solid #dbe3ed; padding: 5px 8px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #c3cfdc; border-radius: 3px; min-height: 32px; }
QScrollBar::handle:horizontal { background: #c3cfdc; border-radius: 3px; min-width: 32px; }
QScrollBar::handle:hover { background: #9fb3c8; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QComboBox:hover, QLineEdit:hover, QSpinBox:hover { border-color: #7ca6c9; }
QComboBox::drop-down { border: 0; width: 24px; }
QTreeWidget { outline: 0; }
QTreeWidget::item { padding: 5px 8px; border: 0; }
QTreeWidget::item:hover:!selected { background: #eaf2fa; border: 0; }
QTreeWidget::item:selected, QTreeWidget::item:selected:active, QTreeWidget::item:selected:!active { background: #cfe4f7; color: #123b60; border: 0; outline: 0; }
QTreeWidget::branch:!has-children, QTreeWidget::branch:!has-children:hover { background: transparent; border-image: none; }
QTreeWidget QLineEdit { min-height: 0; margin: 0; padding: 1px 7px; border: 1px solid #5790bd; border-radius: 4px; background: #ffffff; }
QLabel#formHelp { color: #657991; line-height: 1.4; }
QLabel[invalid='true'] { color: #b33a3a; }
QLabel#dialogTitle { color: #13243b; font-size: 17pt; font-weight: 700; padding: 3px 2px 0; }
QLabel#dialogDescription { color: #64758c; font-size: 11pt; padding: 0 2px 8px; }
QGroupBox { color: #344b65; border: 1px solid #cbd7e3; border-radius: 7px; margin-top: 12px; padding: 12px 8px 7px; font-weight: 650; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #526b87; }
QMenu { background: #ffffff; color: #1d3048; border: 1px solid #b8c8d8; border-radius: 7px; padding: 7px; }
QMenu::item { padding: 9px 28px 9px 13px; border-radius: 4px; min-height: 20px; }
QMenu::item:selected { background: #d7eafa; }
QMenu::separator { height: 1px; background: #d7e0e9; margin: 6px 8px; }
QDialog#startupProgress { background: #ffffff; border: 1px solid #c7d6e5; border-radius: 10px; }
QLabel#startupTitle { color: #13243b; font-size: 16pt; font-weight: 750; letter-spacing: 2px; }
QLabel#startupStatus { color: #64758c; font-size: 10pt; }
QProgressBar#startupBar { background: #e1e9f1; border: 0; border-radius: 4px; }
QProgressBar#startupBar::chunk { background: #2f84bc; border-radius: 4px; }
"""


# Asking Qt for the scheme, rather than only swapping the style sheet, also turns the native
# title bar dark or light; the colorSchemeChanged it emits restyles the widgets.
COLOR_SCHEMES = {"system": Qt.ColorScheme.Unknown, "dark": Qt.ColorScheme.Dark,
                 "light": Qt.ColorScheme.Light}


def apply_theme(theme: str) -> None:
    QGuiApplication.styleHints().setColorScheme(COLOR_SCHEMES.get(theme, Qt.ColorScheme.Unknown))


def application_palette(dark: bool) -> QPalette:
    """Widgets the style sheet does not name still paint from the palette. Over remote desktop
    Qt may fall back to an older Windows style whose palette is always light, so the palette
    has to match the theme as well."""
    window, text, base, button, highlight, highlighted, muted = (
        ("#10151f", "#edf2f8", "#182231", "#1d2a3b", "#285a85", "#ffffff", "#8b9bb0") if dark else
        ("#f4f7fb", "#172235", "#ffffff", "#eef3f8", "#cfe4f7", "#123b60", "#6b7c90"))
    palette = QPalette()
    role = QPalette.ColorRole
    for name, colour in ((role.Window, window), (role.WindowText, text), (role.Base, base),
                         (role.AlternateBase, button), (role.Text, text), (role.Button, button),
                         (role.ButtonText, text), (role.Highlight, highlight),
                         (role.HighlightedText, highlighted), (role.ToolTipBase, base),
                         (role.ToolTipText, text), (role.PlaceholderText, muted)):
        palette.setColor(name, QColor(colour))
    for name in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, name, QColor(muted))
    return palette


def application_style(dark: bool) -> str:
    """The style sheet for the effective colour scheme, whether followed or forced."""
    return DARK_APPLICATION_STYLE if dark else LIGHT_APPLICATION_STYLE


def painted_icon(size: int, draw: Callable[[QPainter], None]) -> QIcon:
    """A small antialiased icon; draw() sets its own pen and brush."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw(painter)
    painter.end()
    return QIcon(pixmap)
