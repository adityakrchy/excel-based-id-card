"""Studio workspace navigation ribbon bar with tabs and canvas utility controls per Screenshot 2."""

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
from id_card_generator.ui.components.status_pill import StatusPill
from id_card_generator.ui.studio_tokens import COLORS, TYPOGRAPHY


class StudioTab(str, Enum):
    """Primary Studio Workspaces matching Stitch designs."""
    HUB = "hub"
    TEMPLATES = "templates"
    DESIGNER = "designer"
    DATA_MAPPING = "data_mapping"
    GENERATE_PREVIEW = "generate_preview"
    EXPORT_PRINT = "export_print"


class StudioNavBar(QFrame):
    """Navigation ribbon containing Project Hub, workspace tabs, and enterprise security badge."""

    tab_selected = Signal(str)  # StudioTab value
    grid_toggled = Signal(bool)
    preview_toggled = Signal(bool)
    help_requested = Signal()

    TABS = [
        (StudioTab.HUB, "Project Hub"),
        (StudioTab.TEMPLATES, "Templates Library"),
        (StudioTab.DESIGNER, "Template Designer"),
        (StudioTab.DATA_MAPPING, "Data Mapping"),
        (StudioTab.GENERATE_PREVIEW, "Batch Queue"),
        (StudioTab.EXPORT_PRINT, "Export & Print"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("studio_nav_bar")
        self.setFixedHeight(44)
        self._buttons: Dict[StudioTab, QPushButton] = {}
        self._active_tab = StudioTab.HUB

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(12)

        # Left Brand Section: ID Studio Lockup
        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(8)

        lbl_icon = QLabel("🪪")
        lbl_icon.setStyleSheet("font-size: 15px;")
        brand_layout.addWidget(lbl_icon)

        lbl_hub = QLabel("ID Studio")
        lbl_hub.setStyleSheet(
            f"color: #FFFFFF; font-family: {TYPOGRAPHY.FONT_FAMILY_UI}; "
            f"font-size: 13px; font-weight: 700; margin-right: 12px;"
        )
        brand_layout.addWidget(lbl_hub)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedHeight(18)
        sep.setStyleSheet("background-color: #2D3038;")
        brand_layout.addWidget(sep)

        layout.addLayout(brand_layout)

        # Center: Tab Buttons
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        tabs_layout = QHBoxLayout()
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.setSpacing(4)

        for tab_id, label in self.TABS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(44)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, t=tab_id: self._on_tab_clicked(t))
            self.btn_group.addButton(btn)
            tabs_layout.addWidget(btn)
            self._buttons[tab_id] = btn

        # Default select Projects & Hub
        if StudioTab.HUB in self._buttons:
            self._buttons[StudioTab.HUB].setChecked(True)

        layout.addLayout(tabs_layout)
        layout.addStretch()

        # Right Side: FIPS Security Pill + User Avatar
        right_tools = QHBoxLayout()
        right_tools.setSpacing(10)

        # Canvas Utility controls (hidden by default on Hub, shown on Designer)
        self.btn_grid = QToolButton()
        self.btn_grid.setText("⊞ Grid")
        self.btn_grid.setCheckable(True)
        self.btn_grid.setChecked(True)
        self.btn_grid.setFixedHeight(26)
        self.btn_grid.setToolTip("Toggle Canvas Grid (G)")
        self.btn_grid.toggled.connect(self.grid_toggled.emit)
        self._style_tool_btn(self.btn_grid)
        self.btn_grid.setVisible(False)
        right_tools.addWidget(self.btn_grid)

        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setFixedHeight(26)
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        self.lbl_zoom.setStyleSheet(
            f"background-color: {COLORS.SURFACE_CONTAINER}; color: {COLORS.ON_SURFACE}; "
            f"border: 1px solid {COLORS.BORDER_HAIRLINE}; border-radius: 4px; "
            f"font-family: {TYPOGRAPHY.FONT_FAMILY_MONO}; font-size: 11px; padding: 0 8px;"
        )
        self.lbl_zoom.setVisible(False)
        right_tools.addWidget(self.lbl_zoom)

        self.btn_preview = QToolButton()
        self.btn_preview.setText("👁 Preview")
        self.btn_preview.setCheckable(True)
        self.btn_preview.setFixedHeight(26)
        self.btn_preview.setToolTip("Toggle Live Record Data Binding Preview")
        self.btn_preview.toggled.connect(self.preview_toggled.emit)
        self._style_tool_btn(self.btn_preview)
        self.btn_preview.setVisible(False)
        right_tools.addWidget(self.btn_preview)

        # FIPS Security Pill
        self.pill_fips = StatusPill(text="FIPS 140-3 HW-SEC OK", dot_color=COLORS.TERTIARY)
        self.pill_fips.setStyleSheet(
            f"QFrame#status_pill {{ background-color: #14171D; border: 1px solid #282C34; border-radius: 4px; }}"
        )
        right_tools.addWidget(self.pill_fips)

        # User Avatar Circle Button
        self.btn_avatar = QToolButton()
        self.btn_avatar.setText("👤")
        self.btn_avatar.setFixedSize(28, 28)
        self.btn_avatar.setCursor(Qt.PointingHandCursor)
        self.btn_avatar.setStyleSheet(
            "QToolButton { background-color: #282C34; border: 1px solid #383D47; border-radius: 14px; font-size: 13px; color: #FFFFFF; }"
            "QToolButton:hover { background-color: #333539; border-color: #6C8CFF; }"
        )
        right_tools.addWidget(self.btn_avatar)

        self.btn_help = QToolButton()
        self.btn_help.setVisible(False)
        self.btn_help.clicked.connect(self.help_requested.emit)
        right_tools.addWidget(self.btn_help)

        layout.addLayout(right_tools)

        self._apply_style()

    def _style_tool_btn(self, btn: QToolButton) -> None:
        btn.setStyleSheet(
            f"QToolButton {{"
            f"  background-color: {COLORS.SURFACE_CONTAINER};"
            f"  color: {COLORS.ON_SURFACE_VARIANT};"
            f"  border: 1px solid {COLORS.BORDER_HAIRLINE};"
            f"  border-radius: 4px;"
            f"  font-size: 11px;"
            f"  padding: 0 8px;"
            f"}}"
            f"QToolButton:hover {{"
            f"  background-color: {COLORS.SURFACE_HIGH};"
            f"  color: {COLORS.ON_SURFACE};"
            f"}}"
            f"QToolButton:checked {{"
            f"  background-color: {COLORS.PRIMARY_CONTAINER};"
            f"  color: #FFFFFF;"
            f"  border-color: {COLORS.PRIMARY_CONTAINER};"
            f"}}"
        )

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"QFrame#studio_nav_bar {{"
            f"  background-color: {COLORS.SURFACE};"
            f"  border-bottom: 1px solid {COLORS.BORDER_HAIRLINE};"
            f"}}"
            f"QPushButton {{"
            f"  background: transparent;"
            f"  color: {COLORS.ON_SURFACE_VARIANT};"
            f"  border: none;"
            f"  border-bottom: 2px solid transparent;"
            f"  font-family: {TYPOGRAPHY.FONT_FAMILY_UI};"
            f"  font-size: 12px;"
            f"  font-weight: 500;"
            f"  padding: 0 12px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  color: {COLORS.ON_SURFACE};"
            f"  background-color: {COLORS.SURFACE_LOW};"
            f"}}"
            f"QPushButton:checked {{"
            f"  color: #FFFFFF;"
            f"  font-weight: 600;"
            f"  border-bottom: 2px solid {COLORS.PRIMARY_CONTAINER};"
            f"}}"
        )

    def _on_tab_clicked(self, tab: StudioTab) -> None:
        self._active_tab = tab
        self.tab_selected.emit(tab.value)

    def set_active_tab(self, tab: StudioTab) -> None:
        if tab in self._buttons:
            self._buttons[tab].setChecked(True)
            self._active_tab = tab

    def set_designer_tools_visible(self, visible: bool) -> None:
        self.btn_grid.setVisible(visible)
        self.lbl_zoom.setVisible(visible)
        self.btn_preview.setVisible(visible)

    def set_zoom_text(self, text: str) -> None:
        self.lbl_zoom.setText(text)
