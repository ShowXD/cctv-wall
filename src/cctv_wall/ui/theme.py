"""One restrained visual system for the monitoring workspace and its dialogs."""

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
QComboBox#profileBox { min-width: 190px; }
QComboBox#languageBox { min-width: 100px; }

QFrame#videoTile { background: #090d14; border: 1px solid #263449; border-radius: 5px; }
QFrame#videoTile:hover { border-color: #4a91c7; }
QWidget#videoSurface, QWidget#focusedSurface { background: #030508; }
QLabel#tileNotice { color: #f3c977; background: #2a2114; padding: 8px 10px; font-size: 10pt; }
QLabel#tileNotice[level='error'] { color: #ff9d9d; background: #321b21; }
QFrame#videoTile[listening='true'] { border-color: #58c07a; }
QLabel#tileAudio { color: #9fe8b6; background: #14251a; padding: 4px 8px; font-size: 9pt; }
QLabel#tileAi { color: #a9d4ff; background: #13202f; padding: 3px 8px; font-size: 9pt; }
QListWidget#aiEventList { font-size: 9pt; }
QLabel#aiStatus[connected='false'] { color: #f3c977; }
QWidget#emptyWall { background: #111924; border: 1px dashed #34445a; border-radius: 10px; }
QLabel#emptyWallTitle { color: #e9eff8; font-size: 16pt; font-weight: 650; }
QLabel#emptyWallDetail { color: #8fa0b7; font-size: 11pt; }

QToolButton, QPushButton { background: #253246; color: #eaf1f9; border: 1px solid #354861; border-radius: 6px; padding: 7px 11px; font-weight: 600; }
QToolButton:hover, QPushButton:hover { background: #30425a; border-color: #4c6d8c; }
QToolButton:checked { background: #6e3f35; border-color: #b86d56; color: #fff7f4; }
QToolButton#pageControl { font-size: 16pt; min-width: 48px; min-height: 40px; padding: 0; }
QToolButton#compactAction { min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px; padding: 0; }
QToolButton#syncAction { min-width: 56px; max-width: 56px; min-height: 40px; max-height: 40px; padding: 0; }
QComboBox, QLineEdit, QTreeWidget { background: #182231; color: #ebf1f9; border: 1px solid #354861; border-radius: 6px; padding: 7px; selection-background-color: #285a85; }
QComboBox:hover, QLineEdit:hover { border-color: #4c6d8c; }
QComboBox::drop-down { border: 0; width: 24px; }
QTreeWidget { outline: 0; }
QTreeWidget::item { padding: 5px 8px; border: 0; }
QTreeWidget::item:hover:!selected { background: #202c3d; border: 0; }
QTreeWidget::item:selected, QTreeWidget::item:selected:active, QTreeWidget::item:selected:!active { background: #285a85; border: 0; outline: 0; }
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
QComboBox#profileBox { min-width: 190px; }
QComboBox#languageBox { min-width: 100px; }
QFrame#videoTile { background: #ffffff; border: 1px solid #bdcad9; border-radius: 5px; }
QFrame#videoTile:hover { border-color: #3c85bd; }
QWidget#videoSurface, QWidget#focusedSurface { background: #030508; }
QLabel#tileNotice { color: #a33333; background: #fff0f0; padding: 8px 10px; font-size: 10pt; }
QLabel#tileNotice[level='error'] { color: #a33333; background: #fff0f0; }
QFrame#videoTile[listening='true'] { border-color: #2f9e57; }
QLabel#tileAudio { color: #1c6b3c; background: #eaf7ee; padding: 4px 8px; font-size: 9pt; }
QLabel#tileAi { color: #1d4f80; background: #e8f1fa; padding: 3px 8px; font-size: 9pt; }
QListWidget#aiEventList { font-size: 9pt; }
QLabel#aiStatus[connected='false'] { color: #a35f00; }
QWidget#emptyWall { background: #ffffff; border: 1px dashed #adbdcf; border-radius: 10px; }
QLabel#emptyWallTitle { color: #24384e; font-size: 16pt; font-weight: 650; }
QLabel#emptyWallDetail { color: #6a7e96; font-size: 11pt; }
QToolButton, QPushButton { background: #edf3f8; color: #1d3e60; border: 1px solid #c7d6e5; border-radius: 6px; padding: 7px 11px; font-weight: 600; }
QToolButton:hover, QPushButton:hover { background: #dceaf5; border-color: #8eafcb; }
QToolButton:checked { background: #ffe1d5; border-color: #d89b80; color: #78351f; }
QToolButton#pageControl { font-size: 16pt; min-width: 48px; min-height: 40px; padding: 0; }
QToolButton#compactAction { min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px; padding: 0; }
QToolButton#syncAction { min-width: 56px; max-width: 56px; min-height: 40px; max-height: 40px; padding: 0; }
QComboBox, QLineEdit, QTreeWidget { background: #ffffff; color: #1e3047; border: 1px solid #bdcad9; border-radius: 6px; padding: 7px; selection-background-color: #cfe4f7; }
QComboBox:hover, QLineEdit:hover { border-color: #7ca6c9; }
QComboBox::drop-down { border: 0; width: 24px; }
QTreeWidget { outline: 0; }
QTreeWidget::item { padding: 5px 8px; border: 0; }
QTreeWidget::item:hover:!selected { background: #eaf2fa; border: 0; }
QTreeWidget::item:selected, QTreeWidget::item:selected:active, QTreeWidget::item:selected:!active { background: #cfe4f7; border: 0; outline: 0; }
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


def application_style(dark: bool) -> str:
    """Return an entire palette so every custom component follows the system appearance."""
    return DARK_APPLICATION_STYLE if dark else LIGHT_APPLICATION_STYLE
