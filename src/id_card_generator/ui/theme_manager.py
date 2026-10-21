"""Centralized theme manager for the ID Studio workstation.

The application ships with a dark "workstation" theme and a light "paper"
theme.  Both are rendered from the shared design tokens in
:mod:`id_card_generator.ui.studio_tokens`, so the two themes always expose
exactly the same widget vocabulary and the reusable components in
:mod:`id_card_generator.ui.components` look identical in both.
"""

import logging
import platform
import re
import sys
from pathlib import Path
from string import Template
from typing import Optional
from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from id_card_generator.ui.studio_tokens import (
    LightStudioColors,
    StudioColors,
    TYPOGRAPHY,
    palette_for,
)

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
        if theme_pref in ("dark", "black"):
            theme_pref = "black"
        elif theme_pref in ("light", "white"):
            theme_pref = "white"
        elif theme_pref != "system":
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
            except Exception as e:  # pragma: no cover - platform specific
                logger.debug("Could not read Windows theme registry: %s", e)

        # Fallback using Qt palette luminance
        app = QApplication.instance()
        if app:
            window_col = app.palette().color(QPalette.Window)
            if window_col.lightness() > 128:
                return "white"

        return "black"

    def _apply_stylesheet(self, app: QApplication, effective_theme: str) -> None:
        """Generate and apply the token-driven stylesheet to the application."""
        # The application font uses the same stack as the stylesheet, so a
        # widget that is painted by the style (a push button for example)
        # shows the same glyphs as one that is painted by the stylesheet.
        font = QFont(self._ui_font_family(), 10)
        font.setStyleHint(QFont.SansSerif)
        app.setFont(font)
        app.setStyleSheet(self.build_stylesheet(effective_theme))

    @staticmethod
    def _ui_font_family() -> str:
        """Return the first installed family of the UI font stack.

        A font stack is only understood by the stylesheet parser - a
        :class:`QFont` takes a single family.  Picking the first family that
        is really installed keeps the widgets and the stylesheet on the same
        font, and every glyph (the "+" of the zoom buttons for example) is
        drawn by the same face.
        """
        return ThemeManager._first_installed_family(TYPOGRAPHY.FONT_FAMILY_UI)

    @staticmethod
    def _mono_font_family() -> str:
        """Return the first installed family of the mono font stack."""
        return ThemeManager._first_installed_family(TYPOGRAPHY.FONT_FAMILY_MONO)

    @staticmethod
    def _first_installed_family(stack: str) -> str:
        """Return the first family of a font stack that is really installed."""
        fallback = stack.split(",")[0].strip().strip("\"'")

        # The font database is only available once an application exists.
        if QGuiApplication.instance() is None:
            return fallback

        try:
            installed = set(QFontDatabase.families())
        except Exception:  # pragma: no cover - no database available
            return fallback

        for candidate in stack.split(","):
            name = candidate.strip().strip("\"'")
            if name in installed:
                return name

        # Nothing of the stack is installed - keep the first entry so the
        # browser of the system can still substitute a face.
        return fallback

    @classmethod
    def retarget_stylesheet(cls, stylesheet: str, theme: str = "black") -> str:
        """Map legacy hard coded colours onto the current palette.

        Older widgets still carry hard coded dark hex values in their inline
        stylesheets.  Rewriting them keeps the light theme readable while the
        pages are migrated to the design tokens.
        """
        if not stylesheet:
            return stylesheet
        values = cls._legacy_values(theme)
        for legacy, token in cls.LEGACY_COLOR_MAP.items():
            value = values[token[1:]]
            if legacy in stylesheet.lower():
                stylesheet = re.sub(
                    re.escape(legacy), value, stylesheet, flags=re.IGNORECASE
                )
        return stylesheet

    @classmethod
    def retarget_widget(cls, widget, theme: str = "black") -> None:
        """Rewrite the inline stylesheet of a widget for the given theme.

        The original stylesheet is remembered so switching back and forth
        between the themes never degrades the result.
        """
        if widget.property("theme_managed"):
            return
        original = widget.property("original_stylesheet")
        if original is None:
            original = widget.styleSheet()
            if not original:
                return
            widget.setProperty("original_stylesheet", original)
        retargeted = cls.retarget_stylesheet(original, theme)
        if retargeted != widget.styleSheet():
            widget.setStyleSheet(retargeted)

    # Legacy dark palette values -> token names.
    LEGACY_COLOR_MAP = {
        "#111317": "$surface",
        "#0f1115": "$surface_dim",
        "#0c0e12": "$surface_lowest",
        "#1a1c20": "$surface_low",
        "#1e2024": "$surface_container",
        "#282a2e": "$surface_high",
        "#333539": "$surface_highest",
        "#202023": "$surface_low",
        "#262629": "$surface_container",
        "#2e2e33": "$surface_high",
        "#333338": "$surface_highest",
        "#27272a": "$surface_container",
        "#14171e": "$surface_low",
        "#1a1e27": "$surface_high",
        "#252934": "$border",
        "#2b303c": "$border",
        "#383d47": "$border",
        "#3f3f46": "$border",
        "#282c34": "$border_subtle",
        "#52525b": "$outline_variant",
        "#e2e2e8": "$on_surface",
        "#c4c5d5": "$on_surface_variant",
        "#c4c6d1": "$on_surface_variant",
        "#8e909f": "$text_muted",
        "#a2a8b3": "$text_muted",
        "#a1a1aa": "$text_muted",
        "#7e8494": "$text_muted",
        "#6c7280": "$text_muted",
        "#64748b": "$text_muted",
        "#6c8cff": "$primary_container",
        "#0078d4": "$primary_container",
        "#005a9e": "$primary_container",
        "#b6c4ff": "$primary",
        "#85a3ff": "$primary",
        "#38bdf8": "$primary",
        "#60cdff": "$primary",
    }

    @classmethod
    def _legacy_values(cls, theme: str = "black") -> dict:
        """Return the token values the legacy map resolves to."""
        p = palette_for(theme)
        return {
            "surface": p.SURFACE,
            "surface_dim": p.SURFACE_DIM,
            "surface_lowest": p.SURFACE_LOWEST,
            "surface_low": p.SURFACE_LOW,
            "surface_container": p.SURFACE_CONTAINER,
            "surface_high": p.SURFACE_HIGH,
            "surface_highest": p.SURFACE_HIGHEST,
            "border": p.BORDER_HAIRLINE,
            "border_subtle": p.BORDER_SUBTLE,
            "outline_variant": p.OUTLINE_VARIANT,
            "on_surface": p.ON_SURFACE,
            "on_surface_variant": p.ON_SURFACE_VARIANT,
            "text_muted": p.TEXT_MUTED,
            "primary": p.PRIMARY,
            "primary_container": p.PRIMARY_CONTAINER,
        }

    # ------------------------------------------------------------------
    # Stylesheet generation
    # ------------------------------------------------------------------
    @classmethod
    def chevron_icon(cls, down: bool = True, theme: str = "black"):
        """Return the chevron icon used by dropdown buttons."""
        from PySide6.QtGui import QIcon

        if down:
            name = "chevron_down_dark.svg" if theme == "black" else "chevron_down_light.svg"
        else:
            name = "chevron_up_dark.svg" if theme == "black" else "chevron_up_light.svg"
        return QIcon(cls._get_asset_path(name).as_posix())

    @classmethod
    def build_stylesheet(cls, theme: str = "black") -> str:
        """Return the full application stylesheet for the given theme."""
        palette = palette_for(theme)
        chevron = cls._get_asset_path(
            "chevron_down_light.svg" if theme == "white" else "chevron_down_dark.svg"
        ).as_posix()
        chevron_up = cls._get_asset_path(
            "chevron_up_light.svg" if theme == "white" else "chevron_up_dark.svg"
        ).as_posix()
        return cls._render_stylesheet(palette, chevron, chevron_up)

    @classmethod
    def _get_black_stylesheet(cls) -> str:
        """Backwards compatible accessor for the dark theme stylesheet."""
        return cls.build_stylesheet("black")

    @classmethod
    def _get_white_stylesheet(cls) -> str:
        """Backwards compatible accessor for the light theme stylesheet."""
        return cls.build_stylesheet("white")

    @classmethod
    def _render_stylesheet(
        cls,
        p: StudioColors,
        chevron_down: str,
        chevron_up: str,
    ) -> str:
        """Render the widget stylesheet from a palette."""
        template = """
/* === ID Studio :: generated from design tokens === */

* {
    font-family: $ui_font;
    outline: none;
}

QWidget {
    background-color: $surface;
    color: $on_surface;
    selection-background-color: $primary;
    selection-color: $on_primary;
}

QMainWindow, QDialog {
    background-color: $surface;
}

/* Plain layout containers never paint a surface of their own, so they can
   be dropped into any panel without showing a darker rectangle. */
QWidget[role="flat"] {
    background-color: transparent;
}

/* Choice controls are drawn by the style, not by a surface. */
QRadioButton, QCheckBox {
    background-color: transparent;
}

/* --- Surfaces --------------------------------------------------- */
QFrame#card_panel, QFrame#sidebar_panel, QFrame#canvas_container,
QFrame#studio_surface, QFrame#surface_card, QFrame#studio_header_bar,
QFrame#studio_nav_bar, QFrame#page_footer, QFrame#page_header {
    background-color: $surface_container;
    border: 1px solid $border;
    border-radius: $radius;
}

QFrame#workspace_panel {
    background-color: $surface_low;
    border: 1px solid $border;
    border-radius: $radius;
}

QFrame#recessed_panel {
    background-color: $surface_lowest;
    border: 1px solid $border;
    border-radius: $radius;
}

QFrame#studio_header_bar {
    background-color: $surface_dim;
    border-top-left-radius: 0px;
    border-top-right-radius: 0px;
    border-bottom: 1px solid $border;
}

QFrame#studio_nav_bar {
    background-color: $surface;
    border-top-left-radius: 0px;
    border-top-right-radius: 0px;
    border-bottom: 1px solid $border;
}

QFrame#page_header {
    background-color: $surface;
    border: none;
    border-bottom: 1px solid $border;
}

QFrame#page_footer {
    background-color: $surface;
    border: none;
    border-top: 1px solid $border;
}

QFrame#canvas_container {
    background-color: $canvas_backdrop;
}

/* --- Buttons ---------------------------------------------------- */
QPushButton {
    background-color: $surface_container;
    color: $on_surface;
    border: 1px solid $border;
    border-radius: $radius_sm;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 500;
    min-height: 18px;
}

QPushButton:hover {
    background-color: $surface_high;
    border-color: $outline_variant;
    color: #FFFFFF;
}

QPushButton:pressed {
    background-color: $surface_low;
}

QPushButton:disabled {
    background-color: $surface_low;
    color: $text_muted;
    border-color: $border_subtle;
}

QPushButton:focus {
    border: 1px solid $primary;
}

QPushButton#btn_primary {
    background-color: $primary_container;
    color: $on_primary_container;
    border: 1px solid $primary;
    font-weight: 600;
}

QPushButton#btn_primary:hover {
    background-color: $primary;
    color: $on_primary_container;
    border-color: $primary;
}

QPushButton#btn_primary:pressed {
    background-color: $primary_pressed;
    color: $on_primary_container;
}

QPushButton#btn_danger {
    background-color: $error_container;
    color: $error;
    border: 1px solid $error;
}

QPushButton#btn_danger:hover {
    background-color: $error;
    color: $on_error;
}

QPushButton#btn_danger:disabled {
    background-color: $surface_low;
    color: $text_muted;
    border-color: $border_subtle;
}

QPushButton#btn_danger:pressed {
    background-color: $error_pressed;
    color: $on_error;
}

QPushButton#btn_success {
    background-color: $tertiary_container;
    color: $on_tertiary_container;
    border: 1px solid $tertiary;
    font-weight: 600;
}

QPushButton#btn_success:hover {
    background-color: $tertiary;
    color: $on_tertiary;
}

QPushButton#btn_success:pressed {
    background-color: $tertiary_pressed;
    color: $on_tertiary_container;
}

QPushButton#btn_ghost {
    background-color: transparent;
    border: 1px solid transparent;
    color: $on_surface_variant;
}

QPushButton#btn_ghost:hover {
    background-color: $surface_high;
    color: $on_surface;
}

QPushButton#btn_secondary {
    background-color: $surface_container;
    color: $on_surface_variant;
    border: 1px solid $border;
    font-weight: 500;
}

QPushButton#btn_secondary:hover {
    background-color: $surface_high;
    color: $on_surface;
    border-color: $outline_variant;
}

QToolButton#btn_ghost {
    background-color: transparent;
    border: 1px solid transparent;
    color: $on_surface_variant;
    font-size: 15px;
}

QToolButton#btn_ghost:hover {
    background-color: $surface_high;
    color: $on_surface;
}

/* Square icon buttons (the zoom steppers of the card preview). */
QPushButton#btn_icon, QToolButton#btn_icon {
    background-color: transparent;
    border: 1px solid transparent;
    color: $on_surface_variant;
    font-size: 14px;
    padding: 0px;
}

QPushButton#btn_icon:hover, QToolButton#btn_icon:hover {
    background-color: $surface_high;
    color: $on_surface;
}

/* Toggle buttons of the designer bar (guides, snap, bleed, ...). */
QToolButton#btn_toggle {
    background-color: $surface_container;
    border: 1px solid $border;
    border-radius: $radius_sm;
    color: $on_surface_variant;
    font-size: 11px;
    padding: 2px 8px;
    /* The content height plus the padding and the border brings the button
       to the same 28 pixels as every other control of the bar. */
    min-height: 22px;
}

QToolButton#btn_toggle:hover {
    background-color: $surface_high;
    color: $on_surface;
    border-color: $outline_variant;
}

QToolButton#btn_toggle:checked {
    background-color: $surface_high;
    border-color: $tertiary;
    color: $tertiary;
    font-weight: 600;
}

/* The vertical tool strip of the designer. */
QFrame#tool_strip {
    background-color: $surface_container;
    border: 1px solid $border;
    border-radius: $radius;
}

QFrame#tool_strip QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: $radius_sm;
    color: $on_surface_variant;
    font-size: 13px;
    font-weight: 600;
}

QFrame#tool_strip QToolButton:hover {
    background-color: $surface_high;
    color: $on_surface;
    border-color: $border;
}

QFrame#tool_strip QToolButton:checked {
    background-color: $surface_container;
    border-color: $primary_container;
    color: $primary;
}

/* The colour wells of the tool strip. */
QToolButton#swatch_fill {
    border: 1px solid $outline_variant;
    border-radius: $radius_sm;
    padding: 0px;
    min-height: 0px;
}

QToolButton#swatch_stroke {
    background-color: transparent;
    border: 2px solid $outline_variant;
    border-radius: $radius_sm;
    padding: 0px;
    min-height: 0px;
}

/* The button that shows the colour of an element. */
QPushButton#swatch_button {
    background-color: $surface_container;
    color: $on_surface;
    border: 1px solid $border;
    border-radius: $radius_sm;
    padding: 2px 8px;
    text-align: left;
    font-family: $mono_font;
    font-size: 11px;
    font-weight: 500;
}

QPushButton#swatch_button:hover {
    background-color: $surface_high;
    border-color: $outline_variant;
}

QPushButton#swatch_button:pressed {
    background-color: $surface_low;
    border-color: $primary_container;
}

/* A thin rule that separates the groups of a toolbar. */
QFrame#separator {
    background-color: $border;
    border: none;
}

/* Compact square buttons (zoom steppers, record stepper, ...) */
QPushButton#btn_stepper, QToolButton#btn_stepper {
    background-color: $surface_container;
    color: $on_surface;
    border: 1px solid $border;
    border-radius: $radius_sm;
    padding: 0px;
    font-size: 13px;
    font-weight: 700;
    min-height: 18px;
}

QPushButton#btn_stepper:hover, QToolButton#btn_stepper:hover {
    background-color: $surface_high;
    border-color: $primary_container;
    color: $on_surface;
}

/* The active segment of a segmented control. */
QPushButton#btn_stepper:checked, QToolButton#btn_stepper:checked {
    background-color: $surface_high;
    border-color: $primary_container;
    color: $primary;
}

/* --- Tool buttons ------------------------------------------------ */
QToolButton {
    background-color: $surface_container;
    color: $on_surface_variant;
    border: 1px solid $border;
    border-radius: $radius_sm;
    padding: 3px 9px;
    font-size: 12px;
    min-height: 20px;
    icon-size: 10px 7px;
}

QToolButton:hover {
    background-color: $surface_high;
    color: $on_surface;
}

QToolButton:checked {
    background-color: $primary_container;
    color: $on_primary_container;
    border-color: $primary_container;
}

QToolButton:pressed {
    background-color: $surface_low;
}

/* --- Inputs ------------------------------------------------------ */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox, QPlainTextEdit, QTextEdit {
    background-color: $surface_low;
    border: 1px solid $border;
    border-radius: $radius_sm;
    padding: 3px 6px;
    color: $on_surface;
    min-height: 20px;
    font-size: 11px;
}

QComboBox, QFontComboBox {
    padding-right: 20px;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QFontComboBox:focus {
    border: 1px solid $primary;
    background-color: $surface_container;
}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    color: $text_muted;
    background-color: $surface_low;
}

QComboBox::drop-down, QFontComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: none;
    border-top-right-radius: $radius_sm;
    border-bottom-right-radius: $radius_sm;
}

QComboBox::down-arrow, QFontComboBox::down-arrow {
    image: url("$chevron_down");
    width: 9px;
    height: 6px;
}

QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {
    background-color: $surface_container;
    border: 1px solid $border;
    border-radius: $radius_sm;
    selection-background-color: $surface_high;
    selection-color: $primary;
    padding: 3px;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    border-left: 1px solid $border;
    border-bottom: 1px solid $border;
    border-top-right-radius: $radius_sm;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
    background-color: $surface_high;
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    border-left: 1px solid $border;
    border-bottom-right-radius: $radius_sm;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("$chevron_up");
    width: 8px;
    height: 5px;
}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("$chevron_down");
    width: 8px;
    height: 5px;
}

/* --- Tables, lists, trees ----------------------------------------- */
QTableWidget, QTableView, QListWidget, QTreeWidget, QTreeView {
    background-color: $surface_low;
    alternate-background-color: $surface_lowest;
    border: 1px solid $border;
    border-radius: $radius_sm;
    gridline-color: $border_subtle;
    color: $on_surface;
    font-size: 11px;
}

QTableWidget::item, QListWidget::item, QTreeWidget::item {
    padding: 5px 6px;
    border-radius: 3px;
}

QTableWidget::item:selected, QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: $surface_high;
    color: $primary;
    border: 1px solid $primary;
}

QHeaderView::section {
    background-color: $surface_container;
    color: $text_muted;
    padding: 5px 8px;
    border: none;
    border-right: 1px solid $border;
    border-bottom: 1px solid $border;
    font-weight: 600;
    font-size: 11px;
}

QHeaderView::section:last {
    border-right: none;
}

/* --- Scrollbars --------------------------------------------------- */
QScrollBar:vertical {
    background-color: transparent;
    width: 8px;
    margin: 1px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background-color: $border;
    min-height: 24px;
    border-radius: 3px;
}

QScrollBar::handle:vertical:hover {
    background-color: $outline_variant;
}

QScrollBar:horizontal {
    background-color: transparent;
    height: 8px;
    margin: 1px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background-color: $border;
    min-width: 24px;
    border-radius: 3px;
}

QScrollBar::handle:horizontal:hover {
    background-color: $outline_variant;
}

QScrollBar::add-line, QScrollBar::sub-line {
    height: 0px;
    width: 0px;
}

QScrollArea {
    border: none;
    background-color: $surface;
}

/* --- Tabs --------------------------------------------------------- */
QTabWidget::pane {
    border: 1px solid $border;
    background-color: $surface_low;
    border-radius: $radius_sm;
}

QTabBar::tab {
    background-color: $surface_container;
    color: $text_muted;
    border: 1px solid $border;
    border-bottom: none;
    padding: 6px 14px;
    border-top-left-radius: $radius_sm;
    border-top-right-radius: $radius_sm;
    margin-right: 2px;
    font-size: 11px;
}

QTabBar::tab:selected {
    background-color: $surface_high;
    color: $on_surface;
    border-bottom: 2px solid $primary_container;
}

/* --- Status bar & progress ----------------------------------------- */
QStatusBar {
    background-color: $surface_dim;
    color: $text_muted;
    border-top: 1px solid $border;
    font-size: 11px;
}

QProgressBar {
    background-color: $surface_low;
    border: 1px solid $border;
    border-radius: $radius_sm;
    text-align: center;
    color: $on_surface;
    font-size: 11px;
    font-family: $mono_font;
    min-height: 18px;
}

QProgressBar::chunk {
    background-color: $primary_container;
    border-radius: 3px;
}

/* --- Splitter ------------------------------------------------------ */
QSplitter::handle {
    background-color: $border_subtle;
}

QSplitter::handle:hover {
    background-color: $primary_container;
}

/* --- Group boxes --------------------------------------------------- */
QGroupBox {
    border: 1px solid $border;
    border-radius: $radius;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: 600;
    color: $on_surface;
    font-size: 12px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 4px;
    color: $primary;
}

/* --- Segmented controls & formatting buttons ---------------------- */
QFrame#ctx_align_rect, QFrame#insp_align_rect, QFrame#segmented {
    background-color: $surface_low;
    border: 1px solid $border;
    border-radius: $radius_sm;
}

QFrame#ctx_align_rect QToolButton, QFrame#insp_align_rect QToolButton,
QFrame#segmented QToolButton, QFrame#segmented QPushButton {
    background-color: transparent;
    color: $on_surface_variant;
    border: none;
    font-size: 12px;
    font-weight: 500;
    padding: 2px 10px;
    min-height: 20px;
}

QFrame#ctx_align_rect QToolButton:hover, QFrame#insp_align_rect QToolButton:hover,
QFrame#segmented QToolButton:hover, QFrame#segmented QPushButton:hover {
    background-color: $surface_high;
    color: $on_surface;
}

QFrame#ctx_align_rect QToolButton:checked, QFrame#insp_align_rect QToolButton:checked,
QFrame#segmented QToolButton:checked, QFrame#segmented QPushButton:checked {
    background-color: $primary_container;
    color: $on_primary_container;
    font-weight: 600;
}

QFrame#segmented QLabel {
    background-color: transparent;
    color: $on_surface;
    border: none;
    font-family: $mono_font;
    font-size: 11px;
    padding: 2px 8px;
    min-height: 20px;
}

QToolButton#ctx_bold_btn, QToolButton#ctx_italic_btn, QToolButton#ctx_color_btn,
QToolButton#ctx_fill_btn, QToolButton#ctx_stroke_btn {
    background-color: $surface_container;
    color: $on_surface;
    border: 1px solid $border;
    border-radius: $radius_sm;
    font-size: 13px;
}

QToolButton#ctx_bold_btn:hover, QToolButton#ctx_italic_btn:hover, QToolButton#ctx_color_btn:hover,
QToolButton#ctx_fill_btn:hover, QToolButton#ctx_stroke_btn:hover {
    background-color: $surface_high;
    border-color: $outline_variant;
}

QToolButton#ctx_bold_btn:checked, QToolButton#ctx_italic_btn:checked {
    background-color: $primary_container;
    color: #FFFFFF;
    border-color: $primary_container;
}

/* --- Notices ------------------------------------------------------- */
QLabel#notice_banner {
    background-color: $surface_low;
    border: 1px solid $border;
    border-left: 3px solid $primary_container;
    border-radius: $radius_sm;
    padding: 8px 12px;
    color: $on_surface_variant;
    font-size: 11px;
}

QLabel#notice_banner[severity="error"] {
    border-left-color: $error;
    color: $error;
}

QLabel#notice_banner[severity="warning"] {
    border-left-color: $warning;
    color: $warning;
}

QLabel#notice_banner[severity="success"] {
    border-left-color: $tertiary;
    color: $tertiary;
}

/* Labels never paint a surface of their own. */
QLabel {
    background: transparent;
}

/* --- Typography roles ------------------------------------------------ */
QLabel[role="heroTitle"] {
    color: $on_surface;
    font-size: 26px;
    font-weight: 800;
}

QLabel[role="pageTitle"] {
    color: $on_surface;
    font-size: 15px;
    font-weight: 700;
}

QLabel[role="pageSubtitle"] {
    color: $text_muted;
    font-size: 11px;
}

QLabel[role="sectionLabel"] {
    color: $text_muted;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
}

QLabel[role="brandTitle"] {
    color: $on_surface;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.08em;
}

QLabel[role="cardTitle"] {
    color: $on_surface;
    font-size: 13px;
    font-weight: 700;
}

QLabel[role="cardSubtitle"] {
    color: $text_muted;
    font-size: 10px;
}

QLabel[role="stepBadge"] {
    color: $text_muted;
    font-family: $mono_font;
    font-size: 11px;
    letter-spacing: 0.06em;
}

QLabel[role="monoMuted"] {
    color: $text_muted;
    font-family: $mono_font;
    font-size: 11px;
}

QLabel[role="statCaption"] {
    color: $text_muted;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.1em;
}

QLabel[role="statValue"] {
    color: $on_surface;
    font-family: $mono_font;
    font-size: 12px;
    font-weight: 600;
}

QLabel[role="specKey"] {
    color: $text_muted;
    font-size: 11px;
}

/* The caption of a control in a toolbar row. */
QLabel[role="controlLabel"] {
    color: $on_surface;
    font-size: 12px;
    font-weight: 600;
}

/* A value that stands out, for example the selection of the canvas. */
QLabel[role="accentText"] {
    color: $primary;
    font-family: $mono_font;
    font-size: 11px;
}

/* The well that holds the photograph of the sample record. */
QLabel[role="photoWell"] {
    background-color: $surface_low;
    border: 1px solid $border;
    border-radius: $radius_sm;
}

QLabel[role="specValue"] {
    color: $on_surface;
    font-family: $mono_font;
    font-size: 11px;
}

QLineEdit[role="fieldFlat"], QTextEdit[role="fieldFlat"] {
    background-color: $surface_low;
    border: 1px solid $border_subtle;
    border-radius: 4px;
    padding: 3px 8px;
    color: $on_surface;
}

QLineEdit[role="fieldFlat"]:focus, QTextEdit[role="fieldFlat"]:focus {
    border-color: $primary;
    background-color: $surface_container;
}

QLabel[role="tableTitle"] {
    color: $on_surface;
    font-size: 13px;
    font-weight: 600;
}

QLabel[role="tableSubtitle"] {
    color: $text_muted;
    font-size: 11px;
}

QLabel[role="tableCell"] {
    color: $on_surface_variant;
    font-size: 11px;
}

QLabel[role="tableMono"] {
    color: $text_muted;
    font-family: $mono_font;
    font-size: 11px;
}

QLabel[role="badgeMuted"] {
    background-color: $surface_high;
    color: $on_surface_variant;
    border: 1px solid $border_subtle;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    padding: 3px 6px;
}

QLabel[role="badgeAccent"] {
    background-color: $surface_high;
    color: $primary;
    border: 1px solid $border_subtle;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    padding: 3px 6px;
}

QLabel[role="badge"] {
    background-color: $surface_container;
    color: $text_muted;
    border: 1px solid $border;
    border-radius: 3px;
    font-family: $mono_font;
    font-size: 10px;
    font-weight: 600;
    padding: 1px 6px;
}

QLabel[role="metricValue"] {
    color: $on_surface;
    font-family: $mono_font;
    font-size: 22px;
    font-weight: 700;
}

QLabel[role="metricCaption"] {
    color: $text_muted;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
}

QMenu {
    background-color: $surface_container;
    border: 1px solid $border;
    border-radius: $radius_sm;
    padding: 4px;
}

QMenu::item {
    padding: 5px 20px;
    border-radius: 3px;
}

QMenu::item:selected {
    background-color: $surface_high;
}

QMenuBar {
    background-color: $surface_dim;
    color: $on_surface_variant;
}

QMenuBar::item:selected {
    background-color: $surface_high;
}

QToolTip {
    background-color: $surface_highest;
    color: $on_surface;
    border: 1px solid $border;
    padding: 4px 6px;
}
"""
        values = {
            "ui_font": cls._ui_font_family(),
            "mono_font": cls._mono_font_family(),
            "surface": p.SURFACE,
            "surface_dim": p.SURFACE_DIM,
            "surface_lowest": p.SURFACE_LOWEST,
            "surface_low": p.SURFACE_LOW,
            "surface_container": p.SURFACE_CONTAINER,
            "surface_high": p.SURFACE_HIGH,
            "surface_highest": p.SURFACE_HIGHEST,
            "canvas_backdrop": p.CANVAS_BACKDROP,
            "border": p.BORDER_HAIRLINE,
            "border_subtle": p.BORDER_SUBTLE,
            "outline_variant": p.OUTLINE_VARIANT,
            "primary": p.PRIMARY,
            "primary_container": p.PRIMARY_CONTAINER,
            "primary_pressed": p.PRIMARY_PRESSED,
            "on_primary": p.ON_PRIMARY,
            "on_primary_container": p.ON_PRIMARY_CONTAINER,
            "on_surface": p.ON_SURFACE,
            "on_surface_variant": p.ON_SURFACE_VARIANT,
            "text_muted": p.TEXT_MUTED,
            "tertiary": p.TERTIARY,
            "tertiary_container": p.TERTIARY_CONTAINER,
            "tertiary_pressed": p.TERTIARY_PRESSED,
            "on_tertiary": p.ON_TERTIARY,
            "on_tertiary_container": p.ON_TERTIARY_CONTAINER,
            "warning": p.WARNING,
            "error": p.ERROR,
            "error_container": p.ERROR_CONTAINER,
            "error_pressed": p.ERROR_PRESSED,
            "on_error": p.ON_ERROR,
            "radius": "6px",
            "radius_sm": "4px",
            "chevron_down": chevron_down,
            "chevron_up": chevron_up,
        }
        return Template(template).safe_substitute(**values)
