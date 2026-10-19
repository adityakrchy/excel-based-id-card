"""Studio workspace navigation ribbon bar with tabs and canvas utility controls."""

from enum import Enum
from typing import Dict
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
)
from id_card_generator.ui.studio_tokens import COLORS, TYPOGRAPHY


class StudioTab(str, Enum):
    """Primary Studio Workspaces matching Stitch designs."""
    TEMPLATES = "templates"
    DESIGNER = "designer"
    DATA_MAPPING = "data_mapping"
    GENERATE_PREVIEW = "generate_preview"
    EXPORT_PRINT = "export_print"


class StudioNavBar(QFrame):
    """Navigation ribbon containing 5 studio workspace tabs and canvas quick toggles."""

    tab_selected = Signal(str)  # StudioTab value
    grid_toggled = Signal(bool)
    preview_toggled = Signal(bool)
    help_requested = Signal()

    TABS = [
        (StudioTab.TEMPLATES, "Templates"),
        (StudioTab.DESIGNER, "Template Designer"),
        (StudioTab.DATA_MAPPING, "Data Mapping"),
        (StudioTab.GENERATE_PREVIEW, "Generate & Preview"),
        (StudioTab.EXPORT_PRINT, "Export & Print"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("studio_nav_bar")
        self.setFixedHeight(44)
        self._buttons: Dict[StudioTab, QPushButton] = {}
        self._active_tab = StudioTab.DESIGNER

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(0)

        # Tab Buttons Container
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        tabs_layout = QHBoxLayout()
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.setSpacing(2)

        for tab_id, label in self.TABS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(44)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, t=tab_id: self._on_tab_clicked(t))
            self.btn_group.addButton(btn)
            tabs_layout.addWidget(btn)
            self._buttons[tab_id] = btn

        layout.addLayout(tabs_layout)
        layout.addStretch()

        # Right Side Quick Utility Tools
        right_tools = QHBoxLayout()
        right_tools.setSpacing(6)

        # Grid Toggle
        self.btn_grid = QToolButton()
        self.btn_grid.setText("⊞ Grid")
        self.btn_grid.setCheckable(True)
        self.btn_grid.setChecked(True)
        self.btn_grid.setFixedHeight(26)
        self.btn_grid.setToolTip("Toggle Canvas Grid (G)")
        self.btn_grid.toggled.connect(self.grid_toggled.emit)
        self._style_tool_btn(self.btn_grid)
        right_tools.addWidget(self.btn_grid)

        # Zoom Indicator
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setFixedHeight(26)
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        self.lbl_zoom.setStyleSheet(
            f"background-color: {COLORS.SURFACE_CONTAINER}; color: {COLORS.ON_SURFACE}; "
            f"border: 1px solid {COLORS.BORDER_HAIRLINE}; border-radius: 4px; "
            f"font-family: {TYPOGRAPHY.FONT_FAMILY_MONO}; font-size: 11px; padding: 0 8px;"
        )
        right_tools.addWidget(self.lbl_zoom)

        # Live Preview Toggle
        self.btn_preview = QToolButton()
        self.btn_preview.setText("👁 Preview")
        self.btn_preview.setCheckable(True)
        self.btn_preview.setFixedHeight(26)
        self.btn_preview.setToolTip("Toggle Live Record Data Binding Preview")
        self.btn_preview.toggled.connect(self.preview_toggled.emit)
        self._style_tool_btn(self.btn_preview)
        right_tools.addWidget(self.btn_preview)

        # Help Button
        self.btn_help = QToolButton()
        self.btn_help.setText("?")
        self.btn_help.setFixedSize(26, 26)
        self.btn_help.setToolTip("Help & Documentation (F1)")
        self.btn_help.clicked.connect(self.help_requested.emit)
        self._style_tool_btn(self.btn_help)
        right_tools.addWidget(self.btn_help)

        layout.addLayout(right_tools)

        self._apply_styles()
        self.set_active_tab(StudioTab.TEMPLATES)

    def _style_tool_btn(self, btn: QToolButton) -> None:
        btn.setStyleSheet(
            f"QToolButton {{"
            f"  background-color: {COLORS.SURFACE_CONTAINER};"
            f"  color: {COLORS.ON_SURFACE_VARIANT};"
            f"  border: 1px solid {COLORS.BORDER_HAIRLINE};"
            f"  border-radius: 4px;"
            f"  font-family: {TYPOGRAPHY.FONT_FAMILY_MONO};"
            f"  font-size: 11px;"
            f"  padding: 0 8px;"
            f"}}"
            f"QToolButton:hover {{"
            f"  background-color: {COLORS.SURFACE_HIGH};"
            f"  color: {COLORS.ON_SURFACE};"
            f"}}"
            f"QToolButton:checked {{"
            f"  background-color: {COLORS.SURFACE_HIGH};"
            f"  color: {COLORS.PRIMARY_CONTAINER};"
            f"  border-color: {COLORS.PRIMARY_CONTAINER};"
            f"}}"
        )

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QFrame#studio_nav_bar {{"
            f"  background-color: {COLORS.SURFACE_LOW};"
            f"  border-bottom: 1px solid {COLORS.BORDER_HAIRLINE};"
            f"}}"
            f"QPushButton {{"
            f"  background-color: transparent;"
            f"  color: {COLORS.ON_SURFACE_VARIANT};"
            f"  border: none;"
            f"  border-bottom: 2px solid transparent;"
            f"  font-family: {TYPOGRAPHY.FONT_FAMILY_UI};"
            f"  font-size: 12px;"
            f"  font-weight: 500;"
            f"  padding: 0 16px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {COLORS.SURFACE_CONTAINER};"
            f"  color: {COLORS.ON_SURFACE};"
            f"}}"
            f"QPushButton:checked {{"
            f"  background-color: {COLORS.SURFACE_HIGH};"
            f"  color: {COLORS.ON_SURFACE};"
            f"  font-weight: 600;"
            f"  border-bottom: 2px solid {COLORS.PRIMARY_CONTAINER};"
            f"}}"
        )

    def _on_tab_clicked(self, tab: StudioTab) -> None:
        self._active_tab = tab
        self.tab_selected.emit(tab.value)

    def set_active_tab(self, tab: StudioTab) -> None:
        self._active_tab = tab
        btn = self._buttons.get(tab)
        if btn:
            btn.setChecked(True)

    def set_zoom_text(self, text: str) -> None:
        self.lbl_zoom.setText(text)
