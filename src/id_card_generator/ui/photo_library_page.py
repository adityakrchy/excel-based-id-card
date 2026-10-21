"""Photograph directory scanning, high-throughput queue processing, streaming display, and lookup matching."""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import QThread, QThreadPool, Qt, Signal
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
from id_card_generator.tasks.photo_match_worker import PhotoMatchWorker
from id_card_generator.ui import workflow
from id_card_generator.ui.components.layout_blocks import OverflowMenu, StatLine
from id_card_generator.ui.components.page_scaffold import InlineNotice, PageFooter, PageHeader
from id_card_generator.ui.studio_tokens import (
    PRIMARY,
    SEMANTIC_SUCCESS,
    SEMANTIC_WARNING,
    SIZES,
)
from id_card_generator.ui.photo_thumbnails import (
    ThumbnailCache,
    ThumbnailSignals,
    ThumbnailTask,
)

logger = logging.getLogger(__name__)

# Every control in a row uses the same height as the rest of the app.
CONTROL_HEIGHT = SIZES.CONTROL_HEIGHT

# Number of thumbnails that are decoded for the visible rows.
MAX_VISIBLE_THUMBS = 60


class PhotoLibraryPage(QWidget):
    """Manages photograph directory scanning, streaming indexing queue, and manual associations."""

    matching_updated = Signal(object, object)  # (match_results_dict, match_summary)
    navigate_requested = Signal(str)  # WorkflowStep value
    lookup_column_changed = Signal(str)  # the column the photos are looked up by

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_config: Optional[ProjectConfiguration] = None
        self.matcher = PhotoMatcher()
        self.records: List[SourceRecord] = []
        self.columns: List[str] = []
        self.match_results: Dict[str, PhotoMatchResult] = {}
        self.match_summary: Optional[MatchSummary] = None
        self._worker: Optional[PhotoIndexingWorker] = None
        self._match_worker: Optional[PhotoMatchWorker] = None
        self._indexed_count: int = 0

        # Thumbnails are decoded on a thread pool and kept in a small cache.
        self._thumbnail_cache = ThumbnailCache()
        self._thumbnail_signals = ThumbnailSignals(self)
        self._thumbnail_signals.ready.connect(self._on_thumbnail_ready)
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(max(2, min(8, (__import__("os").cpu_count() or 2))))

        # Incremented for every match request so stale results are dropped.
        self._match_generation = 0

        # Workers that are still shutting down.  Their reference must not be
        # dropped: destroying a QThread while it is running crashes the app.
        self._retired_workers: List[QThread] = []

        self._setup_ui()

    def set_project_config(self, config: Optional[ProjectConfiguration]) -> None:
        """Associate active project workspace configuration."""
        self.project_config = config

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Page header ---------------------------------------------------------
        badge, title, subtitle = workflow.page_header_text(WorkflowStep.PHOTOS)
        # The page header block is removed from the shell.  Kept off-canvas
        # as a state mirror for tests.
        self.page_header = PageHeader(title, subtitle, badge, parent=self)
        self.page_header.hide()

        self.notice = InlineNotice()
        notice_row = QHBoxLayout()
        notice_row.setContentsMargins(16, 8, 16, 0)
        notice_row.addWidget(self.notice)
        layout.addLayout(notice_row)

        body = QVBoxLayout()
        body.setContentsMargins(16, 12, 16, 12)
        body.setSpacing(10)
        layout.addLayout(body, stretch=1)

        # 1. Source bar: the folder, one primary action, the rest in a menu
        top_card = QFrame()
        top_card.setObjectName("card_panel")
        top_vlayout = QVBoxLayout(top_card)
        top_vlayout.setContentsMargins(14, 10, 14, 10)
        top_vlayout.setSpacing(8)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)

        # Flipped like the data source bar: the primary folder actions lead
        # the row on the left, and the selected path closes it on the right.
        self.btn_select_dir = QPushButton("Select Photo Folder...")
        self.btn_select_dir.setObjectName("btn_primary")
        self.btn_select_dir.setFixedHeight(CONTROL_HEIGHT)
        self.btn_select_dir.clicked.connect(self._browse_directory)
        top_layout.addWidget(self.btn_select_dir)

        self.btn_rescan = QPushButton("Rescan")
        self.btn_rescan.setObjectName("btn_secondary")
        self.btn_rescan.setFixedHeight(CONTROL_HEIGHT)
        self.btn_rescan.setEnabled(False)
        self.btn_rescan.clicked.connect(self._rescan)
        top_layout.addWidget(self.btn_rescan)

        self.lbl_photo_dir = QLabel("No photo directory selected")
        self.lbl_photo_dir.setProperty("role", "monoMuted")
        top_layout.addWidget(self.lbl_photo_dir, stretch=1)

        top_vlayout.addLayout(top_layout)

        # Workspace copied photos badge
        self.lbl_workspace_photos = QLabel("")
        self.lbl_workspace_photos.setProperty("role", "pageSubtitle")
        self.lbl_workspace_photos.setVisible(False)
        top_vlayout.addWidget(self.lbl_workspace_photos)

        body.addWidget(top_card)

        # 2. The indexing queue is a slim status line, not a panel
        self.queue_card = QFrame()
        self.queue_card.setObjectName("card_panel")
        queue_layout = QHBoxLayout(self.queue_card)
        queue_layout.setContentsMargins(14, 8, 14, 8)
        queue_layout.setSpacing(10)

        # Flipped: the queue summary numbers lead on the left, and the
        # status message closes the row on the right.
        self.lbl_queue_latest = QLabel("")
        self.lbl_queue_latest.setProperty("role", "monoMuted")
        queue_layout.addWidget(self.lbl_queue_latest)

        self.progress_queue = QProgressBar()
        self.progress_queue.setRange(0, 0)  # indeterminate while counting
        self.progress_queue.setFixedWidth(120)
        self.progress_queue.setFixedHeight(4)
        self.progress_queue.setVisible(False)
        queue_layout.addWidget(self.progress_queue)

        self.btn_stop_queue = QPushButton("Stop")
        self.btn_stop_queue.setObjectName("btn_secondary")
        self.btn_stop_queue.setFixedHeight(CONTROL_HEIGHT)
        self.btn_stop_queue.setVisible(False)
        self.btn_stop_queue.clicked.connect(self._stop_indexing)
        queue_layout.addWidget(self.btn_stop_queue)

        self.lbl_queue_status = QLabel("Idle")
        self.lbl_queue_status.setProperty("role", "pageSubtitle")
        queue_layout.addWidget(self.lbl_queue_status, stretch=1)

        body.addWidget(self.queue_card)

        # 3. Matching rules - one quiet row
        rules_card = QFrame()
        rules_card.setObjectName("card_panel")
        rules_layout = QHBoxLayout(rules_card)
        rules_layout.setContentsMargins(14, 8, 14, 8)
        rules_layout.setSpacing(10)

        lbl_rules = QLabel("LOOKUP")
        lbl_rules.setProperty("role", "sectionLabel")
        rules_layout.addWidget(lbl_rules)

        self.cmb_key_col = QComboBox()
        self.cmb_key_col.addItem("Auto-detect (PIN / ID)")
        self.cmb_key_col.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_key_col.currentIndexChanged.connect(self._on_rule_changed)
        rules_layout.addWidget(self.cmb_key_col)

        self.txt_prefix = QLineEdit()
        self.txt_prefix.setPlaceholderText("Prefix")
        self.txt_prefix.setFixedWidth(96)
        self.txt_prefix.setFixedHeight(CONTROL_HEIGHT)
        self.txt_prefix.setProperty("role", "fieldFlat")
        self.txt_prefix.textChanged.connect(self._on_rule_changed)
        rules_layout.addWidget(self.txt_prefix)

        self.txt_suffix = QLineEdit()
        self.txt_suffix.setPlaceholderText("Suffix")
        self.txt_suffix.setFixedWidth(96)
        self.txt_suffix.setFixedHeight(CONTROL_HEIGHT)
        self.txt_suffix.setProperty("role", "fieldFlat")
        self.txt_suffix.textChanged.connect(self._on_rule_changed)
        rules_layout.addWidget(self.txt_suffix)

        rules_layout.addStretch()
        body.addWidget(rules_card)

        # 4. Tabbed Workspace: Record Associations vs Live Photo Stream
        self.tabs = QTabWidget()

        # --- TAB 1: SPREADSHEET ASSOCIATIONS ---
        tab_records = QWidget()
        tab_rec_layout = QVBoxLayout(tab_records)
        tab_rec_layout.setContentsMargins(0, 8, 0, 0)
        tab_rec_layout.setSpacing(8)

        # Filter & Summary Metrics Bar - flipped like the data source bar:
        # the quick override actions and the match counters lead on the
        # left, and the search / record filter close the row on the right.
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self.btn_assign_selected = QPushButton("Assign Photo...")
        self.btn_assign_selected.setToolTip("Assign custom photo to currently selected record")
        self.btn_assign_selected.clicked.connect(self._assign_selected_row)
        filter_row.addWidget(self.btn_assign_selected)

        self.btn_clear_selected = QPushButton("Clear Override")
        self.btn_clear_selected.setToolTip("Clear custom photo override for selected record")
        self.btn_clear_selected.clicked.connect(self._clear_selected_row)
        filter_row.addWidget(self.btn_clear_selected)

        self.lbl_metrics = QLabel("0 matched")
        self.lbl_metrics.setVisible(False)
        filter_row.addWidget(self.lbl_metrics)

        self.stat_line = StatLine()
        filter_row.addWidget(self.stat_line)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search by identifier, name, or file...")
        self.txt_search.textChanged.connect(self._filter_table)
        filter_row.addWidget(self.txt_search, stretch=1)

        self.cmb_filter = QComboBox()
        self.cmb_filter.addItems([
            "All records",
            "Matched photos",
            "Missing photos",
            "Ambiguous matches",
            "Overridden photos",
        ])
        self.cmb_filter.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_filter.currentIndexChanged.connect(self._filter_table)
        filter_row.addWidget(self.cmb_filter)
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
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(1, 190)
        self.table.setColumnWidth(2, 72)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 260)
        self.table.setColumnWidth(5, 120)
        self.table.setColumnWidth(6, 100)
        self.table.setIconSize(self.table.iconSize() * 2)
        self.table.cellClicked.connect(self._on_action_clicked)
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
        stream_header = self.table_stream.horizontalHeader()
        stream_header.setSectionResizeMode(QHeaderView.Interactive)
        stream_header.setStretchLastSection(False)
        self.table_stream.setColumnWidth(0, 180)
        self.table_stream.setColumnWidth(1, 200)
        self.table_stream.setColumnWidth(2, 320)
        self.table_stream.setColumnWidth(3, 120)
        tab_stream_layout.addWidget(self.table_stream)
        self.tabs.addTab(tab_stream, "Live Photo Queue (0)")

        body.addWidget(self.tabs, stretch=1)

        # 5. Bottom Step Navigation Bar
        back_label, next_label, badge = workflow.footer_labels(WorkflowStep.PHOTOS)
        self.nav_bar = PageFooter(
            prev_label=back_label,
            next_label=next_label,
            step_badge=badge,
            parent=self,
        )
        self.nav_bar.back_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.DATA_SOURCE.value))
        self.nav_bar.next_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.TEMPLATES.value))
        layout.addWidget(self.nav_bar)

    def _retire_worker(self, worker: QThread) -> None:
        """Hold on to a worker until it has finished.

        A QThread that is destroyed while it is still running takes the
        application down with it, so the reference is kept until the thread
        reports that it is done.
        """
        self._retired_workers.append(worker)

        def _release() -> None:
            if worker in self._retired_workers:
                self._retired_workers.remove(worker)
            worker.deleteLater()

        worker.finished.connect(_release)

    def shutdown(self) -> None:
        """Stop the background workers before the page is destroyed.

        Dropping a QThread reference while the thread is still running
        destroys the thread object mid-execution and crashes the application.
        """
        self._stop_match_worker()
        self._stop_indexing()
        self._thread_pool.clear()
        self._thread_pool.waitForDone(2000)
        for worker in list(self._retired_workers):
            worker.wait(2000)
        self._retired_workers.clear()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.shutdown()
        super().closeEvent(event)

    def set_columns(self, columns: List[str]) -> None:
        """Offer every spreadsheet column as a lookup key.

        The photos can be found by the PIN, by an employee id or by any other
        column of the sheet, so all of them are offered here.
        """
        self.columns = list(columns)
        previous = self.cmb_key_col.currentData()

        self.cmb_key_col.blockSignals(True)
        self.cmb_key_col.clear()
        self.cmb_key_col.addItem("Auto-detect (PIN / ID)", "")
        for col in self.columns:
            self.cmb_key_col.addItem(col, col)

        # Keep the chosen column when the sheet is re-imported.
        if previous:
            index = self.cmb_key_col.findData(previous)
            if index >= 0:
                self.cmb_key_col.setCurrentIndex(index)
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
        """Stop the scanning thread and wait for it to finish.

        The worker reference must not be dropped while the thread is still
        running - the QThread would be destroyed while executing and crash
        the application.
        """
        worker = self._worker
        self._worker = None
        if worker is not None:
            if worker.isRunning():
                worker.cancel()
                if not worker.wait(3000):
                    # Still running: keep it alive until it terminates.
                    self._retire_worker(worker)
            else:
                worker.deleteLater()

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

        # Trim the rolling window once per batch instead of once per row,
        # which keeps the table from invalidating its layout for every
        # single discovered photo.
        overflow = self.table_stream.rowCount() - MAX_STREAM_ROWS
        for _ in range(overflow):
            self.table_stream.removeRow(0)

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
        self.lookup_column_changed.emit(key_col or "")
        self._rematch()

    def _browse_directory(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Photograph Directory")
        if folder:
            self.set_directory(Path(folder))

    def _rescan(self) -> None:
        if self.matcher.photo_dir:
            self.set_directory(self.matcher.photo_dir)

    def _rematch(self) -> None:
        """Re-run the matching on a worker thread.

        Matching and staging the photographs in the workspace is I/O heavy,
        so it runs off the interface thread.  Results of an outdated request
        are discarded.
        """
        if not self.records:
            return

        self._match_generation += 1
        generation = self._match_generation

        self._stop_match_worker()

        self.lbl_metrics.setText("Matching…")
        self._match_worker = PhotoMatchWorker(
            matcher=self.matcher,
            records=self.records,
            project_config=self.project_config,
            copy_to_workspace=self.project_config is not None,
            parent=self,
        )
        self._match_worker.matching_finished.connect(
            lambda results, summary, copied, gen=generation: self._on_match_finished(
                results, summary, copied, gen
            )
        )
        self._match_worker.matching_failed.connect(self._on_match_failed)
        self._match_worker.start()

    def _stop_match_worker(self) -> None:
        """Cancel and join the running match worker."""
        worker = self._match_worker
        self._match_worker = None
        if worker is not None:
            if worker.isRunning():
                worker.cancel()
                if not worker.wait(3000):
                    self._retire_worker(worker)
            else:
                worker.deleteLater()

    def _on_match_finished(
        self,
        results: Dict[str, PhotoMatchResult],
        summary: MatchSummary,
        copied_count: int,
        generation: int,
    ) -> None:
        """Worker finished - publish the results if they are still current."""
        if generation != self._match_generation:
            return

        # The worker is done - release it so it can be collected.
        worker = self._match_worker
        self._match_worker = None
        if worker is not None:
            worker.deleteLater()

        self.match_results = results
        self.match_summary = summary

        if copied_count > 0:
            self.lbl_workspace_photos.setText(
                f"✓ Copied {copied_count:,} matched photo(s) into workspace: photos/"
            )
            self.lbl_workspace_photos.setVisible(True)
        elif any(
            m.status in (MatchStatus.MATCHED, MatchStatus.OVERRIDDEN)
            for m in results.values()
        ):
            self.lbl_workspace_photos.setText(
                "✓ Matched photographs stored in workspace: photos/"
            )
            self.lbl_workspace_photos.setVisible(True)

        s = summary
        self.lbl_metrics.setText(
            f"{s.matched_count:,} matched • {s.missing_count:,} missing • "
            f"{s.ambiguous_count:,} ambiguous • {s.overridden_count:,} overridden"
        )
        self.stat_line.set_stats([
            ("Matched", s.matched_count, SEMANTIC_SUCCESS if s.matched_count else None),
            ("Missing", s.missing_count, SEMANTIC_WARNING if s.missing_count else None),
            ("Ambiguous", s.ambiguous_count, SEMANTIC_WARNING if s.ambiguous_count else None),
            ("Overridden", s.overridden_count, PRIMARY if s.overridden_count else None),
        ])
        self.tabs.setTabText(
            0, f"Record Associations ({s.matched_count:,}/{len(self.records):,} Matched)"
        )

        self._populate_table()
        self.matching_updated.emit(self.match_results, self.match_summary)

    def _on_match_failed(self, error_msg: str) -> None:
        """The matching worker failed."""
        self.lbl_metrics.setText("Matching failed")
        self.notice.set_message(f"Photo matching failed: {error_msg}", severity="error")

    def _populate_table(self) -> None:
        """Fill the association table.

        The rows are plain items - no per row widgets - so a table with tens
        of thousands of records stays light.  Thumbnails are decoded on a
        thread pool and inserted as soon as they are ready.
        """
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        total_records = len(self.records)
        self.table.setRowCount(total_records)

        for row_idx, rec in enumerate(self.records):
            match = self.match_results.get(rec.record_id)
            key_val = self.matcher.get_lookup_key_value(rec)

            # 0. Lookup Key
            self.table.setItem(row_idx, 0, QTableWidgetItem(key_val or rec.pin))

            # 1. Name or other column
            name = rec.get_value("Name", "")
            if not name:
                for k, v in rec.data.items():
                    if "name" in k.lower() and v:
                        name = str(v)
                        break
            self.table.setItem(row_idx, 1, QTableWidgetItem(name))

            # 2. Thumbnail - filled in by the thumbnail workers
            self.table.setItem(row_idx, 2, QTableWidgetItem())

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
            self.table.setItem(row_idx, 4, QTableWidgetItem(path_str))

            # 5. Override Status
            override_str = "Custom Override" if (match and match.is_overridden) else "Automatic"
            item_override = QTableWidgetItem(override_str)
            if match and match.is_overridden:
                item_override.setForeground(QColor("#A855FC"))
            self.table.setItem(row_idx, 5, item_override)

            # 6. Action - a clickable item instead of a widget per row
            action_item = QTableWidgetItem(
                "Clear" if (match and match.is_overridden) else "Assign..."
            )
            action_item.setForeground(
                QColor("#A855FC") if (match and match.is_overridden) else QColor("#38BDF8")
            )
            action_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 6, action_item)

        self.table.setUpdatesEnabled(True)
        self._filter_table()
        self._request_thumbnails()

    def _request_thumbnails(self) -> None:
        """Queue the visible thumbnails for decoding on the thread pool."""
        self._thumbnail_cache.clear()

        first = max(0, self.table.rowAt(0))
        last = min(self.table.rowCount() - 1, first + MAX_VISIBLE_THUMBS)

        for row in range(first, last + 1):
            match = self.match_results.get(self.records[row].record_id)
            if not match or not match.photo_path:
                continue
            path = match.photo_path
            cached = self._thumbnail_cache.get(path)
            if cached is not None:
                self._apply_thumbnail(row, path, cached)
                continue
            self._thread_pool.start(
                ThumbnailTask(row, path, self._thumbnail_signals)
            )

    def _on_thumbnail_ready(self, row: int, path: str, image) -> None:
        """A thumbnail finished decoding - insert it into the table."""
        if image is None:
            return
        if row >= len(self.records):
            return
        self._thumbnail_cache.put(path, image)
        self._apply_thumbnail(row, path, image)

    def _apply_thumbnail(self, row: int, path: str, image) -> None:
        """Show a decoded thumbnail in the table cell."""
        if row >= self.table.rowCount():
            return
        item = self.table.item(row, 2)
        if item is None:
            return
        try:
            pixmap = QPixmap.fromImage(image)
        except Exception:
            return
        item.setIcon(QIcon(pixmap))

    def _on_action_clicked(self, row: int, column: int) -> None:
        """Handle a click in the action column."""
        if column != 6 or not (0 <= row < len(self.records)):
            return
        rec = self.records[row]
        key_val = self.matcher.get_lookup_key_value(rec)
        match = self.match_results.get(rec.record_id)
        if match and match.is_overridden:
            self._clear_override(rec.record_id, key_val, rec.pin)
        else:
            self._manual_override(rec.record_id, key_val, rec.pin)

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
