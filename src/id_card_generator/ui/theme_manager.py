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
from pathlib import Path
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
    def _get_asset_path(cls, filename: str) -> Path:
        base_dir = getattr(sys, "_MEIPASS", None)
        if base_dir:
            cand = Path(base_dir) / "id_card_generator" / "resources" / "assets" / filename
            if cand.exists():
                return cand
        return Path(__file__).parent.parent / "resources" / "assets" / filename

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

    @classmethod
    def _get_black_stylesheet(cls) -> str:
        """ID Studio Dark Workstation stylesheet (Charcoal Value Ramp)."""
        chevron_dark = cls._get_asset_path("chevron_down_dark.svg").as_posix()
        chevron_up_dark = cls._get_asset_path("chevron_up_dark.svg").as_posix()
        stylesheet = """
/* === ID Studio Dark Workstation Palette === */

* {
    font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    outline: none;
}

QWidget {
    background-color: #111317;
    color: #E2E2E8;
    selection-background-color: #6C8CFF;
    selection-color: #002780;
}

/* Main Window & Dialogs */
QMainWindow, QDialog {
    background-color: #111317;
}

/* Card & Content Panels (Level 2 Containers) */
QFrame#card_panel, QFrame#sidebar_panel, QFrame#canvas_container {
    background-color: #1E2024;
    border: 1px solid #383D47;
    border-radius: 6px;
}

/* Toolbars */
QToolBar {
    background-color: #1A1C20;
    border-bottom: 1px solid #383D47;
    spacing: 4px;
    padding: 3px 8px;
}

QToolBar QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 8px;
    color: #C4C5D5;
    font-size: 12px;
}

QToolBar QToolButton:hover {
    background-color: #282A2E;
    border-color: #383D47;
    color: #E2E2E8;
}

QToolBar QToolButton:pressed, QToolBar QToolButton:checked {
    background-color: #282A2E;
    border-color: #6C8CFF;
    color: #B6C4FF;
}

/* Push Buttons (Utility 28px height) */
QPushButton {
    background-color: #1E2024;
    color: #E2E2E8;
    border: 1px solid #383D47;
    border-radius: 4px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 500;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #282A2E;
    border-color: #444653;
    color: #FFFFFF;
}

QPushButton:pressed {
    background-color: #111317;
    border-color: #6C8CFF;
}

QPushButton:disabled {
    background-color: #1A1C20;
    color: #555760;
    border-color: #282A2E;
}

QPushButton:focus {
    border: 1px solid #6C8CFF;
}

/* Primary Accent Button (Vibrant Studio Blue) */
QPushButton#btn_primary {
    background-color: #6C8CFF;
    color: #002780;
    border: 1px solid #B6C4FF;
    font-weight: 600;
}

QPushButton#btn_primary:hover {
    background-color: #829DFF;
    color: #001550;
    border-color: #DCE1FF;
}

QPushButton#btn_primary:pressed {
    background-color: #006CBE;
}

/* Danger Button */
QPushButton#btn_danger {
    background-color: #93000A;
    color: #FFDAD6;
    border: 1px solid #BA1A1A;
}

QPushButton#btn_danger:hover {
    background-color: #BA1A1A;
}

/* Success Button */
QPushButton#btn_success {
    background-color: #34A673;
    color: #002112;
    border: 1px solid #6EDBA3;
    font-weight: 600;
}

QPushButton#btn_success:hover {
    background-color: #49B883;
}

/* Input Fields */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox {
    background-color: #1A1C20;
    border: 1px solid #383D47;
    border-radius: 4px;
    padding: 3px 6px;
    color: #E2E2E8;
    min-height: 20px;
    font-size: 11px;
}

QComboBox, QFontComboBox {
    padding-right: 20px;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QFontComboBox:focus {
    border: 1px solid #6C8CFF;
    background-color: #1E2024;
}

QComboBox::drop-down, QFontComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: none;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}

QComboBox::down-arrow, QFontComboBox::down-arrow {
    image: url("__CHEVRON_DARK_URL__");
    width: 9px;
    height: 6px;
}

QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {
    background-color: #1E2024;
    border: 1px solid #383D47;
    border-radius: 4px;
    selection-background-color: #282A2E;
    selection-color: #B6C4FF;
    padding: 3px;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    border-left: 1px solid #383D47;
    border-bottom: 1px solid #383D47;
    border-top-right-radius: 4px;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
    background-color: #282A2E;
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    border-left: 1px solid #383D47;
    border-bottom-right-radius: 4px;
}

QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #282A2E;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("__CHEVRON_UP_DARK_URL__");
    width: 8px;
    height: 5px;
}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("__CHEVRON_DARK_URL__");
    width: 8px;
    height: 5px;
}

/* Tables and Lists */
QTableWidget, QTableView, QListWidget, QTreeWidget {
    background-color: #1A1C20;
    border: 1px solid #383D47;
    border-radius: 4px;
    gridline-color: #282A2E;
    color: #E2E2E8;
    font-size: 11px;
}

QTableWidget::item, QListWidget::item {
    padding: 5px 6px;
    border-radius: 3px;
}

QTableWidget::item:selected, QListWidget::item:selected {
    background-color: #282A2E;
    color: #B6C4FF;
    border: 1px solid #6C8CFF;
}

QHeaderView::section {
    background-color: #1E2024;
    color: #A2A8B3;
    padding: 5px 8px;
    border: none;
    border-right: 1px solid #383D47;
    border-bottom: 1px solid #383D47;
    font-weight: 600;
    font-size: 11px;
}

/* Scrollbars */
QScrollBar:vertical {
    background-color: transparent;
    width: 8px;
    margin: 1px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background-color: #383D47;
    min-height: 24px;
    border-radius: 3px;
}

QScrollBar::handle:vertical:hover {
    background-color: #444653;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: transparent;
    height: 8px;
    margin: 1px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background-color: #383D47;
    min-width: 24px;
    border-radius: 3px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #444653;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #383D47;
    background-color: #1A1C20;
    border-radius: 4px;
}

QTabBar::tab {
    background-color: #1E2024;
    color: #A2A8B3;
    border: 1px solid #383D47;
    border-bottom: none;
    padding: 6px 14px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
    font-size: 11px;
}

QTabBar::tab:selected {
    background-color: #282A2E;
    color: #E2E2E8;
    border-bottom: 2px solid #6C8CFF;
}

/* Status Bar */
QStatusBar {
    background-color: #111317;
    color: #A2A8B3;
    border-top: 1px solid #383D47;
    font-size: 11px;
}

/* Progress Bar */
QProgressBar {
    background-color: #1A1C20;
    border: 1px solid #383D47;
    border-radius: 4px;
    text-align: center;
    color: #E2E2E8;
    font-size: 11px;
    font-family: "JetBrains Mono", monospace;
}

QProgressBar::chunk {
    background-color: #6C8CFF;
    border-radius: 3px;
}

/* Splitter Handle */
QSplitter::handle {
    background-color: #282A2E;
}

QSplitter::handle:hover {
    background-color: #6C8CFF;
}

/* Group Boxes */
QGroupBox {
    border: 1px solid #383D47;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: 600;
    color: #E2E2E8;
    font-size: 12px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 4px;
    color: #6C8CFF;
}

/* Segmented Alignment Controls & Formatting Buttons */
QFrame#ctx_align_rect, QFrame#insp_align_rect {
    background-color: #202023;
    border: 1px solid #3F3F46;
    border-radius: 4px;
}
QFrame#ctx_align_rect QToolButton, QFrame#insp_align_rect QToolButton {
    background-color: transparent;
    color: #A1A1AA;
    border: none;
    font-size: 11px;
    font-weight: 500;
}
QFrame#ctx_align_rect QToolButton:hover, QFrame#insp_align_rect QToolButton:hover {
    background-color: #2E2E33;
    color: #FFFFFF;
}
QFrame#ctx_align_rect QToolButton:checked, QFrame#insp_align_rect QToolButton:checked {
    background-color: #0078D4;
    color: #FFFFFF;
    font-weight: 600;
}
QFrame#ctx_align_rect QToolButton#btn_align_left, QFrame#insp_align_rect QToolButton#btn_align_left {
    border-top-left-radius: 3px;
    border-bottom-left-radius: 3px;
    border-right: 1px solid #3F3F46;
}
QFrame#ctx_align_rect QToolButton#btn_align_center, QFrame#insp_align_rect QToolButton#btn_align_center {
    border-radius: 0px;
    border-right: 1px solid #3F3F46;
}
QFrame#ctx_align_rect QToolButton#btn_align_right, QFrame#insp_align_rect QToolButton#btn_align_right {
    border-top-right-radius: 3px;
    border-bottom-right-radius: 3px;
}
QToolButton#ctx_bold_btn, QToolButton#ctx_italic_btn, QToolButton#ctx_color_btn, QToolButton#ctx_fill_btn, QToolButton#ctx_stroke_btn {
    background-color: #262629;
    color: #E4E4E7;
    border: 1px solid #3F3F46;
    border-radius: 4px;
    font-size: 13px;
}
QToolButton#ctx_bold_btn:hover, QToolButton#ctx_italic_btn:hover, QToolButton#ctx_color_btn:hover, QToolButton#ctx_fill_btn:hover, QToolButton#ctx_stroke_btn:hover {
    background-color: #333338;
    border-color: #52525B;
}
QToolButton#ctx_bold_btn:checked, QToolButton#ctx_italic_btn:checked {
    background-color: #0078D4;
    color: #FFFFFF;
    border-color: #005A9E;
}
QToolButton#ctx_color_btn:pressed, QToolButton#ctx_fill_btn:pressed, QToolButton#ctx_stroke_btn:pressed {
    background-color: #202023;
}
"""
        return stylesheet.replace("__CHEVRON_DARK_URL__", chevron_dark).replace("__CHEVRON_UP_DARK_URL__", chevron_up_dark)

    @classmethod
    def _get_white_stylesheet(cls) -> str:
        """Windows 11 Fluent Light / White theme stylesheet."""
        chevron_light = cls._get_asset_path("chevron_down_light.svg").as_posix()
        chevron_up_light = cls._get_asset_path("chevron_up_light.svg").as_posix()
        stylesheet = """
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
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 4px 8px;
    color: #111827;
    min-height: 20px;
}

QComboBox, QFontComboBox {
    padding-right: 24px;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QFontComboBox:focus {
    border: 1px solid #0067C0;
    background-color: #FFFFFF;
}

QComboBox::drop-down, QFontComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left: none;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}

QComboBox::down-arrow, QFontComboBox::down-arrow {
    image: url("__CHEVRON_LIGHT_URL__");
    width: 10px;
    height: 7px;
}

QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    selection-background-color: #0067C0;
    selection-color: #FFFFFF;
    padding: 4px;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border-left: 1px solid #D1D5DB;
    border-bottom: 1px solid #D1D5DB;
    border-top-right-radius: 5px;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
    background-color: #F3F4F6;
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border-left: 1px solid #D1D5DB;
    border-bottom-right-radius: 5px;
}

QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #F3F4F6;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("__CHEVRON_UP_LIGHT_URL__");
    width: 8px;
    height: 5px;
}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("__CHEVRON_LIGHT_URL__");
    width: 8px;
    height: 5px;
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

/* Segmented Alignment Controls & Formatting Buttons */
QFrame#ctx_align_rect, QFrame#insp_align_rect {
    background-color: #F3F4F6;
    border: 1px solid #D1D5DB;
    border-radius: 4px;
}
QFrame#ctx_align_rect QToolButton, QFrame#insp_align_rect QToolButton {
    background-color: transparent;
    color: #4B5563;
    border: none;
    font-size: 11px;
    font-weight: 500;
}
QFrame#ctx_align_rect QToolButton:hover, QFrame#insp_align_rect QToolButton:hover {
    background-color: #E5E7EB;
    color: #111827;
}
QFrame#ctx_align_rect QToolButton:checked, QFrame#insp_align_rect QToolButton:checked {
    background-color: #0067C0;
    color: #FFFFFF;
    font-weight: 600;
}
QFrame#ctx_align_rect QToolButton#btn_align_left, QFrame#insp_align_rect QToolButton#btn_align_left {
    border-top-left-radius: 3px;
    border-bottom-left-radius: 3px;
    border-right: 1px solid #D1D5DB;
}
QFrame#ctx_align_rect QToolButton#btn_align_center, QFrame#insp_align_rect QToolButton#btn_align_center {
    border-radius: 0px;
    border-right: 1px solid #D1D5DB;
}
QFrame#ctx_align_rect QToolButton#btn_align_right, QFrame#insp_align_rect QToolButton#btn_align_right {
    border-top-right-radius: 3px;
    border-bottom-right-radius: 3px;
}
QToolButton#ctx_bold_btn, QToolButton#ctx_italic_btn, QToolButton#ctx_color_btn, QToolButton#ctx_fill_btn, QToolButton#ctx_stroke_btn {
    background-color: #F9FAFB;
    color: #1F2937;
    border: 1px solid #D1D5DB;
    border-radius: 4px;
    font-size: 13px;
}
QToolButton#ctx_bold_btn:hover, QToolButton#ctx_italic_btn:hover, QToolButton#ctx_color_btn:hover, QToolButton#ctx_fill_btn:hover, QToolButton#ctx_stroke_btn:hover {
    background-color: #F3F4F6;
    border-color: #9CA3AF;
}
QToolButton#ctx_bold_btn:checked, QToolButton#ctx_italic_btn:checked {
    background-color: #0067C0;
    color: #FFFFFF;
    border-color: #005A9E;
}
QToolButton#ctx_color_btn:pressed, QToolButton#ctx_fill_btn:pressed, QToolButton#ctx_stroke_btn:pressed {
    background-color: #E5E7EB;
}
"""
        return stylesheet.replace("__CHEVRON_LIGHT_URL__", chevron_light).replace("__CHEVRON_UP_LIGHT_URL__", chevron_up_light)
