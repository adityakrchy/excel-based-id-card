"""Centralized Windows 11 Fluent-inspired theme manager.

Provides three selectable themes:
- 'black': Fluent dark theme with charcoal surfaces, high readability, and subtle borders.
- 'white': Fluent light theme with clean surfaces, crisp dark text, and subtle separation.
- 'system': Auto-detects Windows dark/light mode with graceful platform fallback.

Supports instant runtime switching without application restart and persists preferences.
"""

import logging
import platform
import sys
from typing import Optional
from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

SETTINGS_KEY_THEME = "ui/theme_mode"


class ThemeManager(QObject):
    """Manages application themes, runtime switching, and system appearance detection."""

    theme_changed = Signal(str)  # Emits applied effective theme name ("black" or "white")

    _instance: Optional["ThemeManager"] = None

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("CardForge", "ExcelIDCardGenerator")
        self.current_preference: str = self.settings.value(SETTINGS_KEY_THEME, "system")
        self.active_effective_theme: str = "black"

    def get_preference(self) -> str:
        """Get the stored user theme preference ('black', 'white', or 'system')."""
        return self.current_preference

    def set_theme(self, theme_pref: str, app: Optional[QApplication] = None) -> None:
        """Set theme preference and immediately apply it."""
        theme_pref = theme_pref.lower().strip()
        if theme_pref not in ("black", "white", "system"):
            theme_pref = "system"

        self.current_preference = theme_pref
        self.settings.setValue(SETTINGS_KEY_THEME, theme_pref)

        effective_theme = self._resolve_theme(theme_pref)
        self.active_effective_theme = effective_theme

        app_instance = app or QApplication.instance()
        if app_instance:
            self._apply_stylesheet(app_instance, effective_theme)

        self.theme_changed.emit(effective_theme)
        logger.info("Theme switched to preference: %s (effective: %s)", theme_pref, effective_theme)

    def _resolve_theme(self, preference: str) -> str:
        """Resolve 'system' to either 'black' or 'white' based on OS appearance."""
        if preference in ("black", "white"):
            return preference

        # Check Windows system setting
        if platform.system() == "Windows":
            try:
                import winreg
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                    return "white" if value == 1 else "black"
            except Exception as e:
                logger.debug("Could not read Windows theme registry: %s", e)

        # Fallback using Qt palette luminance
        app = QApplication.instance()
        if app:
            window_col = app.palette().color(QPalette.Window)
            if window_col.lightness() > 128:
                return "white"

        # Default fallback is black (Fluent Dark)
        return "black"

    def _apply_stylesheet(self, app: QApplication, effective_theme: str) -> None:
        """Generate and apply Fluent Design stylesheet to application."""
        # Set Windows 11 Segoe UI typography
        font = QFont("Segoe UI", 10)
        font.setStyleHint(QFont.SansSerif)
        app.setFont(font)

        if effective_theme == "black":
            stylesheet = self._get_black_stylesheet()
        else:
            stylesheet = self._get_white_stylesheet()

        app.setStyleSheet(stylesheet)

    @staticmethod
    def _get_black_stylesheet() -> str:
        """Windows 11 Fluent Dark / Black theme stylesheet."""
        return """
/* === Windows 11 Fluent Dark / Black Stylesheet === */

* {
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", "Helvetica Neue", sans-serif;
    outline: none;
}

QWidget {
    background-color: #18181B;
    color: #F4F4F5;
    selection-background-color: #0078D4;
    selection-color: #FFFFFF;
}

/* Main Window & Dialogs */
QMainWindow, QDialog {
    background-color: #121214;
}

/* Card & Content Panels */
QFrame#card_panel, QFrame#sidebar_panel, QFrame#canvas_container {
    background-color: #202023;
    border: 1px solid #2E2E33;
    border-radius: 8px;
}

/* Toolbars */
QToolBar {
    background-color: #1C1C1F;
    border-bottom: 1px solid #2B2B30;
    spacing: 6px;
    padding: 4px;
}

QToolBar QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 6px 10px;
    color: #E4E4E7;
    font-size: 13px;
}

QToolBar QToolButton:hover {
    background-color: #2A2A2E;
    border-color: #3F3F46;
}

QToolBar QToolButton:pressed, QToolBar QToolButton:checked {
    background-color: #333338;
    border-color: #0078D4;
    color: #60CDFF;
}

/* Push Buttons */
QPushButton {
    background-color: #27272A;
    color: #F4F4F5;
    border: 1px solid #3F3F46;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 500;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #323238;
    border-color: #52525B;
}

QPushButton:pressed {
    background-color: #202024;
    border-color: #0078D4;
}

QPushButton:disabled {
    background-color: #1A1A1D;
    color: #52525B;
    border-color: #27272A;
}

QPushButton:focus {
    border: 1px solid #60CDFF;
}

/* Primary Accent Button */
QPushButton#btn_primary {
    background-color: #0078D4;
    color: #FFFFFF;
    border: 1px solid #1084D9;
    font-weight: 600;
}

QPushButton#btn_primary:hover {
    background-color: #1084D9;
    border-color: #2B95E0;
}

QPushButton#btn_primary:pressed {
    background-color: #006CBE;
}

/* Danger Button */
QPushButton#btn_danger {
    background-color: #7F1D1D;
    color: #FEE2E2;
    border: 1px solid #991B1B;
}

QPushButton#btn_danger:hover {
    background-color: #991B1B;
}

/* Input Fields */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #202023;
    border: 1px solid #3F3F46;
    border-radius: 6px;
    padding: 6px 10px;
    color: #F4F4F5;
    min-height: 20px;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #60CDFF;
    background-color: #242428;
}

QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #202023;
    border: 1px solid #3F3F46;
    border-radius: 6px;
    selection-background-color: #0078D4;
    selection-color: #FFFFFF;
    padding: 4px;
}

/* Tables and Lists */
QTableWidget, QTableView, QListWidget, QTreeWidget {
    background-color: #1C1C1F;
    border: 1px solid #2B2B30;
    border-radius: 6px;
    gridline-color: #27272A;
    color: #F4F4F5;
}

QTableWidget::item, QListWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
}

QTableWidget::item:selected, QListWidget::item:selected {
    background-color: #2A3644;
    color: #60CDFF;
    border: 1px solid #0078D4;
}

QHeaderView::section {
    background-color: #202023;
    color: #A1A1AA;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #2B2B30;
    border-bottom: 1px solid #2B2B30;
    font-weight: 600;
}

/* Scrollbars */
QScrollBar:vertical {
    background-color: transparent;
    width: 10px;
    margin: 2px 2px 2px 2px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background-color: #3F3F46;
    min-height: 25px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background-color: #52525B;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: transparent;
    height: 10px;
    margin: 2px 2px 2px 2px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal {
    background-color: #3F3F46;
    min-width: 25px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #52525B;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #2B2B30;
    background-color: #1C1C1F;
    border-radius: 6px;
}

QTabBar::tab {
    background-color: #202023;
    color: #A1A1AA;
    border: 1px solid #2B2B30;
    border-bottom: none;
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #1C1C1F;
    color: #F4F4F5;
    border-bottom: 2px solid #60CDFF;
}

/* Status Bar */
QStatusBar {
    background-color: #141416;
    color: #A1A1AA;
    border-top: 1px solid #27272A;
    font-size: 12px;
}

/* Progress Bar */
QProgressBar {
    background-color: #27272A;
    border: 1px solid #3F3F46;
    border-radius: 5px;
    text-align: center;
    color: #F4F4F5;
    font-size: 12px;
}

QProgressBar::chunk {
    background-color: #0078D4;
    border-radius: 4px;
}

/* Splitter Handle */
QSplitter::handle {
    background-color: #27272A;
}

QSplitter::handle:hover {
    background-color: #0078D4;
}

/* Group Boxes */
QGroupBox {
    border: 1px solid #2B2B30;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 14px;
    font-weight: 600;
    color: #E4E4E7;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #60CDFF;
}
"""

    @staticmethod
    def _get_white_stylesheet() -> str:
        """Windows 11 Fluent Light / White theme stylesheet."""
        return """
/* === Windows 11 Fluent Light / White Stylesheet === */

* {
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", "Helvetica Neue", sans-serif;
    outline: none;
}

QWidget {
    background-color: #F9FAFB;
    color: #111827;
    selection-background-color: #0067C0;
    selection-color: #FFFFFF;
}

/* Main Window & Dialogs */
QMainWindow, QDialog {
    background-color: #F3F4F6;
}

/* Card & Content Panels */
QFrame#card_panel, QFrame#sidebar_panel, QFrame#canvas_container {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
}

/* Toolbars */
QToolBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E5E7EB;
    spacing: 6px;
    padding: 4px;
}

QToolBar QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 6px 10px;
    color: #374151;
    font-size: 13px;
}

QToolBar QToolButton:hover {
    background-color: #F3F4F6;
    border-color: #D1D5DB;
}

QToolBar QToolButton:pressed, QToolBar QToolButton:checked {
    background-color: #E5E7EB;
    border-color: #0067C0;
    color: #0067C0;
}

/* Push Buttons */
QPushButton {
    background-color: #FFFFFF;
    color: #111827;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 500;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #F3F4F6;
    border-color: #9CA3AF;
}

QPushButton:pressed {
    background-color: #E5E7EB;
    border-color: #0067C0;
}

QPushButton:disabled {
    background-color: #F3F4F6;
    color: #9CA3AF;
    border-color: #E5E7EB;
}

QPushButton:focus {
    border: 1px solid #0067C0;
}

/* Primary Accent Button */
QPushButton#btn_primary {
    background-color: #0067C0;
    color: #FFFFFF;
    border: 1px solid #005A9E;
    font-weight: 600;
}

QPushButton#btn_primary:hover {
    background-color: #005A9E;
    border-color: #004578;
}

QPushButton#btn_primary:pressed {
    background-color: #004578;
}

/* Danger Button */
QPushButton#btn_danger {
    background-color: #FEE2E2;
    color: #991B1B;
    border: 1px solid #FCA5A5;
}

QPushButton#btn_danger:hover {
    background-color: #FECACA;
}

/* Input Fields */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 6px 10px;
    color: #111827;
    min-height: 20px;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #0067C0;
    background-color: #FFFFFF;
}

QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    selection-background-color: #0067C0;
    selection-color: #FFFFFF;
    padding: 4px;
}

/* Tables and Lists */
QTableWidget, QTableView, QListWidget, QTreeWidget {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    gridline-color: #F3F4F6;
    color: #111827;
}

QTableWidget::item, QListWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
}

QTableWidget::item:selected, QListWidget::item:selected {
    background-color: #EBF5FF;
    color: #0067C0;
    border: 1px solid #93C5FD;
}

QHeaderView::section {
    background-color: #F3F4F6;
    color: #4B5563;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #E5E7EB;
    border-bottom: 1px solid #E5E7EB;
    font-weight: 600;
}

/* Scrollbars */
QScrollBar:vertical {
    background-color: transparent;
    width: 10px;
    margin: 2px 2px 2px 2px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background-color: #D1D5DB;
    min-height: 25px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background-color: #9CA3AF;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: transparent;
    height: 10px;
    margin: 2px 2px 2px 2px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal {
    background-color: #D1D5DB;
    min-width: 25px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #9CA3AF;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #E5E7EB;
    background-color: #FFFFFF;
    border-radius: 6px;
}

QTabBar::tab {
    background-color: #F3F4F6;
    color: #6B7280;
    border: 1px solid #E5E7EB;
    border-bottom: none;
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #111827;
    border-bottom: 2px solid #0067C0;
}

/* Status Bar */
QStatusBar {
    background-color: #F3F4F6;
    color: #6B7280;
    border-top: 1px solid #E5E7EB;
    font-size: 12px;
}

/* Progress Bar */
QProgressBar {
    background-color: #E5E7EB;
    border: 1px solid #D1D5DB;
    border-radius: 5px;
    text-align: center;
    color: #111827;
    font-size: 12px;
}

QProgressBar::chunk {
    background-color: #0067C0;
    border-radius: 4px;
}

/* Splitter Handle */
QSplitter::handle {
    background-color: #E5E7EB;
}

QSplitter::handle:hover {
    background-color: #0067C0;
}

/* Group Boxes */
QGroupBox {
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 14px;
    font-weight: 600;
    color: #111827;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #0067C0;
}
"""
