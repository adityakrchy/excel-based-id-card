"""Batch card generation workspace with pre-flight checklist and live telemetry.

Revamped per Stitch screen f3c87d2721a2:
- High-density KPI cards for Cards Rendered, Elapsed Time, Rate, and Engine Status.
- Pre-flight verification checklist.
- Glowing progress bar and real-time telemetry console with colored log streams.
"""

import logging
import time
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, QTimer, Signal
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

from id_card_generator.core.constants import MatchStatus, OutputFormat, WorkflowStep
from id_card_generator.core.models import (
    PhotoMatchResult,
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.generation.batch_generator import GenerationSummary
from id_card_generator.generation.generation_worker import GenerationWorker
from id_card_generator.ui.components.status_pill import StatusPill
from id_card_generator.ui import workflow
from id_card_generator.ui.components.page_scaffold import InlineNotice, PageFooter, PageHeader
from id_card_generator.ui.components.surface import StatTile
from id_card_generator.ui.studio_tokens import (
    BORDER_DEFAULT,
    BORDER_SUBTLE,
    FONT_FAMILY_MONO,
    FONT_FAMILY_UI,
    PRIMARY,
    PRIMARY_LIGHT,
    SEMANTIC_ERROR,
    SEMANTIC_SUCCESS,
    SEMANTIC_WARNING,
    SURFACE,
    SURFACE_HIGH,
    SURFACE_LOW,
    SURFACE_LOWEST,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


class GenerationPage(QWidget):
    """Batch generation interface with pre-flight summary and thread-safe execution."""

    generation_completed = Signal(object)  # GenerationSummary
    goto_review_requested = Signal()
    navigate_requested = Signal(str)  # WorkflowStep value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.template: Optional[TemplateDefinition] = None
        self.records: List[SourceRecord] = []
        self.match_results: Dict[str, PhotoMatchResult] = {}
        self.column_mappings: Dict[str, str] = {}
        self.settings = RenderSettings()

        self._worker: Optional[GenerationWorker] = None
        self._start_time: float = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_elapsed_time)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---------------------------------------------------------
        # Page header (step badge, title, subtitle)
        # ---------------------------------------------------------
        badge, title, subtitle = workflow.page_header_text(WorkflowStep.GENERATE)
        self.page_header = PageHeader(title, subtitle, badge)
        layout.addWidget(self.page_header)

        self.notice = InlineNotice()
        notice_row = QHBoxLayout()
        notice_row.setContentsMargins(16, 8, 16, 0)
        notice_row.addWidget(self.notice)
        layout.addLayout(notice_row)

        body = QVBoxLayout()
        body.setContentsMargins(16, 12, 16, 12)
        body.setSpacing(12)
        layout.addLayout(body, stretch=1)

        # Engine state lives in the page header - no duplicated title block.
        self.pill_engine_state = StatusPill("ENGINE READY", color=SEMANTIC_SUCCESS)
        self.page_header.add_action(self.pill_engine_state)

        # ---------------------------------------------------------
        # 1. KPI Telemetry Grid (Cards Rendered, Time, Rate, Workers)
        # ---------------------------------------------------------
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)

        def create_kpi_card(title: str, value: str, color: str = TEXT_PRIMARY):
            """Metric tile built from the shared design system."""
            tile = StatTile(caption=title.upper(), value=value, accent=color)
            return tile, tile.lbl_value

        self.card_rendered, self.lbl_kpi_rendered = create_kpi_card("Cards Rendered", "0 / 0", PRIMARY_LIGHT)
        self.card_time, self.lbl_kpi_time = create_kpi_card("Elapsed Time", "00:00", TEXT_PRIMARY)
        self.card_rate, self.lbl_kpi_rate = create_kpi_card("Render Speed", "0.0 /sec", SEMANTIC_SUCCESS)
        self.card_workers, self.lbl_kpi_workers = create_kpi_card("Worker Threads", "4 Threads", SEMANTIC_WARNING)

        kpi_row.addWidget(self.card_rendered)
        kpi_row.addWidget(self.card_time)
        kpi_row.addWidget(self.card_rate)
        kpi_row.addWidget(self.card_workers)
        body.addLayout(kpi_row)

        # ---------------------------------------------------------
        # 2. Pre-Flight Checklist Panel
        # ---------------------------------------------------------
        self.checklist_frame = QFrame()
        self.checklist_frame.setObjectName("card_panel")
        self.checklist_frame.setObjectName("workspace_panel")
        chk_layout = QVBoxLayout(self.checklist_frame)
        chk_layout.setContentsMargins(10, 8, 10, 8)
        chk_layout.setSpacing(6)

        lbl_chk_title = QLabel("<b>PRE-FLIGHT VERIFICATION CHECKLIST</b>")
        lbl_chk_title.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 0.5px;")
        chk_layout.addWidget(lbl_chk_title)

        self.grid_checklist = QGridLayout()
        self.grid_checklist.setSpacing(8)

        self.lbl_chk_records = QLabel("Records: 0 loaded (0 valid)")
        self.lbl_chk_records.setStyleSheet(f"color: {TEXT_SECONDARY}; font-family: {FONT_FAMILY_MONO}; font-size: 11px;")
        self.lbl_chk_photos = QLabel("Photos: 0 matched (0 missing)")
        self.lbl_chk_photos.setStyleSheet(f"color: {TEXT_SECONDARY}; font-family: {FONT_FAMILY_MONO}; font-size: 11px;")
        self.lbl_chk_template = QLabel("Template: None selected")
        self.lbl_chk_template.setStyleSheet(f"color: {TEXT_SECONDARY}; font-family: {FONT_FAMILY_MONO}; font-size: 11px;")
        self.lbl_chk_output = QLabel("Output: PNG @ 300 DPI ({PIN_NUMBER}_{NAME}.png)")
        self.lbl_chk_output.setStyleSheet(f"color: {TEXT_SECONDARY}; font-family: {FONT_FAMILY_MONO}; font-size: 11px;")

        self.grid_checklist.addWidget(self.lbl_chk_records, 0, 0)
        self.grid_checklist.addWidget(self.lbl_chk_photos, 0, 1)
        self.grid_checklist.addWidget(self.lbl_chk_template, 1, 0)
        self.grid_checklist.addWidget(self.lbl_chk_output, 1, 1)

        chk_layout.addLayout(self.grid_checklist)
        body.addWidget(self.checklist_frame)

        # ---------------------------------------------------------
        # 3. Action Buttons Row
        # ---------------------------------------------------------
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.btn_generate = QPushButton("▶ Launch Batch Generation")
        self.btn_generate.setObjectName("btn_primary")
        self.btn_generate.setStyleSheet(f"font-size: 13px; font-weight: bold; padding: 8px 20px;")
        self.btn_generate.clicked.connect(self._start_generation)

        self.btn_cancel = QPushButton("⏹ Cancel Run")
        self.btn_cancel.setObjectName("btn_danger")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setStyleSheet(f"font-size: 13px; padding: 8px 16px;")
        self.btn_cancel.clicked.connect(self._cancel_generation)

        self.btn_goto_review = QPushButton("Proceed to Sequential Review ▶")
        self.btn_goto_review.setObjectName("btn_success")
        self.btn_goto_review.setEnabled(False)
        self.btn_goto_review.setStyleSheet(f"font-size: 13px; font-weight: bold; padding: 8px 20px;")
        self.btn_goto_review.clicked.connect(lambda: self.goto_review_requested.emit())

        action_row.addWidget(self.btn_generate)
        action_row.addWidget(self.btn_cancel)
        action_row.addStretch()
        action_row.addWidget(self.btn_goto_review)
        body.addLayout(action_row)

        # ---------------------------------------------------------
        # 4. Progress & Telemetry Terminal Console
        # ---------------------------------------------------------
        prog_frame = QFrame()
        prog_frame.setObjectName("card_panel")
        prog_frame.setObjectName("workspace_panel")
        prog_layout = QVBoxLayout(prog_frame)
        prog_layout.setContentsMargins(10, 10, 10, 10)
        prog_layout.setSpacing(8)

        # Status and Progress Bar
        self.lbl_status = QLabel("Ready to generate.")
        self.lbl_status.setStyleSheet(f"font-weight: 600; color: {TEXT_PRIMARY}; font-size: 12px;")
        prog_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ background-color: {SURFACE_LOWEST}; border: 1px solid {BORDER_SUBTLE}; border-radius: 4px; text-align: center; color: #FFFFFF; font-family: {FONT_FAMILY_MONO}; font-size: 11px; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0052cc, stop:1 #6c8cff); border-radius: 3px; }}"
        )
        prog_layout.addWidget(self.progress_bar)

        # Telemetry Log
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet(
            f"QTextEdit {{ background-color: {SURFACE_LOWEST}; color: #8ED0FF; font-family: {FONT_FAMILY_MONO}; font-size: 11px; border: 1px solid {BORDER_SUBTLE}; border-radius: 4px; padding: 6px; }}"
        )
        prog_layout.addWidget(self.log_output)

        body.addWidget(prog_frame, stretch=1)

        # ---------------------------------------------------------
        # 5. Bottom Step Navigation Bar (Preserved for compatibility)
        # ---------------------------------------------------------
        back_label, next_label, badge = workflow.footer_labels(WorkflowStep.GENERATE)
        self.nav_bar = PageFooter(
            prev_label=back_label,
            next_label=next_label,
            step_badge=badge,
            parent=self,
        )
        self.nav_bar.back_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.CANVAS_EDITOR.value))
        self.nav_bar.next_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.REVIEW.value))
        layout.addWidget(self.nav_bar)

    def set_generation_context(
        self,
        template: Optional[TemplateDefinition],
        records: List[SourceRecord],
        match_results: Dict[str, PhotoMatchResult],
        column_mappings: Dict[str, str],
        settings: RenderSettings,
    ) -> None:
        """Update active project context and pre-flight checklist verification."""
        self.template = template
        self.records = records
        self.match_results = match_results
        self.column_mappings = column_mappings
        self.settings = settings

        # Update checklist labels
        valid_count = sum(1 for r in records if r.is_valid)
        self.lbl_chk_records.setText(f"Records: {len(records):,} loaded ({valid_count:,} valid)")
        self.lbl_kpi_rendered.setText(f"0 / {len(records):,}")

        matched_count = sum(
            1
            for m in match_results.values()
            if m.status in (MatchStatus.MATCHED, MatchStatus.OVERRIDDEN)
        )
        missing_count = len(records) - matched_count
        self.lbl_chk_photos.setText(f"Photos: {matched_count:,} matched ({missing_count:,} missing)")

        tmpl_name = template.name if template else "None selected"
        self.lbl_chk_template.setText(f"Template: {tmpl_name}")

        fmt = settings.output_format.value.upper()
        pat = getattr(settings, "filename_pattern", "{PIN_NUMBER}_{NAME}")
        self.lbl_chk_output.setText(f"Output: {fmt} @ {settings.dpi} DPI ({pat})")

    def _start_generation(self) -> None:
        if not self.template:
            self.notice.set_message(
                "Select or create an ID card template first.", severity="warning"
            )
            return

        if not self.records:
            self.notice.set_message(
                "Import an Excel spreadsheet with records first.", severity="warning"
            )
            return

        self.btn_generate.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_goto_review.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_output.clear()
        self.lbl_status.setText("Initializing worker threads...")
        self.pill_engine_state.set_status("RUNNING", color=PRIMARY)

        self._start_time = time.time()
        self._timer.start()

        self._worker = GenerationWorker(
            template=self.template,
            records=self.records,
            match_results=self.match_results,
            column_mappings=self.column_mappings,
            settings=self.settings,
        )
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.status_message.connect(self._on_status)
        self._worker.card_generated.connect(self._on_card_generated)
        self._worker.generation_finished.connect(self._on_finished)
        self._worker.start()

    def _update_elapsed_time(self) -> None:
        if self._start_time > 0:
            elapsed = int(time.time() - self._start_time)
            mins = elapsed // 60
            secs = elapsed % 60
            self.lbl_kpi_time.setText(f"{mins:02d}:{secs:02d}")

    def _cancel_generation(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.lbl_status.setText("Cancelling run...")
            self.pill_engine_state.set_status("CANCELLED", color=SEMANTIC_WARNING)
            self._timer.stop()

    def _on_progress(self, current: int, total: int) -> None:
        if total > 0:
            pct = int((current / total) * 100)
            self.progress_bar.setValue(pct)
            self.lbl_status.setText(f"Generating: {current} of {total} cards completed ({pct}%)")
            self.lbl_kpi_rendered.setText(f"{current:,} / {total:,}")

            elapsed = max(0.1, time.time() - self._start_time)
            rate = current / elapsed
            self.lbl_kpi_rate.setText(f"{rate:.1f} /sec")

    def _on_status(self, msg: str) -> None:
        self.log_output.append(msg)
        # Auto-scroll log to bottom
        sb = self.log_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_card_generated(self, result) -> None:
        if result.success:
            self._on_status(f"[OK] Rendered PIN: {result.pin} -> {result.output_path}")
        else:
            self._on_status(f"[ERROR] Failed PIN: {result.pin} - {result.error_message}")

    def _on_finished(self, summary: GenerationSummary) -> None:
        self._timer.stop()
        self.btn_generate.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_goto_review.setEnabled(True)
        self.nav_bar.btn_next.setEnabled(True)

        status_text = (
            f"Finished in {summary.elapsed_seconds:.1f}s: "
            f"{summary.completed_count} generated, {summary.error_count} errors, {summary.skipped_count} skipped."
        )
        self.lbl_status.setText(status_text)
        self.pill_engine_state.set_status("COMPLETED", color=SEMANTIC_SUCCESS)
        self._on_status("\n" + "=" * 50)
        self._on_status(status_text)

        self.generation_completed.emit(summary)
