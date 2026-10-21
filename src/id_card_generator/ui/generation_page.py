"""Batch card generation workspace.

The screen follows the Stitch "bulk generation batch engine" layout:

* a row of KPI telemetry tiles (cards generated, elapsed / remaining time,
  disk throughput, thread pool size and CPU utilisation),
* a left column with the run configuration (pre-flight checklist, target
  template, dataset, batch scope and raster output),
* a centre column with the multi-core progress ring, the throughput graph
  and the status of the running workers,
* a right column with the live event log and the error inspector.
"""

import logging
import os
import time
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
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
from id_card_generator.generation.batch_generator import BatchGenerator, GenerationSummary
from id_card_generator.generation.generation_worker import GenerationWorker
from id_card_generator.ui import workflow
from id_card_generator.ui.components.page_scaffold import InlineNotice, PageFooter, PageHeader
from id_card_generator.ui.components.progress_ring import ProgressRing
from id_card_generator.ui.components.speed_graph import SpeedGraph
from id_card_generator.ui.components.status_pill import StatusPill
from id_card_generator.ui.components.surface import StatTile, SurfaceCard
from id_card_generator.ui.studio_tokens import SIZES
from id_card_generator.ui.studio_tokens import (
    BORDER_SUBTLE,
    FONT_FAMILY_MONO,
    PRIMARY,
    PRIMARY_LIGHT,
    SEMANTIC_ERROR,
    SEMANTIC_SUCCESS,
    SEMANTIC_WARNING,
    SURFACE_LOWEST,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)

