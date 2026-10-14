"""Batch card generation workspace with pre-flight checklist and live progress."""

import logging
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import OutputFormat
from id_card_generator.core.models import (
    PhotoMatchResult,
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.generation.batch_generator import GenerationSummary
from id_card_generator.generation.generation_worker import GenerationWorker

logger = logging.getLogger(__name__)


class GenerationPage(QWidget):
    """Batch generation interface with pre-flight summary and thread-safe execution."""

    generation_completed = Signal(object)  # GenerationSummary
    goto_review_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.template: Optional[TemplateDefinition] = None
        self.records: List[SourceRecord] = []
        self.match_results: Dict[str, PhotoMatchResult] = {}
        self.column_mappings: Dict[str, str] = {}
        self.settings = RenderSettings()

        self._worker: Optional[GenerationWorker] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Header
        layout.addWidget(QLabel("<h2>Batch Card Generation</h2>"))

        # Pre-Flight Checklist Panel
        self.checklist_frame = QFrame()
        self.checklist_frame.setObjectName("card_panel")
        chk_layout = QVBoxLayout(self.checklist_frame)
        chk_layout.addWidget(QLabel("<b>Pre-Flight Verification Checklist:</b>"))

        self.grid_checklist = QGridLayout()
        self.grid_checklist.setSpacing(10)

        self.lbl_chk_records = QLabel("Records: 0 loaded (0 valid)")
        self.lbl_chk_photos = QLabel("Photos: 0 matched (0 missing)")
        self.lbl_chk_template = QLabel("Template: None selected")
        self.lbl_chk_output = QLabel("Output: PNG @ 300 DPI ({PIN_NUMBER}_{NAME}.png)")

        self.grid_checklist.addWidget(self.lbl_chk_records, 0, 0)
        self.grid_checklist.addWidget(self.lbl_chk_photos, 0, 1)
        self.grid_checklist.addWidget(self.lbl_chk_template, 1, 0)
        self.grid_checklist.addWidget(self.lbl_chk_output, 1, 1)

        chk_layout.addLayout(self.grid_checklist)
        layout.addWidget(self.checklist_frame)

        # Action Buttons Row
        action_row = QHBoxLayout()
        self.btn_generate = QPushButton("Generate All ID Cards")
        self.btn_generate.setObjectName("btn_primary")
        self.btn_generate.setStyleSheet("font-size: 15px; padding: 12px 24px;")
        self.btn_generate.clicked.connect(self._start_generation)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btn_danger")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_generation)

        self.btn_goto_review = QPushButton("Proceed to Sequential Review ▶")
        self.btn_goto_review.setObjectName("btn_success")
        self.btn_goto_review.setEnabled(False)
        self.btn_goto_review.clicked.connect(lambda: self.goto_review_requested.emit())

        action_row.addWidget(self.btn_generate)
        action_row.addWidget(self.btn_cancel)
        action_row.addStretch()
        action_row.addWidget(self.btn_goto_review)
        layout.addLayout(action_row)

        # Progress Section
        prog_frame = QFrame()
        prog_frame.setObjectName("card_panel")
        prog_layout = QVBoxLayout(prog_frame)

        self.lbl_status = QLabel("Ready to generate.")
        self.lbl_status.setStyleSheet("font-weight: 600; color: #94A3B8;")
        prog_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(24)
        prog_layout.addWidget(self.progress_bar)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFixedHeight(160)
        self.log_output.setStyleSheet("font-family: monospace; font-size: 11px;")
        prog_layout.addWidget(self.log_output)

        layout.addWidget(prog_frame)
        layout.addStretch()

    def set_generation_context(
        self,
        template: Optional[TemplateDefinition],
        records: List[SourceRecord],
        match_results: Dict[str, PhotoMatchResult],
        column_mappings: Dict[str, str],
        settings: Optional[RenderSettings] = None,
    ) -> None:
        """Update pre-flight checklist details."""
        self.template = template
        self.records = records
        self.match_results = match_results
        self.column_mappings = column_mappings
        if settings:
            self.settings = settings

        valid_count = sum(1 for r in records if r.is_valid)
        missing_photos = sum(1 for m in match_results.values() if m.status.value == "missing")
        matched_photos = len(records) - missing_photos

        self.lbl_chk_records.setText(f"Records: {len(records):,} loaded ({valid_count:,} valid)")
        self.lbl_chk_photos.setText(f"Photos: {matched_photos:,} matched ({missing_photos:,} missing)")

        if template:
            self.lbl_chk_template.setText(f"Template: {template.name} ({template.width_px}x{template.height_px} px)")
        else:
            self.lbl_chk_template.setText("Template: ⚠ None selected")

        self.lbl_chk_output.setText(
            f"Output: {self.settings.output_format.value} @ {self.settings.dpi} DPI (Staging Area)"
        )

        can_start = bool(self.template and self.records)
        self.btn_generate.setEnabled(can_start)

    def _start_generation(self) -> None:
        if not self.template or not self.records:
            QMessageBox.warning(self, "Incomplete Setup", "Please load a spreadsheet and select a template first.")
            return

        self.btn_generate.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_goto_review.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_output.clear()
        self.lbl_status.setText("Generation in progress...")

        self._worker = GenerationWorker(
            template=self.template,
            records=self.records,
            match_results=self.match_results,
            column_mappings=self.column_mappings,
            settings=self.settings,
        )
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.batch_finished.connect(self._on_finished)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()

    def _cancel_generation(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.lbl_status.setText("Cancelling generation...")
            self.btn_cancel.setEnabled(False)

    def _on_progress(self, completed: int, total: int, pin: str, msg: str) -> None:
        pct = int((completed / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(f"Processing record {completed} of {total}: PIN {pin} ({msg})")
        self.log_output.append(f"[{completed}/{total}] PIN {pin}: {msg}")

    def _on_finished(self, summary: GenerationSummary) -> None:
        self.btn_generate.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_goto_review.setEnabled(summary.completed_count > 0)

        status_text = "Generation Completed!" if not summary.cancelled else "Generation Cancelled."
        self.lbl_status.setText(
            f"{status_text} {summary.completed_count} generated, {summary.skipped_count} skipped, {summary.failed_count} failed."
        )
        self.log_output.append(
            f"\n--- {status_text} ---\n"
            f"Successfully generated: {summary.completed_count}\n"
            f"Skipped: {summary.skipped_count}\n"
            f"Failed: {summary.failed_count}\n"
        )

        self.generation_completed.emit(summary)

    def _on_error(self, err_msg: str) -> None:
        self.btn_generate.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.lbl_status.setText(f"Error: {err_msg}")
        QMessageBox.critical(self, "Generation Error", f"An error occurred: {err_msg}")
