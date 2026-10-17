"""Photograph directory scanning, high-throughput queue processing, streaming display, and lookup matching."""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import MatchStatus, WorkflowStep
from id_card_generator.core.models import PhotoMatchResult, ProjectConfiguration, SourceRecord
from id_card_generator.core.project_manager import ProjectManager
from id_card_generator.data.photo_matcher import MatchSummary, PhotoMatcher
from id_card_generator.tasks.photo_indexing_worker import PhotoIndexingWorker
from id_card_generator.ui.step_nav_bar import StepNavBar

logger = logging.getLogger(__name__)


class PhotoLibraryPage(QWidget):
    """Manages photograph directory scanning, streaming indexing queue, and manual associations."""

    matching_updated = Signal(object, object)  # (match_results_dict, match_summary)
    navigate_requested = Signal(str)  # WorkflowStep value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_config: Optional[ProjectConfiguration] = None
        self.matcher = PhotoMatcher()
        self.records: List[SourceRecord] = []
        self.columns: List[str] = []
        self.match_results: Dict[str, PhotoMatchResult] = {}
        self.match_summary: Optional[MatchSummary] = None
        self._worker: Optional[PhotoIndexingWorker] = None
        self._indexed_count: int = 0

        self._setup_ui()

    def set_project_config(self, config: Optional[ProjectConfiguration]) -> None:
        """Associate active project workspace configuration."""
        self.project_config = config

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 1. Directory Selection Card
        top_card = QFrame()
        top_card.setObjectName("card_panel")
        top_vlayout = QVBoxLayout(top_card)

        top_layout = QHBoxLayout()

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
        top_vlayout.addLayout(top_layout)

        # Workspace copied photos badge
        self.lbl_workspace_photos = QLabel("")
        self.lbl_workspace_photos.setStyleSheet("color: #10B981; font-weight: 600; font-size: 11px;")
        self.lbl_workspace_photos.setVisible(False)
        top_vlayout.addWidget(self.lbl_workspace_photos)

        layout.addWidget(top_card)

        # 2. Live Background Queue & Indexing Banner (Visible during scanning)
        self.queue_card = QFrame()
        self.queue_card.setObjectName("card_panel")
        queue_layout = QVBoxLayout(self.queue_card)
        queue_layout.setContentsMargins(12, 10, 12, 10)
        queue_layout.setSpacing(6)

        queue_header_row = QHBoxLayout()
        self.lbl_queue_status = QLabel("⚡ Background Photo Indexing Queue Idle")
        self.lbl_queue_status.setStyleSheet("font-weight: 600; color: #38BDF8;")
        queue_header_row.addWidget(self.lbl_queue_status, stretch=1)

        self.lbl_queue_latest = QLabel("")
        self.lbl_queue_latest.setStyleSheet("color: #94A3B8; font-size: 11px; font-family: monospace;")
        queue_header_row.addWidget(self.lbl_queue_latest)

        self.btn_stop_queue = QPushButton("Stop Scan")
        self.btn_stop_queue.setFixedWidth(80)
        self.btn_stop_queue.setVisible(False)
        self.btn_stop_queue.clicked.connect(self._stop_indexing)
        queue_header_row.addWidget(self.btn_stop_queue)

        queue_layout.addLayout(queue_header_row)

        self.progress_queue = QProgressBar()
        self.progress_queue.setRange(0, 0)  # indeterminate while counting
        self.progress_queue.setFixedHeight(8)
        self.progress_queue.setVisible(False)
        queue_layout.addWidget(self.progress_queue)

        layout.addWidget(self.queue_card)

        # 3. Matching Rules Card (Generic Column, Prefix, Suffix)
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

        # 4. Tabbed Workspace: Record Associations vs Live Photo Stream
        self.tabs = QTabWidget()

        # --- TAB 1: SPREADSHEET ASSOCIATIONS ---
        tab_records = QWidget()
        tab_rec_layout = QVBoxLayout(tab_records)
        tab_rec_layout.setContentsMargins(0, 8, 0, 0)
        tab_rec_layout.setSpacing(8)

        # Filter & Summary Metrics Bar
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

        # Dedicated quick override buttons in toolbar
        self.btn_assign_selected = QPushButton("Assign Photo...")
        self.btn_assign_selected.setToolTip("Assign custom photo to currently selected record")
        self.btn_assign_selected.clicked.connect(self._assign_selected_row)
        filter_row.addWidget(self.btn_assign_selected)

        self.btn_clear_selected = QPushButton("Clear Override")
        self.btn_clear_selected.setToolTip("Clear custom photo override for selected record")
        self.btn_clear_selected.clicked.connect(self._clear_selected_row)
        filter_row.addWidget(self.btn_clear_selected)

        self.lbl_metrics = QLabel("0 matched")
        self.lbl_metrics.setStyleSheet("font-weight: 600; color: #60CDFF;")
        filter_row.addWidget(self.lbl_metrics)
        tab_rec_layout.addLayout(filter_row)

        # Association Table
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
        tab_rec_layout.addWidget(self.table)
        self.tabs.addTab(tab_records, "Record Associations (0)")

        # --- TAB 2: LIVE STREAMED PHOTO QUEUE ---
        tab_stream = QWidget()
        tab_stream_layout = QVBoxLayout(tab_stream)
        tab_stream_layout.setContentsMargins(0, 8, 0, 0)
        tab_stream_layout.setSpacing(8)

        stream_info = QLabel(
            "Displays photographs as they are discovered and indexed by the high-speed background queue."
        )
        stream_info.setStyleSheet("color: #64748B; font-size: 12px;")
        tab_stream_layout.addWidget(stream_info)

        self.table_stream = QTableWidget()
        self.table_stream.setColumnCount(4)
        self.table_stream.setHorizontalHeaderLabels([
            "Normalized ID Stem",
            "File Name",
            "Full Path",
            "Indexed Status",
        ])
        self.table_stream.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_stream.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        tab_stream_layout.addWidget(self.table_stream)
        self.tabs.addTab(tab_stream, "Live Photo Queue (0)")

        layout.addWidget(self.tabs, stretch=1)

        # 5. Bottom Step Navigation Bar
        self.nav_bar = StepNavBar(
            prev_label="Data Source",
            next_label="Choose Template",
            step_badge="Step 2 of 7: Photo Library",
            parent=self,
        )
        self.nav_bar.back_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.DATA_SOURCE.value))
        self.nav_bar.next_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.TEMPLATES.value))
        layout.addWidget(self.nav_bar)

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
        self.tabs.setTabText(0, f"Record Associations ({len(records)})")
        self._rematch()

    def set_directory(self, photo_dir: Path) -> None:
        """Set photograph directory path and launch background streaming scanner."""
        photo_dir = Path(photo_dir)
        self.lbl_photo_dir.setText(str(photo_dir))
        self.btn_rescan.setEnabled(True)
        self.matcher.photo_dir = photo_dir
        self._start_indexing(photo_dir)

    def _start_indexing(self, photo_dir: Path) -> None:
        """Launch background PhotoIndexingWorker thread."""
        self._stop_indexing()

        self._indexed_count = 0
        self.table_stream.setRowCount(0)
        self.tabs.setTabText(1, "Live Photo Queue (0)")
        self.lbl_queue_status.setText(f"⚡ Fast Indexing Queue Active: Reading {photo_dir.name}...")
        self.lbl_queue_latest.setText("Scanning folder...")
        self.progress_queue.setVisible(True)
        self.btn_stop_queue.setVisible(True)

        self._worker = PhotoIndexingWorker(photo_dir=photo_dir, batch_size=500, parent=self)
        self._worker.batch_discovered.connect(self._on_worker_batch)
        self._worker.indexing_finished.connect(self._on_worker_finished)
        self._worker.indexing_failed.connect(self._on_worker_failed)
        self._worker.indexing_cancelled.connect(self._on_worker_cancelled)
        self._worker.start()

    def _stop_indexing(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(500)
            self._worker = None
        self.progress_queue.setVisible(False)
        self.btn_stop_queue.setVisible(False)

    def _on_worker_batch(self, batch: List[tuple], total_so_far: int, latest_name: str) -> None:
        """Incremental streaming update as items are read from disk."""
        self._indexed_count = total_so_far
        self.lbl_queue_status.setText(
            f"⚡ Fast Indexing Queue Active: {total_so_far:,} images processed and indexed"
        )
        self.lbl_queue_latest.setText(f"Reading: {latest_name}")
        self.tabs.setTabText(1, f"Live Photo Queue ({total_so_far:,})")

        # Stream into live table (keep max 60 rows rolling smoothly)
        MAX_STREAM_ROWS = 60
        self.table_stream.setUpdatesEnabled(False)
        for stem, path_str in batch:
            row = self.table_stream.rowCount()
            if row >= MAX_STREAM_ROWS:
                self.table_stream.removeRow(0)
                row = self.table_stream.rowCount()

            self.table_stream.insertRow(row)
            item_stem = QTableWidgetItem(stem)
            item_name = QTableWidgetItem(Path(path_str).name)
            item_path = QTableWidgetItem(path_str)
            item_status = QTableWidgetItem("✓ Indexed")
            item_status.setForeground(QColor("#22C55E"))

            self.table_stream.setItem(row, 0, item_stem)
            self.table_stream.setItem(row, 1, item_name)
            self.table_stream.setItem(row, 2, item_path)
            self.table_stream.setItem(row, 3, item_status)

        self.table_stream.scrollToBottom()
        self.table_stream.setUpdatesEnabled(True)

    def _on_worker_finished(self, exact_index: dict, lower_index: dict, total: int) -> None:
        """Worker completed scanning all directory items."""
        self.progress_queue.setVisible(False)
        self.btn_stop_queue.setVisible(False)
        self.matcher.set_indexes(exact_index, lower_index)

        self.lbl_queue_status.setText(
            f"✓ Ready: {total:,} photographs indexed and cached in memory."
        )
        self.lbl_queue_latest.setText(f"{len(exact_index):,} unique stems")
        self.tabs.setTabText(1, f"Live Photo Queue ({total:,})")

        self._rematch()

    def _on_worker_failed(self, error_msg: str) -> None:
        self.progress_queue.setVisible(False)
        self.btn_stop_queue.setVisible(False)
        self.lbl_queue_status.setText(f"⚠ Scanning Error: {error_msg}")

    def _on_worker_cancelled(self) -> None:
        self.progress_queue.setVisible(False)
        self.btn_stop_queue.setVisible(False)
        self.lbl_queue_status.setText(f"Scan stopped. {self._indexed_count:,} photos indexed.")

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
        if self.matcher.photo_dir:
            self.set_directory(self.matcher.photo_dir)

    def _rematch(self) -> None:
        if not self.records:
            return

        self.match_results, self.match_summary = self.matcher.match_all(self.records)

        # Copy ONLY matched photographs into the workspace/photos directory
        if self.project_config and self.project_config.workspace_dir:
            try:
                self.match_results, copied_count = ProjectManager.copy_matched_photos_to_workspace(
                    self.project_config, self.match_results
                )
                if copied_count > 0:
                    self.lbl_workspace_photos.setText(
                        f"✓ Copied {copied_count} matched photo(s) into workspace: photos/"
                    )
                    self.lbl_workspace_photos.setVisible(True)
                elif any(
                    m.status in (MatchStatus.MATCHED, MatchStatus.OVERRIDDEN)
                    or (hasattr(m.status, "value") and m.status.value in ("matched", "overridden"))
                    for m in self.match_results.values()
                ):
                    self.lbl_workspace_photos.setText(
                        "✓ Matched photographs stored in workspace: photos/"
                    )
                    self.lbl_workspace_photos.setVisible(True)
            except Exception as e:
                logger.warning("Error copying matched photos to workspace: %s", e)

        s = self.match_summary
        self.lbl_metrics.setText(
            f"{s.matched_count} matched • {s.missing_count} missing • "
            f"{s.ambiguous_count} ambiguous • {s.overridden_count} overridden"
        )
        self.tabs.setTabText(0, f"Record Associations ({s.matched_count}/{len(self.records)} Matched)")

        self._populate_table()
        self.matching_updated.emit(self.match_results, self.match_summary)

    def _populate_table(self) -> None:
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        total_records = len(self.records)
        self.table.setRowCount(total_records)

        # Thumbnails are loaded for initial visible rows to prevent Qt GUI freeze
        MAX_INITIAL_THUMBS = 50

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

            # 2. Thumbnail (Lazy load initial set)
            thumb_item = QTableWidgetItem()
            if row_idx < MAX_INITIAL_THUMBS and match and match.photo_path and Path(match.photo_path).exists():
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
            path_str = match.photo_path or (match.details if match else "No match")
            item_path = QTableWidgetItem(path_str)
            self.table.setItem(row_idx, 4, item_path)

            # 5. Override Status
            override_str = "Custom Override" if (match and match.is_overridden) else "Automatic"
            item_override = QTableWidgetItem(override_str)
            if match and match.is_overridden:
                item_override.setForeground(QColor("#A855F7"))
            self.table.setItem(row_idx, 5, item_override)

            # 6. Action button with explicit row parameters
            action_btn = QPushButton("Clear" if (match and match.is_overridden) else "Assign...")
            action_btn.setFixedWidth(75)
            if match and match.is_overridden:
                action_btn.setStyleSheet("color: #EC4899; font-weight: bold;")
                action_btn.clicked.connect(
                    lambda ch=False, rid=rec.record_id, kv=key_val, p=rec.pin: self._clear_override(rid, kv, p)
                )
            else:
                action_btn.setStyleSheet("color: #38BDF8;")
                action_btn.clicked.connect(
                    lambda ch=False, rid=rec.record_id, kv=key_val, p=rec.pin: self._manual_override(rid, kv, p)
                )
            self.table.setCellWidget(row_idx, 6, action_btn)

        self.table.setUpdatesEnabled(True)
        self._filter_table()

    def _assign_selected_row(self) -> None:
        """Assign custom photo to the currently selected table row."""
        row = self.table.currentRow()
        if 0 <= row < len(self.records):
            rec = self.records[row]
            key_val = self.matcher.get_lookup_key_value(rec)
            self._manual_override(rec.record_id, key_val, rec.pin)

    def _clear_selected_row(self) -> None:
        """Clear custom photo override for the currently selected table row."""
        row = self.table.currentRow()
        if 0 <= row < len(self.records):
            rec = self.records[row]
            key_val = self.matcher.get_lookup_key_value(rec)
            self._clear_override(rec.record_id, key_val, rec.pin)

    def _manual_override(self, record_id: str, key_val: str, pin: str = "") -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select Photograph for Record '{key_val or pin}'",
            str(self.matcher.photo_dir) if self.matcher.photo_dir else "",
            "Images (*.jpg *.jpeg *.png *.bmp *.webp *.tiff)",
        )
        if file_path:
            p = Path(file_path).resolve()
            if self.project_config and self.project_config.workspace_dir:
                try:
                    p = ProjectManager.copy_single_photo_to_workspace(self.project_config, p, pin=pin or key_val)
                    file_path = str(p)
                except Exception as e:
                    logger.warning("Could not copy override photo to workspace: %s", e)

            logger.info("Setting manual photo override for record_id=%s, file=%s", record_id, file_path)
            self.matcher.set_override(record_id, file_path)
            if key_val:
                self.matcher.set_override(key_val, file_path)
            if pin:
                self.matcher.set_override(pin, file_path)
            self._rematch()

    def _clear_override(self, record_id: str, key_val: str = "", pin: str = "") -> None:
        logger.info("Clearing manual photo override for record_id=%s, key_val=%s, pin=%s", record_id, key_val, pin)
        self.matcher.remove_override(record_id, key_val, pin)
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
