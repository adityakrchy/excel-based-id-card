"""Photograph directory scanning, matching review, and manual override panel."""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import MatchStatus
from id_card_generator.core.models import PhotoMatchResult, SourceRecord
from id_card_generator.data.photo_matcher import MatchSummary, PhotoMatcher

logger = logging.getLogger(__name__)


class PhotoLibraryPage(QWidget):
    """Manages photograph directory, displays matching table with thumbnails, and handles overrides."""

    matching_updated = Signal(object, object)  # (match_results_dict, match_summary)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.matcher = PhotoMatcher()
        self.records: List[SourceRecord] = []
        self.match_results: Dict[str, PhotoMatchResult] = {}
        self.match_summary: Optional[MatchSummary] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 1. Directory Selection Card
        top_card = QFrame()
        top_card.setObjectName("card_panel")
        top_layout = QHBoxLayout(top_card)

        self.btn_select_dir = QPushButton("Select Photo Folder...")
        self.btn_select_dir.setObjectName("btn_primary")
        self.btn_select_dir.clicked.connect(self._browse_directory)

        self.lbl_photo_dir = QLabel("<i>No photo directory selected</i>")
        self.lbl_photo_dir.setStyleSheet("color: #94A3B8; font-weight: 500;")

        self.btn_rescan = QPushButton("Rescan Directory")
        self.btn_rescan.setEnabled(False)
        self.btn_rescan.clicked.connect(self._rescan)

        top_layout.addWidget(self.btn_select_dir)
        top_layout.addWidget(self.lbl_photo_dir, stretch=1)
        top_layout.addWidget(self.btn_rescan)
        layout.addWidget(top_card)

        # 2. Filter & Summary Bar
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter Records:"))
        self.cmb_filter = QComboBox()
        self.cmb_filter.addItems([
            "All Records",
            "Matched Photos Only",
            "Missing Photos Only",
            "Ambiguous Matches Only",
            "Overridden Photos Only",
        ])
        self.cmb_filter.currentIndexChanged.connect(self._filter_table)
        filter_row.addWidget(self.cmb_filter)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search by PIN or Name...")
        self.txt_search.textChanged.connect(self._filter_table)
        filter_row.addWidget(self.txt_search, stretch=1)

        self.lbl_metrics = QLabel("0 matched")
        self.lbl_metrics.setStyleSheet("font-weight: 600; color: #64748B;")
        filter_row.addWidget(self.lbl_metrics)
        layout.addLayout(filter_row)

        # 3. Matching Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "PIN Number",
            "Name",
            "Thumbnail",
            "Match Status",
            "Resolved File Path",
            "Override Action",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setIconSize(self.table.iconSize() * 2)
        layout.addWidget(self.table)

    def set_records(self, records: List[SourceRecord]) -> None:
        """Receive imported spreadsheet records."""
        self.records = records
        self._rematch()

    def set_directory(self, photo_dir: Path) -> None:
        """Set photograph directory path."""
        self.lbl_photo_dir.setText(str(photo_dir))
        self.btn_rescan.setEnabled(True)
        self.matcher.set_directory(photo_dir)
        self._rematch()

    def _browse_directory(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Photograph Directory")
        if folder:
            self.set_directory(Path(folder))

    def _rescan(self) -> None:
        self.matcher.rescan()
        self._rematch()

    def _rematch(self) -> None:
        if not self.records:
            return

        self.match_results, self.match_summary = self.matcher.match_all(self.records)

        s = self.match_summary
        self.lbl_metrics.setText(
            f"{s.matched_count} matched • {s.missing_count} missing • "
            f"{s.ambiguous_count} ambiguous • {s.overridden_count} overridden"
        )

        self._populate_table()
        self.matching_updated.emit(self.match_results, self.match_summary)

    def _populate_table(self) -> None:
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.records))

        for row_idx, rec in enumerate(self.records):
            match = self.match_results.get(rec.record_id)

            # PIN Number
            item_pin = QTableWidgetItem(rec.pin or rec.raw_pin)
            self.table.setItem(row_idx, 0, item_pin)

            # Name
            item_name = QTableWidgetItem(rec.get_value("Name", ""))
            self.table.setItem(row_idx, 1, item_name)

            # Thumbnail
            thumb_item = QTableWidgetItem()
            if match and match.photo_path and Path(match.photo_path).exists():
                pix = QPixmap(match.photo_path)
                if not pix.isNull():
                    thumb_item.setIcon(QIcon(pix.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            self.table.setItem(row_idx, 2, thumb_item)

            # Match Status
            status_text = match.status.value.upper() if match else "MISSING"
            item_status = QTableWidgetItem(status_text)
            if match and match.status in (MatchStatus.MATCHED, MatchStatus.OVERRIDDEN):
                item_status.setForeground(QColor("#059669"))
            elif match and match.status == MatchStatus.AMBIGUOUS:
                item_status.setForeground(QColor("#D97706"))
                item_status.setBackground(QColor(245, 158, 11, 40))
            else:
                item_status.setForeground(QColor("#DC2626"))
                item_status.setBackground(QColor(239, 68, 68, 40))

            item_status.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 3, item_status)

            # Resolved Path
            path_str = match.photo_path or match.details if match else "No match"
            item_path = QTableWidgetItem(path_str)
            self.table.setItem(row_idx, 4, item_path)

            # Action button
            action_btn = QPushButton("Override..." if not match or not match.is_overridden else "Clear Override")
            if match and match.is_overridden:
                action_btn.clicked.connect(lambda ch=False, p=rec.pin: self._clear_override(p))
            else:
                action_btn.clicked.connect(lambda ch=False, p=rec.pin: self._manual_override(p))
            self.table.setCellWidget(row_idx, 5, action_btn)

        self._filter_table()

    def _manual_override(self, pin: str) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select Photograph for PIN '{pin}'",
            str(self.matcher.photo_dir) if self.matcher.photo_dir else "",
            "Images (*.jpg *.jpeg *.png *.bmp *.webp *.tiff)",
        )
        if file_path:
            self.matcher.set_override(pin, file_path)
            self._rematch()

    def _clear_override(self, pin: str) -> None:
        self.matcher.remove_override(pin)
        self._rematch()

    def _filter_table(self) -> None:
        filter_idx = self.cmb_filter.currentIndex()
        query = self.txt_search.text().lower().strip()

        for r in range(self.table.rowCount()):
            status_item = self.table.item(r, 3)
            status_text = status_item.text() if status_item else ""

            # Check status match
            status_ok = True
            if filter_idx == 1 and "MATCHED" not in status_text and "OVERRIDDEN" not in status_text:
                status_ok = False
            elif filter_idx == 2 and "MISSING" not in status_text:
                status_ok = False
            elif filter_idx == 3 and "AMBIGUOUS" not in status_text:
                status_ok = False
            elif filter_idx == 4 and "OVERRIDDEN" not in status_text:
                status_ok = False

            # Check query match
            query_ok = True
            if query:
                pin_text = self.table.item(r, 0).text().lower() if self.table.item(r, 0) else ""
                name_text = self.table.item(r, 1).text().lower() if self.table.item(r, 1) else ""
                query_ok = (query in pin_text or query in name_text)

            self.table.setRowHidden(r, not (status_ok and query_ok))
