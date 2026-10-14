"""Photograph directory scanning, generic lookup matching, and manual override panel."""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
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
    """Manages photograph directory, generic column matching, and manual associations."""

    matching_updated = Signal(object, object)  # (match_results_dict, match_summary)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.matcher = PhotoMatcher()
        self.records: List[SourceRecord] = []
        self.columns: List[str] = []
        self.match_results: Dict[str, PhotoMatchResult] = {}
        self.match_summary: Optional[MatchSummary] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Directory Selection Card
        top_card = QFrame()
        top_card.setObjectName("card_panel")
        top_layout = QHBoxLayout(top_card)

        self.btn_select_dir = QPushButton("Select Photo Folder...")
        self.btn_select_dir.setObjectName("btn_primary")
        self.btn_select_dir.clicked.connect(self._browse_directory)

        self.lbl_photo_dir = QLabel("<i>No photo directory selected</i>")
        self.lbl_photo_dir.setStyleSheet("color: #94A3B8; font-weight: 500;")

        self.btn_rescan = QPushButton("Rescan Folder")
        self.btn_rescan.setEnabled(False)
        self.btn_rescan.clicked.connect(self._rescan)

        top_layout.addWidget(self.btn_select_dir)
        top_layout.addWidget(self.lbl_photo_dir, stretch=1)
        top_layout.addWidget(self.btn_rescan)
        layout.addWidget(top_card)

        # 2. Matching Rules Card (Generic Column, Prefix, Suffix)
        rules_card = QFrame()
        rules_card.setObjectName("card_panel")
        rules_layout = QHBoxLayout(rules_card)
        rules_layout.setContentsMargins(10, 8, 10, 8)
        rules_layout.setSpacing(12)

        rules_layout.addWidget(QLabel("<b>Photo Lookup Key Column:</b>"))
        self.cmb_key_col = QComboBox()
        self.cmb_key_col.addItem("Auto-Detect (PIN / ID)")
        self.cmb_key_col.currentIndexChanged.connect(self._on_rule_changed)
        rules_layout.addWidget(self.cmb_key_col)

        rules_layout.addSpacing(8)
        rules_layout.addWidget(QLabel("Prefix:"))
        self.txt_prefix = QLineEdit()
        self.txt_prefix.setPlaceholderText("e.g. EMP_")
        self.txt_prefix.setFixedWidth(80)
        self.txt_prefix.textChanged.connect(self._on_rule_changed)
        rules_layout.addWidget(self.txt_prefix)

        rules_layout.addWidget(QLabel("Suffix:"))
        self.txt_suffix = QLineEdit()
        self.txt_suffix.setPlaceholderText("e.g. _id")
        self.txt_suffix.setFixedWidth(80)
        self.txt_suffix.textChanged.connect(self._on_rule_changed)
        rules_layout.addWidget(self.txt_suffix)

        rules_layout.addStretch()
        layout.addWidget(rules_card)

        # 3. Filter & Summary Metrics Bar
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
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
        self.txt_search.setPlaceholderText("Search by identifier, name, or file...")
        self.txt_search.textChanged.connect(self._filter_table)
        filter_row.addWidget(self.txt_search, stretch=1)

        self.lbl_metrics = QLabel("0 matched")
        self.lbl_metrics.setStyleSheet("font-weight: 600; color: #60CDFF;")
        filter_row.addWidget(self.lbl_metrics)
        layout.addLayout(filter_row)

        # 4. Association Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Lookup Key Value",
            "Record Name / Info",
            "Thumbnail",
            "Match Status",
            "Selected Image File",
            "Override Status",
            "Action",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setIconSize(self.table.iconSize() * 2)
        layout.addWidget(self.table)

    def set_columns(self, columns: List[str]) -> None:
        """Set available spreadsheet columns in lookup combo."""
        self.columns = columns
        self.cmb_key_col.blockSignals(True)
        self.cmb_key_col.clear()
        self.cmb_key_col.addItem("Auto-Detect (PIN / ID)", "")
        for col in columns:
            self.cmb_key_col.addItem(col, col)
        self.cmb_key_col.blockSignals(False)

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

    def _on_rule_changed(self) -> None:
        key_col = self.cmb_key_col.currentData()
        self.matcher.set_key_column(key_col if key_col else None)
        self.matcher.set_affixes(
            prefix=self.txt_prefix.text().strip(),
            suffix=self.txt_suffix.text().strip(),
        )
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
            key_val = self.matcher.get_lookup_key_value(rec)

            # 0. Lookup Key
            item_key = QTableWidgetItem(key_val or rec.pin)
            self.table.setItem(row_idx, 0, item_key)

            # 1. Name or other column
            name = rec.get_value("Name", "")
            if not name:
                for k, v in rec.data.items():
                    if "name" in k.lower() and v:
                        name = str(v)
                        break
            item_name = QTableWidgetItem(name)
            self.table.setItem(row_idx, 1, item_name)

            # 2. Thumbnail
            thumb_item = QTableWidgetItem()
            if match and match.photo_path and Path(match.photo_path).exists():
                pix = QPixmap(match.photo_path)
                if not pix.isNull():
                    thumb_item.setIcon(QIcon(pix.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            self.table.setItem(row_idx, 2, thumb_item)

            # 3. Match Status
            status_text = match.status.value.upper() if match else "MISSING"
            item_status = QTableWidgetItem(status_text)
            if match and match.status in (MatchStatus.MATCHED, MatchStatus.OVERRIDDEN):
                item_status.setForeground(QColor("#22C55E"))
            elif match and match.status == MatchStatus.AMBIGUOUS:
                item_status.setForeground(QColor("#EAB308"))
            else:
                item_status.setForeground(QColor("#EF4444"))

            item_status.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 3, item_status)

            # 4. Resolved Path
            path_str = match.photo_path or match.details if match else "No match"
            item_path = QTableWidgetItem(path_str)
            self.table.setItem(row_idx, 4, item_path)

            # 5. Override Status
            override_str = "Custom Override" if (match and match.is_overridden) else "Automatic"
            item_override = QTableWidgetItem(override_str)
            if match and match.is_overridden:
                item_override.setForeground(QColor("#A855F7"))
            self.table.setItem(row_idx, 5, item_override)

            # 6. Action button
            action_btn = QPushButton("Assign Photo..." if not match or not match.is_overridden else "Clear Override")
            if match and match.is_overridden:
                action_btn.clicked.connect(lambda ch=False, rid=rec.record_id: self._clear_override(rid))
            else:
                action_btn.clicked.connect(lambda ch=False, rid=rec.record_id, kv=key_val: self._manual_override(rid, kv))
            self.table.setCellWidget(row_idx, 6, action_btn)

        self._filter_table()

    def _manual_override(self, record_id: str, key_val: str) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select Photograph for Record '{key_val}'",
            str(self.matcher.photo_dir) if self.matcher.photo_dir else "",
            "Images (*.jpg *.jpeg *.png *.bmp *.webp *.tiff)",
        )
        if file_path:
            self.matcher.set_override(record_id, file_path)
            if key_val:
                self.matcher.set_override(key_val, file_path)
            self._rematch()

    def _clear_override(self, record_id: str) -> None:
        self.matcher.remove_override(record_id)
        self._rematch()

    def _filter_table(self) -> None:
        filter_idx = self.cmb_filter.currentIndex()
        query = self.txt_search.text().lower().strip()

        for r in range(self.table.rowCount()):
            status_item = self.table.item(r, 3)
            status_text = status_item.text() if status_item else ""

            status_ok = True
            if filter_idx == 1 and "MATCHED" not in status_text and "OVERRIDDEN" not in status_text:
                status_ok = False
            elif filter_idx == 2 and "MISSING" not in status_text:
                status_ok = False
            elif filter_idx == 3 and "AMBIGUOUS" not in status_text:
                status_ok = False
            elif filter_idx == 4 and "OVERRIDDEN" not in status_text:
                status_ok = False

            query_ok = True
            if query:
                key_text = self.table.item(r, 0).text().lower() if self.table.item(r, 0) else ""
                name_text = self.table.item(r, 1).text().lower() if self.table.item(r, 1) else ""
                path_text = self.table.item(r, 4).text().lower() if self.table.item(r, 4) else ""
                query_ok = (query in key_text or query in name_text or query in path_text)

            self.table.setRowHidden(r, not (status_ok and query_ok))
