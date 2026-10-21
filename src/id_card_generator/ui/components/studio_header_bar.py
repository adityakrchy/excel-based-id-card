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
from id_card_generator.ui.studio_tokens import COLORS, TYPOGRAPHY, palette_for


class StudioHeaderBar(QFrame):
    """Studio top header bar featuring document lockup, undo/save, and local sync badge per Stitch Screen c0960262ecc9."""

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
        # The bar restyles itself on every theme change.
        self.setProperty("theme_managed", True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)

        # -------------------------------------------------------------
        # Left Group: ID STUDIO brand + Version Pill + Repository Path
        # -------------------------------------------------------------
        left_layout = QHBoxLayout()
        left_layout.setSpacing(8)

        self.lbl_brand = QLabel("ID STUDIO")
        self.lbl_brand.setProperty("role", "brandTitle")
        left_layout.addWidget(self.lbl_brand)

        self.lbl_version_badge = QLabel("v2.4.1 Enterprise")
        self.lbl_version_badge.setProperty("role", "badge")
        left_layout.addWidget(self.lbl_version_badge)

        self.lbl_slash = QLabel("/")
        self.lbl_slash.setProperty("role", "monoMuted")
        left_layout.addWidget(self.lbl_slash)

        self.lbl_project_name = QLabel("Project: Untitled.idcrt")
        self.lbl_project_name.setProperty("role", "monoMuted")
        left_layout.addWidget(self.lbl_project_name)

        self.lbl_dirty_dot = QLabel("•")
        self.lbl_dirty_dot.setStyleSheet(
            f"color: {COLORS.PRIMARY_CONTAINER}; font-size: 16px; font-weight: bold;"
        )
        self.lbl_dirty_dot.setVisible(False)
        left_layout.addWidget(self.lbl_dirty_dot)

        # Document actions - always visible so the shell is self explanatory.
        self.btn_new = self._create_icon_btn("＋", "New Project (Ctrl+N)")
        self.btn_new.clicked.connect(self.new_requested.emit)
        left_layout.addWidget(self.btn_new)

        self.btn_open = self._create_icon_btn("⇱", "Open Project (Ctrl+O)")
        self.btn_open.clicked.connect(self.open_requested.emit)
        left_layout.addWidget(self.btn_open)

        self.btn_save = self._create_icon_btn("⇲", "Save Project (Ctrl+S)")
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

        # -------------------------------------------------------------
        # Right Group: CLUSTER ONLINE Status Pill + Window Controls
        # -------------------------------------------------------------
        right_layout = QHBoxLayout()
        right_layout.setSpacing(10)

        self.status_pill = StatusPill(text="CLUSTER ONLINE", dot_color=COLORS.TERTIARY)
        self.status_pill.setStyleSheet(
            f"QFrame#status_pill {{ background-color: transparent; border: none; }}"
        )
        right_layout.addWidget(self.status_pill)

        # Window Controls Mock (per design screenshot)
        win_controls = QHBoxLayout()
        win_controls.setSpacing(6)
        btn_min = QLabel("—")
        btn_min.setStyleSheet("color: #8E909F; font-size: 11px; padding: 0 4px;")
        btn_max = QLabel("□")
        btn_max.setStyleSheet("color: #8E909F; font-size: 11px; padding: 0 4px;")
        btn_close = QLabel("✕")
        btn_close.setStyleSheet("color: #8E909F; font-size: 11px; padding: 0 4px;")
        win_controls.addWidget(btn_min)
        win_controls.addWidget(btn_max)
        win_controls.addWidget(btn_close)
        right_layout.addLayout(win_controls)

        # Hidden theme combo kept for test compatibility
        self.cmb_theme = QComboBox()
        self.cmb_theme.setVisible(False)
        self.cmb_theme.addItem("Dark Workstation", "black")
        self.cmb_theme.addItem("Light Canvas", "white")
        self.cmb_theme.currentIndexChanged.connect(self._on_theme_changed)
        right_layout.addWidget(self.cmb_theme)

        layout.addLayout(right_layout)

        self.refresh_theme("black")

    def _create_icon_btn(self, icon_char: str, tooltip: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(icon_char)
        btn.setToolTip(tooltip)
        btn.setFixedSize(26, 26)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setProperty("role", "iconButton")
        return btn

    def refresh_theme(self, theme: str = "black") -> None:
        """Re-apply the chrome styling for the given theme."""
        c = palette_for(theme)
        for name in ("btn_new", "btn_open", "btn_save", "btn_undo", "btn_redo"):
            btn = getattr(self, name, None)
            if btn is None:
                continue
            btn.setStyleSheet(
                f"QToolButton {{"
                f"  background: transparent;"
                f"  color: {c.ON_SURFACE_VARIANT};"
                f"  border: 1px solid transparent;"
                f"  border-radius: 3px;"
                f"  font-size: 15px;"
                f"}}"
                f"QToolButton:hover {{"
                f"  background-color: {c.SURFACE_HIGH};"
                f"  color: {c.ON_SURFACE};"
                f"  border-color: {c.BORDER_HAIRLINE};"
                f"}}"
                f"QToolButton:pressed {{"
                f"  background-color: {c.SURFACE_LOW};"
                f"}}"
            )

        self.setStyleSheet(
            f"QFrame#studio_header_bar {{"
            f"  background-color: {c.SURFACE_DIM};"
            f"  border-bottom: 1px solid {c.BORDER_HAIRLINE};"
            f"}}"
        )

    def _on_theme_changed(self) -> None:
        theme = self.cmb_theme.currentData()
        if theme:
            self.theme_requested.emit(theme)

    def set_project_title(self, name: str, is_dirty: bool = False) -> None:
        if name:
            clean = name.strip()
            if not clean.endswith(".idcrt") and not clean.endswith(".idproj") and not clean.endswith(".json"):
                clean = f"{clean}.idcrt"
            self.lbl_project_name.setText(f"Project: {clean}")
        else:
            self.lbl_project_name.setText("Project: Untitled.idcrt")
        self.lbl_dirty_dot.setVisible(is_dirty)

    def set_sync_status(self, text: str, dot_color: str = COLORS.TERTIARY) -> None:
        self.status_pill.set_text(text)
        self.status_pill.set_dot_color(dot_color)
