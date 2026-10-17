"""Direct dynamic field mapping panel integrated into canvas workspace."""

import logging
from typing import Dict, List, Optional
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import MatchStatus
from id_card_generator.core.models import PhotoMatchResult, SourceRecord
from id_card_generator.editor.canvas_items import CanvasItem

logger = logging.getLogger(__name__)


class FieldMappingPanel(QWidget):
    """Integrated panel for direct dynamic spreadsheet field mapping and live sample inspection."""

    bind_column_requested = Signal(str)  # column_name
    create_dynamic_requested = Signal(str)  # column_name
    sample_changed = Signal(int)  # sample_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records: List[SourceRecord] = []
        self.match_results: Dict[str, PhotoMatchResult] = []
        self.columns: List[str] = []
        self.current_index: int = 0
        self.selected_item: Optional[CanvasItem] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # 1. Available Spreadsheet Columns
        col_group = QGroupBox("Available Spreadsheet Columns")
        col_layout = QVBoxLayout(col_group)
        col_layout.setContentsMargins(6, 6, 6, 6)
        col_layout.setSpacing(6)

        self.col_list = QListWidget()
        self.col_list.setMaximumHeight(140)
        col_layout.addWidget(self.col_list)

        btn_row = QHBoxLayout()
        self.btn_bind = QPushButton("Bind to Selected")
        self.btn_bind.setToolTip("Bind selected column to currently selected canvas text element")
        self.btn_bind.clicked.connect(self._on_bind_clicked)
        btn_row.addWidget(self.btn_bind)

        self.btn_add_dyn = QPushButton("+ Add Field")
        self.btn_add_dyn.setToolTip("Create a new canvas dynamic text element for selected column")
        self.btn_add_dyn.clicked.connect(self._on_add_dyn_clicked)
        btn_row.addWidget(self.btn_add_dyn)
        col_layout.addLayout(btn_row)

        layout.addWidget(col_group)

        # 2. Live Sample Record Preview
        sample_group = QGroupBox("Live Sample Record Preview")
        sample_layout = QVBoxLayout(sample_group)
        sample_layout.setContentsMargins(6, 6, 6, 6)
        sample_layout.setSpacing(6)

        nav_box = QHBoxLayout()
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedWidth(30)
        self.btn_prev.clicked.connect(self._prev_sample)
        nav_box.addWidget(self.btn_prev)

        self.lbl_record_num = QLabel("0 / 0")
        self.lbl_record_num.setAlignment(Qt.AlignCenter)
        self.lbl_record_num.setStyleSheet("font-weight: 600; color: #38BDF8;")
        nav_box.addWidget(self.lbl_record_num, stretch=1)

        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedWidth(30)
        self.btn_next.clicked.connect(self._next_sample)
        nav_box.addWidget(self.btn_next)
        sample_layout.addLayout(nav_box)

        # Search bar
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search record value...")
        self.txt_search.returnPressed.connect(self._on_search)
        sample_layout.addWidget(self.txt_search)

        # Photo status badge
        photo_box = QHBoxLayout()
        self.lbl_photo_thumb = QLabel()
        self.lbl_photo_thumb.setFixedSize(48, 56)
        self.lbl_photo_thumb.setStyleSheet("background-color: #27272A; border-radius: 4px; border: 1px solid #3F3F46;")
        self.lbl_photo_thumb.setAlignment(Qt.AlignCenter)
        photo_box.addWidget(self.lbl_photo_thumb)

        self.lbl_photo_status = QLabel("No photo loaded")
        self.lbl_photo_status.setWordWrap(True)
        self.lbl_photo_status.setStyleSheet("font-size: 11px;")
        photo_box.addWidget(self.lbl_photo_status, stretch=1)
        sample_layout.addLayout(photo_box)

        # Key-value preview table
        self.tbl_values = QTableWidget()
        self.tbl_values.setColumnCount(2)
        self.tbl_values.setHorizontalHeaderLabels(["Column", "Sample Value"])
        self.tbl_values.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_values.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        sample_layout.addWidget(self.tbl_values)

        layout.addWidget(sample_group)

    def set_dataset(
        self,
        columns: List[str],
        records: List[SourceRecord],
        match_results: Dict[str, PhotoMatchResult],
    ) -> None:
        """Update available dataset and refresh column list and sample preview."""
        self.columns = columns
        self.records = records
        self.match_results = match_results
        self.current_index = 0

        self.col_list.clear()
        for col in columns:
            self.col_list.addItem(col)

        self._refresh_sample_view()

    def set_selected_item(self, item: Optional[CanvasItem]) -> None:
        self.selected_item = item
        self.btn_bind.setEnabled(item is not None)

    def _on_bind_clicked(self) -> None:
        item = self.col_list.currentItem()
        if item:
            self.bind_column_requested.emit(item.text())

    def _on_add_dyn_clicked(self) -> None:
        item = self.col_list.currentItem()
        if item:
            self.create_dynamic_requested.emit(item.text())

    def _prev_sample(self) -> None:
        if not self.records:
            return
        self.current_index = max(0, self.current_index - 1)
        self._refresh_sample_view()
        self.sample_changed.emit(self.current_index)

    def _next_sample(self) -> None:
        if not self.records:
            return
        self.current_index = min(len(self.records) - 1, self.current_index + 1)
        self._refresh_sample_view()
        self.sample_changed.emit(self.current_index)

    def _on_search(self) -> None:
        query = self.txt_search.text().strip().lower()
        if not query or not self.records:
            return

        for idx, rec in enumerate(self.records):
            if query in rec.pin.lower():
                self.current_index = idx
                self._refresh_sample_view()
                self.sample_changed.emit(self.current_index)
                return
            for v in rec.data.values():
                if query in str(v).lower():
                    self.current_index = idx
                    self._refresh_sample_view()
                    self.sample_changed.emit(self.current_index)
                    return

    def _refresh_sample_view(self) -> None:
        total = len(self.records)
        if total == 0:
            self.lbl_record_num.setText("0 / 0")
            self.lbl_photo_status.setText("No records available")
            self.lbl_photo_thumb.clear()
            self.tbl_values.setRowCount(0)
            return

        rec = self.records[self.current_index]
        self.lbl_record_num.setText(f"{self.current_index + 1} of {total}")

        # Photo match
        match = self.match_results.get(rec.record_id)
        if match and match.photo_path and Path(match.photo_path).exists():
            pix = QPixmap(match.photo_path)
            if not pix.isNull():
                self.lbl_photo_thumb.setPixmap(pix.scaled(48, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            if match.status == MatchStatus.OVERRIDDEN:
                self.lbl_photo_status.setText(f"<b style='color: #A855F7;'>Overridden:</b> {Path(match.photo_path).name}")
            else:
                self.lbl_photo_status.setText(f"<b style='color: #22C55E;'>Matched:</b> {Path(match.photo_path).name}")
        elif match and match.status == MatchStatus.AMBIGUOUS:
            avatar = CanvasItem.get_avatar_pixmap()
            if avatar and not avatar.isNull():
                self.lbl_photo_thumb.setPixmap(avatar.scaled(44, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.lbl_photo_thumb.clear()
            self.lbl_photo_status.setText(f"<b style='color: #EAB308;'>Ambiguous:</b> {len(match.candidate_paths)} photos found")
        else:
            avatar = CanvasItem.get_avatar_pixmap()
            if avatar and not avatar.isNull():
                self.lbl_photo_thumb.setPixmap(avatar.scaled(44, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.lbl_photo_thumb.clear()
            self.lbl_photo_status.setText("<b style='color: #EF4444;'>Photo Missing</b>")

        # Values table
        self.tbl_values.setRowCount(len(self.columns))
        for row, col in enumerate(self.columns):
            self.tbl_values.setItem(row, 0, QTableWidgetItem(col))
            val = rec.get_value(col, "")
            self.tbl_values.setItem(row, 1, QTableWidgetItem(val))
