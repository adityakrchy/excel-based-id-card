"""Photoshop-inspired panels for Color Swatches and Action History."""

from typing import List
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class ColorSwatchesPanel(QWidget):
    """Photoshop-inspired Swatches palette with curated card design colors and custom color picker."""

    color_selected = Signal(str)  # hex color string e.g. "#1E3A8A"

    PALETTE = [
        # Blues / Corporate
        ("#0F172A", "Deep Midnight"),
        ("#1E293B", "Slate 800"),
        ("#1E3A8A", "Navy Blue"),
        ("#1D4ED8", "Royal Blue"),
        ("#2563EB", "Corporate Blue"),
        ("#0284C7", "Sky Blue"),
        ("#06B6D4", "Cyan Accent"),
        ("#0D9488", "Teal"),
        # Greens
        ("#064E3B", "Dark Emerald"),
        ("#059669", "Emerald Green"),
        ("#10B981", "Bright Green"),
        ("#84CC16", "Lime"),
        # Warm / Warnings / Badges
        ("#78350F", "Bronze"),
        ("#B45309", "Dark Amber"),
        ("#D97706", "Amber Gold"),
        ("#F59E0B", "Warning Yellow"),
        ("#DC2626", "Crimson Red"),
        ("#BE123C", "Ruby Accent"),
        ("#E11D48", "Rose"),
        ("#7C3AED", "Purple"),
        # Neutrals
        ("#000000", "Pitch Black"),
        ("#475569", "Slate Gray"),
        ("#94A3B8", "Silver"),
        ("#FFFFFF", "Pure White"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        lbl_head = QLabel("<b>Swatches Palette</b>")
        lbl_head.setStyleSheet("color: #E2E8F0; font-size: 12px;")
        layout.addWidget(lbl_head)

        grid_frame = QFrame()
        grid = QGridLayout(grid_frame)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)

        for idx, (hex_code, name) in enumerate(self.PALETTE):
            r = idx // 6
            c = idx % 6
            btn = QToolButton()
            btn.setFixedSize(28, 28)
            btn.setToolTip(f"{name} ({hex_code})")
            border_col = "#64748B" if hex_code == "#FFFFFF" else "rgba(255,255,255,0.15)"
            btn.setStyleSheet(
                f"background-color: {hex_code}; border: 1px solid {border_col}; border-radius: 4px;"
            )
            btn.clicked.connect(lambda ch=False, h=hex_code: self.color_selected.emit(h))
            grid.addWidget(btn, r, c)

        layout.addWidget(grid_frame)

        self.btn_custom = QPushButton("🎨 Custom Color Picker...")
        self.btn_custom.clicked.connect(self._open_custom_picker)
        layout.addWidget(self.btn_custom)

        layout.addStretch()

    def _open_custom_picker(self) -> None:
        col = QColorDialog.getColor(QColor("#2563EB"), self, "Pick Custom Color")
        if col.isValid():
            self.color_selected.emit(col.name().upper())


class HistoryPanel(QWidget):
    """Photoshop-inspired History panel showing action stack with step-back jump support."""

    def __init__(self, undo_stack, parent=None):
        super().__init__(parent)
        self.undo_stack = undo_stack

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        lbl_head = QLabel("<b>History (Action Stack)</b>")
        lbl_head.setStyleSheet("color: #E2E8F0; font-size: 12px;")
        layout.addWidget(lbl_head)

        self.list_history = QListWidget()
        self.list_history.setStyleSheet(
            "QListWidget { background: #18181B; border: 1px solid #3F3F46; border-radius: 6px; } "
            "QListWidget::item { padding: 5px 8px; border-bottom: 1px solid #27272A; } "
            "QListWidget::item:selected { background: #2563EB; color: white; }"
        )
        self.list_history.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_history, stretch=1)

        # Bottom undo/redo buttons
        btn_row = QHBoxLayout()
        self.btn_undo = QPushButton("↶ Step Backward")
        self.btn_undo.clicked.connect(self.undo_stack.undo)
        self.btn_redo = QPushButton("↷ Step Forward")
        self.btn_redo.clicked.connect(self.undo_stack.redo)
        btn_row.addWidget(self.btn_undo)
        btn_row.addWidget(self.btn_redo)
        layout.addLayout(btn_row)

        self.undo_stack.indexChanged.connect(self.refresh_history)
        self.refresh_history()

    def refresh_history(self) -> None:
        try:
            if not self.undo_stack:
                return
            count = self.undo_stack.count()
            curr_idx = self.undo_stack.index()
        except RuntimeError:
            return

        self.list_history.blockSignals(True)
        self.list_history.clear()

        # Base snapshot
        base_item = QListWidgetItem("📄 Document Opened")
        base_item.setData(Qt.UserRole, 0)
        self.list_history.addItem(base_item)

        for i in range(count):
            try:
                text = self.undo_stack.text(i) or f"Action {i + 1}"
            except RuntimeError:
                break
            item = QListWidgetItem(f"⚡ {text}")
            item.setData(Qt.UserRole, i + 1)
            if i + 1 > curr_idx:
                item.setForeground(QColor("#71717A"))  # Undone / dimmed action
            else:
                item.setForeground(QColor("#F4F4F5"))
            self.list_history.addItem(item)

        self.list_history.setCurrentRow(curr_idx)
        self.list_history.blockSignals(False)

        self.btn_undo.setEnabled(self.undo_stack.canUndo())
        self.btn_redo.setEnabled(self.undo_stack.canRedo())

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        target_idx = item.data(Qt.UserRole)
        if target_idx is not None:
            self.undo_stack.setIndex(target_idx)
