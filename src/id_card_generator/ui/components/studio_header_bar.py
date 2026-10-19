"""Top command bar with project title, dirty state, quick action buttons, and status pill."""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
)
from id_card_generator.ui.components.status_pill import StatusPill
from id_card_generator.ui.studio_tokens import COLORS, TYPOGRAPHY


class StudioHeaderBar(QFrame):
    """Studio top header bar featuring document lockup, undo/save, and local sync badge."""

    undo_requested = Signal()
    redo_requested = Signal()
    save_requested = Signal()
    new_requested = Signal()
    open_requested = Signal()
    theme_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("studio_header_bar")
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        # Left Group: Brand + Project File + Dirty Dot + Quick Tools
        left_layout = QHBoxLayout()
        left_layout.setSpacing(6)

        self.lbl_logo = QLabel("🪪")
        self.lbl_logo.setStyleSheet("font-size: 14px;")
        left_layout.addWidget(self.lbl_logo)

        self.lbl_brand = QLabel("ID Studio")
        self.lbl_brand.setStyleSheet(
            f"color: {COLORS.ON_SURFACE}; font-family: {TYPOGRAPHY.FONT_FAMILY_UI}; "
            f"font-size: 13px; font-weight: 700; letter-spacing: -0.01em;"
        )
        left_layout.addWidget(self.lbl_brand)

        lbl_slash = QLabel("/")
        lbl_slash.setStyleSheet(f"color: {COLORS.BORDER_HAIRLINE}; font-size: 12px;")
        left_layout.addWidget(lbl_slash)

        self.lbl_project_name = QLabel("Untitled.idproj")
        self.lbl_project_name.setStyleSheet(
            f"color: {COLORS.ON_SURFACE_VARIANT}; font-family: {TYPOGRAPHY.FONT_FAMILY_MONO}; "
            f"font-size: 11px;"
        )
        left_layout.addWidget(self.lbl_project_name)

        self.lbl_dirty_dot = QLabel("•")
        self.lbl_dirty_dot.setStyleSheet(
            f"color: {COLORS.PRIMARY_CONTAINER}; font-size: 16px; font-weight: bold;"
        )
        self.lbl_dirty_dot.setVisible(False)
        left_layout.addWidget(self.lbl_dirty_dot)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setFixedHeight(14)
        sep1.setStyleSheet(f"background-color: {COLORS.BORDER_HAIRLINE};")
        left_layout.addWidget(sep1)

        # Quick action buttons
        self.btn_new = self._create_icon_btn("📄", "New Project (Ctrl+N)")
        self.btn_new.clicked.connect(self.new_requested.emit)
        left_layout.addWidget(self.btn_new)

        self.btn_open = self._create_icon_btn("📁", "Open Project (Ctrl+O)")
        self.btn_open.clicked.connect(self.open_requested.emit)
        left_layout.addWidget(self.btn_open)

        self.btn_save = self._create_icon_btn("💾", "Save Project (Ctrl+S)")
        self.btn_save.clicked.connect(self.save_requested.emit)
        left_layout.addWidget(self.btn_save)

        self.btn_undo = self._create_icon_btn("↶", "Undo (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.undo_requested.emit)
        left_layout.addWidget(self.btn_undo)

        self.btn_redo = self._create_icon_btn("↷", "Redo (Ctrl+Y)")
        self.btn_redo.clicked.connect(self.redo_requested.emit)
        left_layout.addWidget(self.btn_redo)

        layout.addLayout(left_layout)
        layout.addStretch()

        # Center Group: Auto-Saved Status Pill
        self.status_pill = StatusPill(text="Auto-saved (Local)", dot_color=COLORS.TERTIARY)
        layout.addWidget(self.status_pill)
        layout.addStretch()

        # Right Group: Theme & Options
        right_layout = QHBoxLayout()
        right_layout.setSpacing(6)

        self.cmb_theme = QComboBox()
        self.cmb_theme.setFixedHeight(22)
        self.cmb_theme.addItem("Dark Workstation", "black")
        self.cmb_theme.addItem("Light Canvas", "white")
        self.cmb_theme.setStyleSheet(
            f"QComboBox {{"
            f"  background-color: {COLORS.SURFACE_CONTAINER};"
            f"  color: {COLORS.ON_SURFACE_VARIANT};"
            f"  border: 1px solid {COLORS.BORDER_HAIRLINE};"
            f"  border-radius: 4px;"
            f"  font-size: 11px;"
            f"  padding: 1px 6px;"
            f"}}"
        )
        self.cmb_theme.currentIndexChanged.connect(self._on_theme_changed)
        right_layout.addWidget(self.cmb_theme)

        layout.addLayout(right_layout)

        self.setStyleSheet(
            f"QFrame#studio_header_bar {{"
            f"  background-color: {COLORS.SURFACE_DIM};"
            f"  border-bottom: 1px solid {COLORS.BORDER_HAIRLINE};"
            f"}}"
        )

    def _create_icon_btn(self, icon_char: str, tooltip: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(icon_char)
        btn.setToolTip(tooltip)
        btn.setFixedSize(22, 22)
        btn.setStyleSheet(
            f"QToolButton {{"
            f"  background: transparent;"
            f"  color: {COLORS.ON_SURFACE_VARIANT};"
            f"  border: 1px solid transparent;"
            f"  border-radius: 3px;"
            f"  font-size: 11px;"
            f"}}"
            f"QToolButton:hover {{"
            f"  background-color: {COLORS.SURFACE_HIGH};"
            f"  color: {COLORS.ON_SURFACE};"
            f"  border-color: {COLORS.BORDER_HAIRLINE};"
            f"}}"
        )
        return btn

    def _on_theme_changed(self) -> None:
        theme = self.cmb_theme.currentData()
        if theme:
            self.theme_requested.emit(theme)

    def set_project_title(self, name: str, is_dirty: bool = False) -> None:
        self.lbl_project_name.setText(name)
        self.lbl_dirty_dot.setVisible(is_dirty)

    def set_sync_status(self, text: str, dot_color: str = COLORS.TERTIARY) -> None:
        self.status_pill.set_text(text)
        self.status_pill.set_dot_color(dot_color)