# Every control in a toolbar row uses the same height.
CONTROL_HEIGHT = SIZES.CONTROL_HEIGHT


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
        self._retired_workers: List[GenerationWorker] = []
        self._start_time: float = 0.0
        self._bytes_written: int = 0
        self._cpu_time: float = 0.0
        self._completed_count: int = 0
        self._last_sample_count: int = 0
        self._last_sample_time: float = 0.0
        self._active_workers: int = 0
        self._core_values: List[float] = []
        self._errors: List[str] = []
        self._log_history: List[str] = []

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_elapsed_time)

        self._setup_ui()

    # -----------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------
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

        # Engine state lives in the page header - no duplicated title block.
        self.pill_engine_state = StatusPill("ENGINE READY", color=SEMANTIC_SUCCESS)
        self.page_header.add_action(self.pill_engine_state)

        self.notice = InlineNotice()
        notice_row = QHBoxLayout()
        notice_row.setContentsMargins(16, 8, 16, 0)
        notice_row.addWidget(self.notice)
        layout.addLayout(notice_row)

        body = QVBoxLayout()
        body.setContentsMargins(16, 12, 16, 12)
        body.setSpacing(12)
        layout.addLayout(body, stretch=1)

        # ---------------------------------------------------------
        # 1. KPI Telemetry Grid
        # ---------------------------------------------------------
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)

        def create_kpi_card(title: str, value: str, color: str = TEXT_PRIMARY):
            """Metric tile built from the shared design system."""
            tile = StatTile(caption=title, value=value, accent=color)
            return tile, tile.lbl_value

        self.card_rendered, self.lbl_kpi_rendered = create_kpi_card(
            "Cards Generated", "0 / 0", PRIMARY_LIGHT
        )
        self.card_time, self.lbl_kpi_time = create_kpi_card(
            "Elapsed / Remaining", "00:00 / --:--", TEXT_PRIMARY
        )
        self.card_throughput, self.lbl_kpi_throughput = create_kpi_card(
            "Disk Throughput", "0.0 MB/s", SEMANTIC_SUCCESS
        )
        self.card_workers, self.lbl_kpi_workers = create_kpi_card(
            "Thread Pool", "1 Thread", SEMANTIC_WARNING
        )
        self.card_cpu, self.lbl_kpi_cpu = create_kpi_card(
            "CPU Load", "0 %", TEXT_SECONDARY
        )

        for tile in (
            self.card_rendered,
            self.card_time,
            self.card_throughput,
            self.card_workers,
            self.card_cpu,
        ):
            kpi_row.addWidget(tile)
        body.addLayout(kpi_row)

        # ---------------------------------------------------------
        # 2. The three column workstation
        # ---------------------------------------------------------
        splitter = QSplitter(Qt.Horizontal)

        splitter.addWidget(self._build_config_column())
        splitter.addWidget(self._build_engine_column())
        splitter.addWidget(self._build_log_column())

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([320, 520, 380])
        body.addWidget(splitter, stretch=1)

        # ---------------------------------------------------------
        # 3. Action Buttons Row
        # ---------------------------------------------------------
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.btn_generate = QPushButton("▶ Launch Batch Generation")
        self.btn_generate.setObjectName("btn_primary")
        self.btn_generate.setFixedHeight(CONTROL_HEIGHT)
        self.btn_generate.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px 16px;")
        self.btn_generate.clicked.connect(self._start_generation)

        self.btn_cancel = QPushButton("⏹ Cancel Run")
        self.btn_cancel.setObjectName("btn_danger")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setFixedHeight(CONTROL_HEIGHT)
        self.btn_cancel.setStyleSheet("font-size: 13px; padding: 4px 16px;")
        self.btn_cancel.clicked.connect(self._cancel_generation)

        self.btn_goto_review = QPushButton("Proceed to Sequential Review ▶")
        self.btn_goto_review.setObjectName("btn_success")
        self.btn_goto_review.setEnabled(False)
        self.btn_goto_review.setFixedHeight(CONTROL_HEIGHT)
        self.btn_goto_review.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px 16px;")
        self.btn_goto_review.clicked.connect(lambda: self.goto_review_requested.emit())

        action_row.addWidget(self.btn_generate)
        action_row.addWidget(self.btn_cancel)
        action_row.addStretch()
        action_row.addWidget(self.btn_goto_review)
        body.addLayout(action_row)

        # ---------------------------------------------------------
        # 4. Bottom Step Navigation Bar
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

    # -- left column --------------------------------------------------
    def _build_config_column(self) -> QWidget:
        """The run configuration: pre-flight, template, dataset, scope, output."""
        card = SurfaceCard("Run Configuration")
        card.setMinimumWidth(280)
        card.setMaximumWidth(420)

        # -- pre-flight checklist ---------------------------------
        self.checklist_frame = QFrame()
        self.checklist_frame.setObjectName("workspace_panel")
        chk_layout = QVBoxLayout(self.checklist_frame)
        chk_layout.setContentsMargins(10, 8, 10, 8)
        chk_layout.setSpacing(6)

        lbl_chk_title = QLabel("PRE-FLIGHT VERIFICATION")
        lbl_chk_title.setProperty("role", "sectionLabel")
        chk_layout.addWidget(lbl_chk_title)

        self.grid_checklist = QGridLayout()
        self.grid_checklist.setSpacing(8)

        self.lbl_chk_records = QLabel("0 loaded (0 valid)")
        self.lbl_chk_records.setProperty("role", "specValue")
        self.lbl_chk_photos = QLabel("0 matched (0 missing)")
        self.lbl_chk_photos.setProperty("role", "specValue")
        self.lbl_chk_template = QLabel("None selected")
        self.lbl_chk_template.setProperty("role", "specValue")
        self.lbl_chk_output = QLabel("PNG @ 300 DPI")
        self.lbl_chk_output.setProperty("role", "specValue")

        for label in (
            self.lbl_chk_records,
            self.lbl_chk_photos,
            self.lbl_chk_template,
            self.lbl_chk_output,
        ):
            label.setWordWrap(True)

        for row, (key, value) in enumerate((
            ("Records", self.lbl_chk_records),
            ("Photos", self.lbl_chk_photos),
            ("Template", self.lbl_chk_template),
            ("Output", self.lbl_chk_output),
        )):
            caption = QLabel(key)
            caption.setProperty("role", "specKey")
            self.grid_checklist.addWidget(caption, row, 0)
            self.grid_checklist.addWidget(value, row, 1)

        chk_layout.addLayout(self.grid_checklist)
        card.add(self.checklist_frame)

        # -- target template --------------------------------------
        card.add(self._spec_row("Template", "lbl_cfg_template", "None selected"))
        card.add(self._spec_row("Card", "lbl_cfg_card", "-"))

        # -- dataset ------------------------------------------------
        card.add(self._spec_row("Dataset", "lbl_cfg_dataset", "0 records"))
        card.add(self._spec_row("Photos", "lbl_cfg_photos", "0 matched"))

        # -- batch scope --------------------------------------------
        scope_title = QLabel("BATCH SCOPE")
        scope_title.setProperty("role", "sectionLabel")
        card.add(scope_title)

        self.scope_group = QButtonGroup(self)
        self.scope_group.setExclusive(True)

        scope_row = QHBoxLayout()
        scope_row.setSpacing(6)

        self.btn_scope_all = QPushButton("All records")
        self.btn_scope_all.setCheckable(True)
        self.btn_scope_all.setChecked(True)
        self.btn_scope_all.setObjectName("btn_stepper")
        self.btn_scope_all.setFixedHeight(CONTROL_HEIGHT)
        self.btn_scope_all.setToolTip("Render every record of the dataset")
        self.btn_scope_all.toggled.connect(self._on_scope_changed)
        self.scope_group.addButton(self.btn_scope_all)
        scope_row.addWidget(self.btn_scope_all)

        self.btn_scope_range = QPushButton("Custom range")
        self.btn_scope_range.setCheckable(True)
        self.btn_scope_range.setObjectName("btn_stepper")
        self.btn_scope_range.setFixedHeight(CONTROL_HEIGHT)
        self.btn_scope_range.setToolTip("Render only the records of the given range")
        self.btn_scope_range.toggled.connect(self._on_scope_changed)
        self.scope_group.addButton(self.btn_scope_range)
        scope_row.addWidget(self.btn_scope_range)

        card.add_layout(scope_row)

        range_row = QHBoxLayout()
        range_row.setSpacing(6)

        self.spin_range_start = QSpinBox()
        self.spin_range_start.setRange(1, 1_000_000)
        self.spin_range_start.setPrefix("From ")
        self.spin_range_start.setFixedHeight(CONTROL_HEIGHT)

        self.spin_range_end = QSpinBox()
        self.spin_range_end.setRange(1, 1_000_000)
        self.spin_range_end.setPrefix("To ")
        self.spin_range_end.setFixedHeight(CONTROL_HEIGHT)

        range_row.addWidget(self.spin_range_start)
        range_row.addWidget(self.spin_range_end)
        card.add_layout(range_row)

        self.lbl_range_hint = QLabel("")
        self.lbl_range_hint.setProperty("role", "specKey")
        self.lbl_range_hint.setWordWrap(True)
        card.add(self.lbl_range_hint)

        self.spin_range_start.valueChanged.connect(self._on_scope_changed)
        self.spin_range_end.valueChanged.connect(self._on_scope_changed)

        # -- raster output ------------------------------------------
        output_title = QLabel("RASTER OUTPUT")
        output_title.setProperty("role", "sectionLabel")
        card.add(output_title)

        format_row = QHBoxLayout()
        format_row.setSpacing(6)

        self.cmb_format = QComboBox()
        self.cmb_format.addItem("PNG 24-bit", OutputFormat.PNG.value)
        self.cmb_format.addItem("JPEG High", OutputFormat.JPEG.value)
        self.cmb_format.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_format.currentIndexChanged.connect(self._on_output_changed)

        self.cmb_dpi = QComboBox()
        for dpi in (150, 300, 600):
            self.cmb_dpi.addItem(f"{dpi} DPI", dpi)
        self.cmb_dpi.setCurrentIndex(1)  # 300 DPI is the studio default
        self.cmb_dpi.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_dpi.currentIndexChanged.connect(self._on_output_changed)

        format_row.addWidget(self.cmb_format)
        format_row.addWidget(self.cmb_dpi)
        card.add_layout(format_row)

        self.lbl_naming = QLabel("")
        self.lbl_naming.setProperty("role", "specValue")
        self.lbl_naming.setWordWrap(True)
        card.add(self._caption("File naming"))
        card.add(self.lbl_naming)

        # The column can get long, so it scrolls.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumWidth(280)
        scroll.setMaximumWidth(420)
        scroll.setWidget(card)
        return scroll

    def _build_engine_column(self) -> QWidget:
        """The progress ring, the throughput graph and the worker status."""
        card = SurfaceCard("Batch Engine")
        card.setMinimumWidth(360)

        engine_layout = QVBoxLayout()
        engine_layout.setContentsMargins(0, 0, 0, 0)
        engine_layout.setSpacing(10)

        ring_row = QHBoxLayout()
        ring_row.setSpacing(16)

        self.progress_ring = ProgressRing(diameter=168, cores=1)
        ring_row.addWidget(self.progress_ring)

        ring_text = QVBoxLayout()
        ring_text.setSpacing(6)

        self.lbl_status = QLabel("Ready to generate.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setProperty("role", "cardTitle")
        ring_text.addWidget(self.lbl_status)

        self.lbl_workers_status = QLabel("No worker is running.")
        self.lbl_workers_status.setWordWrap(True)
        self.lbl_workers_status.setProperty("role", "cardSubtitle")
        ring_text.addWidget(self.lbl_workers_status)

        self.lbl_batch_scope = QLabel("")
        self.lbl_batch_scope.setProperty("role", "specKey")
        self.lbl_batch_scope.setWordWrap(True)
        ring_text.addWidget(self.lbl_batch_scope)

        ring_text.addStretch()
        ring_row.addLayout(ring_text, stretch=1)
        engine_layout.addLayout(ring_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ background-color: {SURFACE_LOWEST}; border: 1px solid {BORDER_SUBTLE}; border-radius: 4px; text-align: center; color: #FFFFFF; font-family: {FONT_FAMILY_MONO}; font-size: 11px; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0052cc, stop:1 #6c8cff); border-radius: 3px; }}"
        )
        engine_layout.addWidget(self.progress_bar)

        graph_title = QLabel("THROUGHPUT")
        graph_title.setProperty("role", "sectionLabel")
        engine_layout.addWidget(graph_title)

        self.speed_graph = SpeedGraph(capacity=90, minimum_height=96)
        engine_layout.addWidget(self.speed_graph, stretch=1)

        card.add_layout(engine_layout)
        return card

    def _build_log_column(self) -> QWidget:
        """The live event log and the error inspector."""
        card = SurfaceCard("Event Log")
        card.setMinimumWidth(280)
        card.setMaximumWidth(460)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        filter_caption = QLabel("Show")
        filter_caption.setProperty("role", "specKey")
        filter_row.addWidget(filter_caption)

        self.cmb_log_filter = QComboBox()
        self.cmb_log_filter.addItem("All events", "all")
        self.cmb_log_filter.addItem("Errors only", "errors")
        self.cmb_log_filter.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_log_filter.currentIndexChanged.connect(self._refresh_log)
        filter_row.addWidget(self.cmb_log_filter)
        filter_row.addStretch()

        card.add_layout(filter_row)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QTextEdit.NoWrap)
        self.log_output.setStyleSheet(
            f"QTextEdit {{ background-color: {SURFACE_LOWEST}; color: #8ED0FF; font-family: {FONT_FAMILY_MONO}; font-size: 11px; border: 1px solid {BORDER_SUBTLE}; border-radius: 4px; padding: 6px; }}"
        )
        card.add(self.log_output, stretch=1)

        error_title = QLabel("ERROR INSPECTOR")
        error_title.setProperty("role", "sectionLabel")
        card.add(error_title)

        self.lbl_error_count = QLabel("0 failures")
        self.lbl_error_count.setProperty("role", "specKey")
        card.add(self.lbl_error_count)

        self.error_list = QListWidget()
        self.error_list.setStyleSheet(
            f"QListWidget {{ background-color: {SURFACE_LOWEST}; border: 1px solid {BORDER_SUBTLE}; border-radius: 4px; font-family: {FONT_FAMILY_MONO}; font-size: 10px; }}"
        )
        card.add(self.error_list)

        return card

    # -- small helpers ------------------------------------------------
    def _spec_row(self, key: str, value_attr: str, value: str) -> QWidget:
        """Build a small caption / value row."""
        holder = QWidget()
        holder.setProperty("role", "flat")
        row = QVBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)

        caption = QLabel(key)
        caption.setProperty("role", "specKey")
        row.addWidget(caption)

        label = QLabel(value)
        label.setProperty("role", "specValue")
        label.setWordWrap(True)
        row.addWidget(label)

        setattr(self, value_attr, label)
        return holder

    def _caption(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "specKey")
        return label

    # -----------------------------------------------------------------
    # Context
    # -----------------------------------------------------------------
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
        self.lbl_chk_records.setText(f"{len(records):,} loaded ({valid_count:,} valid)")
        self.lbl_kpi_rendered.setText(f"0 / {len(records):,}")

        matched_count = sum(
            1
            for m in match_results.values()
            if m.status in (MatchStatus.MATCHED, MatchStatus.OVERRIDDEN)
        )
        missing_count = len(records) - matched_count
        self.lbl_chk_photos.setText(f"{matched_count:,} matched ({missing_count:,} missing)")

        tmpl_name = template.name if template else "None selected"
        self.lbl_chk_template.setText(tmpl_name)

        current_format = settings.output_format
        fmt = (
            current_format.value
            if hasattr(current_format, "value")
            else str(current_format)
        ).upper()
        pat = getattr(settings, "filename_pattern", "{PIN_NUMBER}_{NAME}")
        self.lbl_chk_output.setText(f"{fmt} @ {settings.dpi} DPI · {pat}")

        # The configuration column mirrors the same facts.
        self.lbl_cfg_template.setText(tmpl_name)
        self.lbl_cfg_card.setText(self._card_summary(template))
        self.lbl_cfg_dataset.setText(
            f"{len(records):,} records · {valid_count:,} valid"
        )
        self.lbl_cfg_photos.setText(
            f"{matched_count:,} matched · {missing_count:,} missing"
        )

        self._sync_output_widgets()
        self._on_scope_changed()

    def _card_summary(self, template: Optional[TemplateDefinition]) -> str:
        """Describe the card size of the active template."""
        if not template:
            return "-"
        dpi = getattr(template, "dpi", None) or 300
        width = getattr(template, "width_physical", None)
        height = getattr(template, "height_physical", None)
        if not width or not height:
            width = (getattr(template, "width_px", 0) or 0) / dpi * 25.4
            height = (getattr(template, "height_px", 0) or 0) / dpi * 25.4
        return f"{width:.2f} × {height:.2f} mm @ {dpi} DPI"

    def _sync_output_widgets(self) -> None:
        """Push the render settings into the output widgets."""
        current = self.settings.output_format
        value = current.value if hasattr(current, "value") else str(current)
        index = self.cmb_format.findData(value)
        if index < 0:
            index = self.cmb_format.findData(OutputFormat.PNG.value)
        self.cmb_format.setCurrentIndex(index)

        index = self.cmb_dpi.findData(self.settings.dpi)
        if index < 0:
            index = self.cmb_dpi.findData(300)
        self.cmb_dpi.setCurrentIndex(index)

        self._update_naming_preview()

    def _update_naming_preview(self) -> None:
        """Show the file name that the batch engine will write."""
        extension = "jpg" if self.cmb_format.currentData() == OutputFormat.JPEG.value else "png"
        self.lbl_naming.setText(f"{{PIN}}_{{Name}}.{extension}")

    def _on_output_changed(self) -> None:
        """Apply the chosen raster format and resolution."""
        fmt = self.cmb_format.currentData()
        dpi = self.cmb_dpi.currentData()
        if fmt is not None:
            self.settings.output_format = OutputFormat(fmt)
        if dpi is not None:
            self.settings.dpi = int(dpi)
        self._update_naming_preview()
        if self.template is not None:
            fmt_name = self.settings.output_format.value.upper()
            self.lbl_chk_output.setText(
                f"{fmt_name} @ {self.settings.dpi} DPI · {{PIN}}_{{Name}}"
            )

    def _on_scope_changed(self) -> None:
        """Keep the batch scope widgets consistent."""
        total = len(self.records)
        custom = self.btn_scope_range.isChecked()
        self.spin_range_start.setEnabled(custom)
        self.spin_range_end.setEnabled(custom)

        if not custom:
            self.spin_range_start.setMaximum(max(1, total))
            self.spin_range_end.setMaximum(max(1, total))
            if total:
                self.spin_range_start.setValue(1)
                self.spin_range_end.setValue(total)
            self.lbl_range_hint.setText(f"All {total:,} records are rendered.")
            self.lbl_batch_scope.setText(f"Scope: all {total:,} records")
            return

        start = self.spin_range_start.value()
        end = self.spin_range_end.value()
        if end < start:
            end = start
            self.spin_range_end.setValue(end)

        count = max(0, end - start + 1)
        self.lbl_range_hint.setText(
            f"Records {start:,} - {end:,} ({count:,} cards) of {total:,}."
        )
        self.lbl_batch_scope.setText(
            f"Scope: records {start:,} - {end:,} ({count:,} cards)"
        )

    def _selected_records(self) -> List[SourceRecord]:
        """Return the records that the batch scope selects."""
        if not self.btn_scope_range.isChecked():
            return list(self.records)
        start = max(1, self.spin_range_start.value())
        end = self.spin_range_end.value()
        if end < start:
            end = start
        # The range is 1-based and inclusive on both ends.
        return list(self.records[start - 1 : end])

    # -----------------------------------------------------------------
    # Running the batch
    # -----------------------------------------------------------------
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

        records = self._selected_records()
        if not records:
            self.notice.set_message(
                "The selected batch range is empty.", severity="warning"
            )
            return

        self.btn_generate.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_goto_review.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_output.clear()
        self.error_list.clear()
        self._errors.clear()
        self._bytes_written = 0
        self._completed_count = 0
        self._last_sample_count = 0
        self._last_sample_time = 0.0
        self._log_history.clear()
        self.speed_graph.clear_samples()
        self.progress_ring.set_progress(0.0)
        self.progress_ring.set_detail("")
        self.lbl_status.setText("Initializing worker threads...")
        self.pill_engine_state.set_status("RUNNING", color=PRIMARY)

        self._start_time = time.time()
        self._cpu_time = time.process_time()
        self._timer.start()

        workers = BatchGenerator.resolve_workers(len(records))
        self._active_workers = workers
        self.lbl_kpi_workers.setText(
            f"{workers} Thread{'s' if workers != 1 else ''}"
        )
        self.progress_ring.set_cores(workers)
        self.lbl_kpi_rendered.setText(f"0 / {len(records):,}")
        self.lbl_workers_status.setText(
            f"{workers} worker{'s' if workers != 1 else ''} are rendering into the staging area."
        )

        self._stop_worker()
        self._worker = GenerationWorker(
            template=self.template,
            records=records,
            match_results=self.match_results,
            column_mappings=self.column_mappings,
            settings=self.settings,
            workers=workers,
        )
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.status_message.connect(self._on_status)
        self._worker.record_finished.connect(self._on_card_generated)
        self._worker.batch_finished.connect(self._on_finished)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()

    def _update_elapsed_time(self) -> None:
        """Refresh the telemetry tiles once per second."""
        if self._start_time <= 0:
            return

        elapsed = max(0.0, time.time() - self._start_time)
        mins = int(elapsed) // 60
        secs = int(elapsed) % 60

        # The remaining time is derived from the current rate.
        done = self._completed_count
        total = self._batch_total()
        remaining = 0.0
        if done and total > done and elapsed > 0:
            rate = done / elapsed
            if rate > 0:
                remaining = (total - done) / rate

        self.lbl_kpi_time.setText(
            f"{mins:02d}:{secs:02d} / {self._format_duration(remaining)}"
        )

        # Disk throughput.
        throughput = self._bytes_written / elapsed if elapsed > 0 else 0.0
        self.lbl_kpi_throughput.setText(f"{throughput / (1024 * 1024):.1f} MB/s")

        # CPU load of this process, spread over the available cores.
        cpu_now = time.process_time()
        cpu_delta = cpu_now - self._cpu_time
        self._cpu_time = cpu_now
        cores = max(1, os.cpu_count() or 1)
        load = min(100.0, (cpu_delta / max(elapsed, 0.001)) / cores * 100.0)
        self.lbl_kpi_cpu.setText(f"{load:.0f} %")

        # A throughput sample for the graph.
        now = time.time()
        if self._last_sample_time > 0:
            delta = now - self._last_sample_time
            if delta > 0:
                self.speed_graph.push_sample(
                    (done - self._last_sample_count) / delta
                )
        self._last_sample_time = now
        self._last_sample_count = done

        # The per core segments of the ring share the overall progress.
        if self._active_workers > 1:
            share = self.progress_ring.value / self._active_workers
            self.progress_ring.set_core_values([share] * self._active_workers)

    def _batch_total(self) -> int:
        """The number of cards the current run has to produce."""
        if self._worker is not None:
            return len(self._worker.records)
        return len(self._selected_records())

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format a duration as ``MM:SS``."""
        seconds = int(max(0.0, seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _stop_worker(self) -> None:
        """Join the running worker before it is replaced.

        A QThread that is destroyed while it is still running crashes the
        application, so the reference is kept until the thread has finished.
        """
        worker = self._worker
        self._worker = None
        if worker is None:
            return
        if worker.isRunning():
            worker.cancel()
            if not worker.wait(3000):
                # Still running - hold on to it until it reports that it is done.
                self._retired_workers.append(worker)

                def _release() -> None:
                    if worker in self._retired_workers:
                        self._retired_workers.remove(worker)
                    worker.deleteLater()

                worker.finished.connect(_release)
        else:
            worker.deleteLater()

    def shutdown(self) -> None:
        """Stop the generation before the page is destroyed."""
        self._timer.stop()
        self._stop_worker()
        for worker in list(self._retired_workers):
            worker.wait(2000)
        self._retired_workers.clear()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.shutdown()
        super().closeEvent(event)

    def _cancel_generation(self) -> None:
        """Request a cancellation - the worker confirms when it stopped."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.lbl_status.setText("Cancelling run...")
            self.pill_engine_state.set_status("CANCELLING", color=SEMANTIC_WARNING)
            self.btn_cancel.setEnabled(False)

    # -- worker events -------------------------------------------------
    def _on_progress(self, current: int, total: int, pin: str = "", message: str = "") -> None:
        if total > 0:
            self._completed_count = current
            pct = int((current / total) * 100)
            self.progress_bar.setValue(pct)
            self.lbl_status.setText(
                f"Generating: {current} of {total} cards completed ({pct}%)"
            )
            self.lbl_kpi_rendered.setText(f"{current:,} / {total:,}")
            self.progress_ring.set_progress(current / total)
            self.progress_ring.set_detail(f"{current:,} / {total:,}")
            self.progress_ring.set_caption("RENDERING")

    def _on_status(self, msg: str) -> None:
        text = str(msg)
        self._log_history.append(text)

        is_error = text.startswith("[ERROR]") or text.startswith("[FATAL]")
        if is_error:
            self._errors.append(text)
            self.lbl_error_count.setText(f"{len(self._errors)} failure(s)")
            self.error_list.addItem(text)

        if self.cmb_log_filter.currentData() == "errors" and not is_error:
            return

        self.log_output.append(text)
        # Auto-scroll log to bottom
        sb = self.log_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _refresh_log(self) -> None:
        """Re-render the log for the selected filter."""
        self.log_output.clear()
        only_errors = self.cmb_log_filter.currentData() == "errors"
        for line in self._log_history:
            if only_errors and not (
                line.startswith("[ERROR]") or line.startswith("[FATAL]")
            ):
                continue
            self.log_output.append(line)
        sb = self.log_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_card_generated(self, result) -> None:
        """A single card was rendered - the log line is emitted by the worker."""
        if result is None:
            return
        if result.success and result.image_path:
            try:
                self._bytes_written += os.path.getsize(result.image_path)
            except OSError:
                pass

    def _on_error(self, message: str) -> None:
        """The batch run failed."""
        self._timer.stop()
        self.btn_generate.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.lbl_status.setText("Generation failed.")
        self.pill_engine_state.set_status("ERROR", color=SEMANTIC_ERROR)
        self.notice.set_message(f"Generation failed: {message}", severity="error")
        self._on_status(f"[FATAL] {message}")

    def _on_finished(self, summary: GenerationSummary) -> None:
        """The batch run finished (successfully or cancelled)."""
        self._timer.stop()
        self.btn_generate.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_goto_review.setEnabled(True)
        self.nav_bar.btn_next.setEnabled(True)

        # Release the worker - it must not be destroyed while it runs.
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()

        elapsed = time.time() - self._start_time if self._start_time else 0.0
        status_text = (
            f"Finished in {elapsed:.1f}s: "
            f"{summary.completed_count} generated, {summary.failed_count} errors, "
            f"{summary.skipped_count} skipped."
        )

        if summary.cancelled:
            status_text = (
                f"Cancelled after {summary.completed_count} of "
                f"{summary.total_records} cards ({elapsed:.1f}s)."
            )
            self.pill_engine_state.set_status("CANCELLED", color=SEMANTIC_WARNING)
            self.notice.set_message(status_text, severity="warning")
        else:
            self.pill_engine_state.set_status("COMPLETED", color=SEMANTIC_SUCCESS)
            if summary.failed_count:
                self.notice.set_message(
                    f"{summary.failed_count} card(s) could not be generated.",
                    severity="warning",
                )

        self.lbl_status.setText(status_text)
        self.progress_ring.set_progress(1.0)
        self.progress_ring.set_caption("COMPLETED")
        self.lbl_workers_status.setText("All workers finished.")
        self._on_status("\n" + "=" * 50)
        self._on_status(status_text)

        self.generation_completed.emit(summary)
