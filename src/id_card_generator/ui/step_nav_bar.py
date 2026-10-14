"""Standardized step-by-step bottom navigation bar for sequential module interaction."""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)


class StepNavBar(QFrame):
    """Bottom navigation bar enabling sequential module-by-module interaction."""

    back_requested = Signal()
    next_requested = Signal()

    def __init__(
        self,
        prev_label: Optional[str] = None,
        next_label: Optional[str] = None,
        step_badge: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("card_panel")
        self.setFixedHeight(54)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        # Back Button
        self.btn_back = QPushButton(f"◀ Back: {prev_label}" if prev_label else "◀ Back")
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.clicked.connect(self.back_requested.emit)
        if not prev_label:
            self.btn_back.setVisible(False)
        layout.addWidget(self.btn_back)

        layout.addStretch()

        # Step badge / helper text
        if step_badge:
            lbl_badge = QLabel(f"<b>{step_badge}</b>")
            lbl_badge.setStyleSheet("color: #64748B; font-size: 12px; letter-spacing: 0.5px;")
            layout.addWidget(lbl_badge)
            layout.addStretch()

        # Next Button
        self.btn_next = QPushButton(f"{next_label} ➔" if next_label else "Next ➔")
        self.btn_next.setObjectName("btn_primary")
        self.btn_next.setCursor(Qt.PointingHandCursor)
        self.btn_next.clicked.connect(self.next_requested.emit)
        if not next_label:
            self.btn_next.setVisible(False)
        layout.addWidget(self.btn_next)

    def set_back_visible(self, visible: bool) -> None:
        self.btn_back.setVisible(visible)

    def set_next_visible(self, visible: bool) -> None:
        self.btn_next.setVisible(visible)

    def set_next_enabled(self, enabled: bool) -> None:
        self.btn_next.setEnabled(enabled)

    def set_next_text(self, text: str) -> None:
        self.btn_next.setText(f"{text} ➔")

    def set_back_text(self, text: str) -> None:
        self.btn_back.setText(f"◀ {text}")
