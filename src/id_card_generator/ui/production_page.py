"""The production workspace: render the batch and review every card.

Generating and reviewing were two halves of the same job, so they now live on
one page:

* the left column configures the run, starts it and reports what the process
  is doing (progress, CPU load, memory),
* the centre column shows the card that is being reviewed, with the fields of
  the record underneath it,
* the right column is the queue of the produced cards and the decisions that
  are made on them.
"""

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import MatchStatus, ReviewStatus, WorkflowStep
from id_card_generator.core.models import (
    PhotoMatchResult,
    RenderResult,
    RenderSettings,
    ReviewRecord,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.core.process_metrics import ProcessMetrics
from id_card_generator.generation.batch_generator import BatchGenerator, GenerationSummary
from id_card_generator.generation.generation_worker import GenerationWorker
from id_card_generator.rendering.pillow_renderer import PillowRenderer
from id_card_generator.resources.resource_loader import get_staging_dir
from id_card_generator.review.review_manager import ReviewManager
from id_card_generator.ui import workflow
from id_card_generator.ui.components.busy_button import BusyButton
from id_card_generator.ui.components.layout_blocks import StatLine
from id_card_generator.ui.components.page_scaffold import (
    InlineNotice,
    PageFooter,
    PageHeader,
)
from id_card_generator.ui.components.record_list import (
    SEVERITY_ERROR,
    SEVERITY_OK,
    SEVERITY_WARN,
    RecordListEntry,
    RecordListModel,
    RecordListView,
)
from id_card_generator.ui.components.status_pill import StatusPill
from id_card_generator.ui.components.surface import SurfaceCard
from id_card_generator.ui.components.template_gallery import pil_to_qimage
from id_card_generator.ui.studio_tokens import SIZES
from id_card_generator.ui.studio_tokens import (
    BORDER_SUBTLE,
    FONT_FAMILY_MONO,
    PRIMARY,
    SEMANTIC_ERROR,
    SEMANTIC_SUCCESS,
    SEMANTIC_WARNING,
    SURFACE_HIGH,
    SURFACE_LOWEST,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)

# Every control in a toolbar row uses the same height.
CONTROL_HEIGHT = SIZES.CONTROL_HEIGHT

# The four data quality filters of the queue.
QUALITY_ALL = "all"
QUALITY_VALID = "valid"
QUALITY_WARN = "warn"
QUALITY_ERROR = "error"

# How many fields of a record the editor shows at once.
MAX_EDITED_FIELDS = 24


class ProductionPage(QWidget):
    """Renders the batch and reviews the produced cards."""

    generation_completed = Signal(object)  # GenerationSummary
    review_updated = Signal(object)  # ReviewManager
    goto_export_requested = Signal()
    navigate_requested = Signal(str)  # WorkflowStep value

    def __init__(self, parent=None):
        super().__init__(parent)

        # -- the project ------------------------------------------
        self.template: Optional[TemplateDefinition] = None
        self.records: List[SourceRecord] = []
        self.match_results: Dict[str, PhotoMatchResult] = {}
        self.column_mappings: Dict[str, str] = {}
        self.settings = RenderSettings()

        # -- the review session -----------------------------------
        self.manager = ReviewManager()
        self.source_records_map: Dict[str, SourceRecord] = {}
        self.match_results_map: Dict[str, PhotoMatchResult] = {}
        self.render_results_map: Dict[str, RenderResult] = {}

        # -- the run ----------------------------------------------
        self._worker: Optional[GenerationWorker] = None
        self._retired_workers: List[GenerationWorker] = []
        self._start_time: float = 0.0
        self._completed_count: int = 0
        self._metrics = ProcessMetrics()
        self._errors: List[str] = []
        self._log_history: List[str] = []

        # -- the view ---------------------------------------------
        self._quality_filter: str = QUALITY_ALL
        self._side: str = "front"
        self._zoom: float = 1.0
        self._last_pixmap: Optional[QPixmap] = None
        self._field_editors: Dict[str, QLineEdit] = {}

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

        self._setup_ui()

    # -----------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        badge, title, subtitle = workflow.page_header_text(WorkflowStep.GENERATE)
        self.page_header = PageHeader(title, subtitle, badge)
        layout.addWidget(self.page_header)

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

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_batch_column())
        splitter.addWidget(self._build_preview_column())
        splitter.addWidget(self._build_queue_column())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([330, 620, 350])
        body.addWidget(splitter, stretch=1)

        back_label, next_label, badge = workflow.footer_labels(WorkflowStep.GENERATE)
        self.nav_bar = PageFooter(
            prev_label=back_label,
            next_label=next_label,
            step_badge=badge,
            parent=self,
        )
        self.nav_bar.back_requested.connect(
            lambda: self.navigate_requested.emit(WorkflowStep.CANVAS_EDITOR.value)
        )
        self.nav_bar.next_requested.connect(
            lambda: self.navigate_requested.emit(WorkflowStep.EXPORT.value)
        )
        layout.addWidget(self.nav_bar)

    # -- left column: the run ---------------------------------------
    def _build_batch_column(self) -> QWidget:
        """Configure the batch, start it and watch the process."""
        card = SurfaceCard("Batch")
        card.setMinimumWidth(250)
        card.setMaximumWidth(380)

        # -- progress ------------------------------------------------
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("0 / 0")
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ background-color: {SURFACE_LOWEST}; border: 1px solid {BORDER_SUBTLE};"
            f" border-radius: 4px; text-align: center; color: {TEXT_PRIMARY};"
            f" font-family: {FONT_FAMILY_MONO}; font-size: 11px; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0052cc, stop:1 #6c8cff);"
            f" border-radius: 3px; }}"
        )
        card.add(self.progress_bar)

        # -- the two numbers that matter ----------------------------
        self.stat_line = StatLine()
        card.add(self.stat_line)

        # -- the action ----------------------------------------------
        self.btn_generate = BusyButton("▶  Launch batch")
        self.btn_generate.setObjectName("btn_primary")
        self.btn_generate.setFixedHeight(CONTROL_HEIGHT + 6)
        self.btn_generate.setStyleSheet(
            "font-size: 13px; font-weight: bold; padding: 4px 16px;"
        )
        self.btn_generate.clicked.connect(self._start_generation)
        card.add(self.btn_generate)

        action_row = QHBoxLayout()
        action_row.setSpacing(6)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btn_ghost")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setFixedHeight(CONTROL_HEIGHT)
        self.btn_cancel.clicked.connect(self._cancel_generation)
        action_row.addWidget(self.btn_cancel)

        self.btn_goto_export = QPushButton("Proceed to export →")
        self.btn_goto_export.setObjectName("btn_secondary")
        self.btn_goto_export.setEnabled(False)
        self.btn_goto_export.setFixedHeight(CONTROL_HEIGHT)
        self.btn_goto_export.clicked.connect(lambda: self.goto_export_requested.emit())
        action_row.addWidget(self.btn_goto_export)

        card.add_layout(action_row)

        # -- the configuration ---------------------------------------
        config_title = QLabel("CONFIGURATION")
        config_title.setProperty("role", "sectionLabel")
        card.add(config_title)

        self.lbl_chk_records = QLabel("0 loaded (0 valid)")
        self.lbl_chk_photos = QLabel("0 matched (0 missing)")
        self.lbl_chk_template = QLabel("None selected")
        self.lbl_chk_output = QLabel("PNG @ 300 DPI")
        for label in (
            self.lbl_chk_records,
            self.lbl_chk_photos,
            self.lbl_chk_template,
            self.lbl_chk_output,
        ):
            label.setProperty("role", "specValue")
            label.setWordWrap(True)

        checklist = QFrame()
        checklist.setObjectName("workspace_panel")
        checklist_layout = QVBoxLayout(checklist)
        checklist_layout.setContentsMargins(10, 8, 10, 8)
        checklist_layout.setSpacing(5)

        for key, value in (
            ("Records", self.lbl_chk_records),
            ("Photos", self.lbl_chk_photos),
            ("Template", self.lbl_chk_template),
            ("Output", self.lbl_chk_output),
        ):
            row = QHBoxLayout()
            row.setSpacing(8)
            caption = QLabel(key)
            caption.setProperty("role", "specKey")
            caption.setFixedWidth(64)
            row.addWidget(caption)
            row.addWidget(value, stretch=1)
            checklist_layout.addLayout(row)

        card.add(checklist)

        # Batch scope.
        scope_row = QHBoxLayout()
        scope_row.setSpacing(6)

        self.scope_group = QButtonGroup(self)
        self.scope_group.setExclusive(True)

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

        # Raster output.
        output_row = QHBoxLayout()
        output_row.setSpacing(6)

        self.cmb_format = QComboBox()
        self.cmb_format.addItem("PNG 24-bit", "PNG")
        self.cmb_format.addItem("JPEG High", "JPEG")
        self.cmb_format.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_format.currentIndexChanged.connect(self._on_output_changed)

        self.cmb_dpi = QComboBox()
        for dpi in (150, 300, 600):
            self.cmb_dpi.addItem(f"{dpi} DPI", dpi)
        self.cmb_dpi.setCurrentIndex(1)  # 300 DPI is the studio default
        self.cmb_dpi.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_dpi.currentIndexChanged.connect(self._on_output_changed)

        output_row.addWidget(self.cmb_format)
        output_row.addWidget(self.cmb_dpi)
        card.add_layout(output_row)

        self.lbl_naming = QLabel("")
        self.lbl_naming.setProperty("role", "specKey")
        card.add(self.lbl_naming)

        # -- the log --------------------------------------------------
        log_title = QLabel("EVENT LOG")
        log_title.setProperty("role", "sectionLabel")
        card.add(log_title)

        log_row = QHBoxLayout()
        log_row.setSpacing(6)

        self.cmb_log_filter = QComboBox()
        self.cmb_log_filter.addItem("All events", "all")
        self.cmb_log_filter.addItem("Errors only", "errors")
        self.cmb_log_filter.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_log_filter.currentIndexChanged.connect(self._refresh_log)
        log_row.addWidget(self.cmb_log_filter)

        self.lbl_error_count = QLabel("0 failures")
        self.lbl_error_count.setProperty("role", "specKey")
        log_row.addWidget(self.lbl_error_count)
        log_row.addStretch()
        card.add_layout(log_row)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QTextEdit.NoWrap)
        self.log_output.setStyleSheet(
            f"QTextEdit {{ background-color: {SURFACE_LOWEST}; color: #8ED0FF;"
            f" font-family: {FONT_FAMILY_MONO}; font-size: 10px;"
            f" border: 1px solid {BORDER_SUBTLE}; border-radius: 4px; padding: 4px; }}"
        )
        card.add(self.log_output, stretch=1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumWidth(250)
        scroll.setMaximumWidth(380)
        scroll.setWidget(card)
        return scroll

    # -- centre column: the card -------------------------------------
    def _build_preview_column(self) -> QWidget:
        """The card that is reviewed, with the fields of its record."""
        card = SurfaceCard("Card")
        card.setMinimumWidth(280)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.side_group = QButtonGroup(self)
        self.side_group.setExclusive(True)

        for side, caption in (("front", "Front"), ("back", "Back")):
            button = QPushButton(caption)
            button.setCheckable(True)
            button.setFixedHeight(CONTROL_HEIGHT)
            button.setObjectName("btn_stepper")
            if side == "front":
                button.setChecked(True)
            button.clicked.connect(lambda checked, s=side: self._on_side_changed(s))
            self.side_group.addButton(button)
            toolbar.addWidget(button)

        toolbar.addSpacing(10)

        self.btn_zoom_out = QPushButton("−")
        self.btn_zoom_out.setToolTip("Zoom out")
        self.btn_zoom_out.setFixedSize(CONTROL_HEIGHT, CONTROL_HEIGHT)
        self.btn_zoom_out.setObjectName("btn_icon")
        self.btn_zoom_out.clicked.connect(lambda: self._change_zoom(-0.25))
        toolbar.addWidget(self.btn_zoom_out)

        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setProperty("role", "monoMuted")
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        self.lbl_zoom.setFixedWidth(52)
        toolbar.addWidget(self.lbl_zoom)

        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setToolTip("Zoom in")
        self.btn_zoom_in.setFixedSize(CONTROL_HEIGHT, CONTROL_HEIGHT)
        self.btn_zoom_in.setObjectName("btn_icon")
        self.btn_zoom_in.clicked.connect(lambda: self._change_zoom(0.25))
        toolbar.addWidget(self.btn_zoom_in)

        self.btn_zoom_fit = QPushButton("Fit")
        self.btn_zoom_fit.setToolTip("Fit the card into the viewport")
        self.btn_zoom_fit.setFixedHeight(CONTROL_HEIGHT)
        self.btn_zoom_fit.setObjectName("btn_ghost")
        self.btn_zoom_fit.clicked.connect(self._fit_preview)
        toolbar.addWidget(self.btn_zoom_fit)

        toolbar.addStretch()

        self.lbl_preview_meta = QLabel("")
        self.lbl_preview_meta.setProperty("role", "specKey")
        toolbar.addWidget(self.lbl_preview_meta)

        card.add_layout(toolbar)

        # The preview fills the free space of the column.
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        preview_container = QWidget()
        preview_container.setProperty("role", "flat")
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setAlignment(Qt.AlignCenter)

        self.lbl_card_preview = QLabel("<i>No card to preview</i>")
        self.lbl_card_preview.setAlignment(Qt.AlignCenter)
        self.lbl_card_preview.setStyleSheet(
            f"border: 1px dashed {BORDER_SUBTLE}; border-radius: 6px; padding: 20px; color: {TEXT_MUTED};"
        )
        preview_layout.addWidget(self.lbl_card_preview)
        self.preview_scroll.setWidget(preview_container)
        card.add(self.preview_scroll, stretch=1)

        # The fields of the record sit under the card.
        fields_header = QHBoxLayout()
        fields_header.setSpacing(6)

        fields_title = QLabel("RECORD FIELDS")
        fields_title.setProperty("role", "sectionLabel")
        fields_header.addWidget(fields_title)
        fields_header.addStretch()

        self.btn_apply_fields = QPushButton("Apply & re-render")
        self.btn_apply_fields.setObjectName("btn_secondary")
        self.btn_apply_fields.setFixedHeight(CONTROL_HEIGHT)
        self.btn_apply_fields.setEnabled(False)
        self.btn_apply_fields.clicked.connect(self._apply_field_edits)
        fields_header.addWidget(self.btn_apply_fields)
        card.add_layout(fields_header)

        self.fields_scroll = QScrollArea()
        self.fields_scroll.setWidgetResizable(True)
        self.fields_scroll.setFixedHeight(120)
        self.fields_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self.fields_container = QWidget()
        self.fields_container.setProperty("role", "flat")
        self.fields_layout = QVBoxLayout(self.fields_container)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        self.fields_layout.setSpacing(6)
        self.fields_scroll.setWidget(self.fields_container)
        card.add(self.fields_scroll)

        return card

    # -- right column: the queue -------------------------------------
    def _build_queue_column(self) -> QWidget:
        """The queue of the produced cards and the decisions on them."""
        card = SurfaceCard("Queue")
        card.setMinimumWidth(250)
        card.setMaximumWidth(380)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter by PIN or name...")
        self.txt_search.setProperty("role", "fieldFlat")
        self.txt_search.setFixedHeight(CONTROL_HEIGHT)
        self.txt_search.textChanged.connect(self._on_search_changed)
        card.add(self.txt_search)

        quality_row = QHBoxLayout()
        quality_row.setSpacing(4)

        self.quality_buttons: Dict[str, QPushButton] = {}
        self.quality_group = QButtonGroup(self)
        self.quality_group.setExclusive(True)

        for kind, caption in (
            (QUALITY_ALL, "All"),
            (QUALITY_VALID, "Valid"),
            (QUALITY_WARN, "Warn"),
            (QUALITY_ERROR, "Err"),
        ):
            button = QPushButton(caption)
            button.setCheckable(True)
            button.setFixedHeight(CONTROL_HEIGHT)
            button.setObjectName("btn_stepper")
            button.setToolTip(f"Show the {caption.lower()} records")
            if kind == QUALITY_ALL:
                button.setChecked(True)
            button.clicked.connect(lambda checked, k=kind: self._on_quality_filter(k))
            self.quality_group.addButton(button)
            self.quality_buttons[kind] = button
            quality_row.addWidget(button)

        quality_row.addStretch()
        card.add_layout(quality_row)

        self.record_model = RecordListModel(self)
        self.record_list = RecordListView()
        self.record_list.setModel(self.record_model)
        self.record_list.record_selected.connect(self._on_record_selected)
        card.add(self.record_list, stretch=1)

        self.lbl_list_info = QLabel("No cards yet")
        self.lbl_list_info.setProperty("role", "specKey")
        card.add(self.lbl_list_info)

        # -- the decision ---------------------------------------------
        index_row = QHBoxLayout()
        index_row.setSpacing(4)

        self.lbl_nav_index = QLabel("Card 0 of 0")
        self.lbl_nav_index.setProperty("role", "cardTitle")
        index_row.addWidget(self.lbl_nav_index)
        index_row.addStretch()

        for caption, tooltip, handler in (
            ("⏮", "First card", self._first),
            ("◀", "Previous card", self._prev),
            ("▶", "Next card", self._next),
            ("⏭", "Last card", self._last),
        ):
            button = QPushButton(caption)
            button.setToolTip(tooltip)
            button.setFixedHeight(CONTROL_HEIGHT)
            button.setObjectName("btn_icon")
            button.clicked.connect(handler)
            index_row.addWidget(button)

        card.add_layout(index_row)

        self.lbl_status_badge = QLabel("STATUS: PENDING")
        self.lbl_status_badge.setAlignment(Qt.AlignCenter)
        self.lbl_status_badge.setProperty("role", "badgeAccent")
        card.add(self.lbl_status_badge)

        self.lbl_photo_status = QLabel("Photo: -")
        self.lbl_photo_status.setWordWrap(True)
        self.lbl_photo_status.setProperty("role", "specKey")
        card.add(self.lbl_photo_status)

        self.lbl_record_details = QLabel("")
        self.lbl_record_details.setProperty("role", "specKey")
        card.add(self.lbl_record_details)

        decisions = QGridLayout()
        decisions.setSpacing(6)

        self.btn_approve = QPushButton("✓ Approve")
        self.btn_approve.setObjectName("btn_success")
        self.btn_approve.setFixedHeight(CONTROL_HEIGHT)
        self.btn_approve.clicked.connect(lambda: self._set_current_status(ReviewStatus.APPROVED))
        decisions.addWidget(self.btn_approve, 0, 0)

        self.btn_reject = QPushButton("✗ Reject")
        self.btn_reject.setObjectName("btn_danger")
        self.btn_reject.setFixedHeight(CONTROL_HEIGHT)
        self.btn_reject.clicked.connect(lambda: self._set_current_status(ReviewStatus.REJECTED))
        decisions.addWidget(self.btn_reject, 0, 1)

        self.btn_correction = QPushButton("⚠ Correction")
        self.btn_correction.setFixedHeight(CONTROL_HEIGHT)
        self.btn_correction.setStyleSheet(
            f"border-color: {SEMANTIC_WARNING}; color: {SEMANTIC_WARNING}; padding: 4px 8px;"
        )
        self.btn_correction.clicked.connect(lambda: self._set_current_status(ReviewStatus.CORRECTION))
        decisions.addWidget(self.btn_correction, 1, 0)

        self.btn_override_photo = QPushButton("Override photo…")
        self.btn_override_photo.setObjectName("btn_secondary")
        self.btn_override_photo.setFixedHeight(CONTROL_HEIGHT)
        self.btn_override_photo.clicked.connect(self._override_photo)
        decisions.addWidget(self.btn_override_photo, 1, 1)

        self.btn_skip = QPushButton("Skip")
        self.btn_skip.setObjectName("btn_secondary")
        self.btn_skip.setFixedHeight(CONTROL_HEIGHT)
        self.btn_skip.clicked.connect(lambda: self._set_current_status(ReviewStatus.SKIPPED))
        decisions.addWidget(self.btn_skip, 2, 0)

        self.btn_regen = QPushButton("⟳ Re-render")
        self.btn_regen.setObjectName("btn_secondary")
        self.btn_regen.setFixedHeight(CONTROL_HEIGHT)
        self.btn_regen.clicked.connect(lambda: self._regenerate_current())
        decisions.addWidget(self.btn_regen, 2, 1)

        card.add_layout(decisions)

        return card

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
        """Update the project context of the workspace."""
        self.template = template
        self.records = records
        self.match_results = match_results
        self.column_mappings = column_mappings
        self.settings = settings

        valid_count = sum(1 for record in records if record.is_valid)
        self.lbl_chk_records.setText(f"{len(records):,} loaded ({valid_count:,} valid)")

        matched_count = sum(
            1
            for match in match_results.values()
            if match.status in (MatchStatus.MATCHED, MatchStatus.OVERRIDDEN)
        )
        missing_count = len(records) - matched_count
        self.lbl_chk_photos.setText(f"{matched_count:,} matched ({missing_count:,} missing)")

        self.lbl_chk_template.setText(template.name if template else "None selected")
        self._update_output_label()
        self._sync_output_widgets()
        self._on_scope_changed()

    def _update_output_label(self) -> None:
        """Show the raster output in the pre-flight list."""
        current = self.settings.output_format
        value = current.value if hasattr(current, "value") else str(current)
        self.lbl_chk_output.setText(f"{value.upper()} @ {self.settings.dpi} DPI")

    def _sync_output_widgets(self) -> None:
        """Push the render settings into the output widgets."""
        current = self.settings.output_format
        value = current.value if hasattr(current, "value") else str(current)
        index = self.cmb_format.findData(value)
        if index < 0:
            index = self.cmb_format.findData("PNG")
        self.cmb_format.setCurrentIndex(index)

        index = self.cmb_dpi.findData(self.settings.dpi)
        if index < 0:
            index = self.cmb_dpi.findData(300)
        self.cmb_dpi.setCurrentIndex(index)

    def _on_output_changed(self) -> None:
        """Apply the chosen raster format and resolution."""
        from id_card_generator.core.constants import OutputFormat

        fmt = self.cmb_format.currentData()
        dpi = self.cmb_dpi.currentData()
        if fmt:
            self.settings.output_format = OutputFormat(fmt)
        if dpi:
            self.settings.dpi = int(dpi)

        extension = "jpg" if fmt == "JPEG" else "png"
        self.lbl_naming.setText(f"{{PIN}}_{{Name}}.{extension}")
        self._update_output_label()

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
            return

        start = self.spin_range_start.value()
        end = max(start, self.spin_range_end.value())
        self.spin_range_end.setValue(end)
        self.lbl_range_hint.setText(
            f"Records {start:,} - {end:,} ({end - start + 1:,} cards) of {total:,}."
        )

    def _selected_records(self) -> List[SourceRecord]:
        """Return the records that the batch scope selects."""
        if not self.btn_scope_range.isChecked():
            return list(self.records)
        start = max(1, self.spin_range_start.value())
        end = max(start, self.spin_range_end.value())
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

        self.btn_generate.set_busy(True)
        self.btn_generate.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_goto_export.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"0 / {len(records):,}")
        self.log_output.clear()
        self._log_history.clear()
        self._errors.clear()
        self._completed_count = 0
        self.lbl_status_badge.setText("RENDERING")
        self.pill_engine_state.set_status("RUNNING", color=PRIMARY)

        self._start_time = time.time()
        self._metrics = ProcessMetrics()
        self._timer.start()

        workers = BatchGenerator.resolve_workers(len(records))

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

    def _on_tick(self) -> None:
        """Report the CPU load and the memory of the process."""
        cpu, memory = self._metrics.sample()
        self.stat_line.set_stats([
            ("CPU", f"{cpu:.0f} %"),
            ("Memory", f"{memory:.0f} MB"),
        ])

    def _refresh_metrics(self) -> None:
        """Start the measurement over and show the current numbers."""
        self._metrics = ProcessMetrics()
        self._on_tick()

    def _stop_worker(self) -> None:
        """Join the running worker before it is replaced."""
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
            self.pill_engine_state.set_status("CANCELLING", color=SEMANTIC_WARNING)
            self.btn_cancel.setEnabled(False)

    # -- worker events -------------------------------------------------
    def _on_progress(self, current: int, total: int, pin: str = "", message: str = "") -> None:
        if total <= 0:
            return
        self._completed_count = current
        self.progress_bar.setValue(int(current / total * 100))
        self.progress_bar.setFormat(f"{current:,} / {total:,} cards")

    def _on_status(self, msg: str) -> None:
        text = str(msg)
        self._log_history.append(text)

        is_error = text.startswith("[ERROR]") or text.startswith("[FATAL]")
        if is_error:
            self._errors.append(text)
            self.lbl_error_count.setText(f"{len(self._errors)} failure(s)")

        if self.cmb_log_filter.currentData() == "errors" and not is_error:
            return

        self.log_output.append(text)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

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
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_card_generated(self, result) -> None:
        """A single card was rendered."""
        return

    def _on_error(self, message: str) -> None:
        """The batch run failed."""
        self._timer.stop()
        self._refresh_metrics()
        self.btn_generate.set_busy(False)
        self.btn_generate.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.pill_engine_state.set_status("ERROR", color=SEMANTIC_ERROR)
        self.notice.set_message(f"Generation failed: {message}", severity="error")
        self._on_status(f"[FATAL] {message}")

    def _on_finished(self, summary: GenerationSummary) -> None:
        """The batch run finished - the cards are now in the queue."""
        self._timer.stop()
        self._refresh_metrics()
        self.btn_generate.set_busy(False)
        self.btn_generate.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_goto_export.setEnabled(True)
        self.nav_bar.btn_next.setEnabled(True)

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

        self._on_status("\n" + "=" * 50)
        self._on_status(status_text)

        # The produced cards become the queue that is reviewed.
        self.load_review_session(
            source_records=self.records,
            generation_results=summary.results,
            template=self.template,
            match_results=self.match_results,
            column_mappings=self.column_mappings,
        )

        self.generation_completed.emit(summary)

    # -----------------------------------------------------------------
    # The review session
    # -----------------------------------------------------------------
    def load_review_session(
        self,
        source_records: List[SourceRecord],
        generation_results: List[RenderResult],
        template: Optional[TemplateDefinition],
        match_results: Dict[str, PhotoMatchResult],
        column_mappings: Dict[str, str],
        saved_states: Optional[Dict[str, ReviewStatus]] = None,
    ) -> None:
        """Fill the queue with the produced cards."""
        self.template = template or self.template
        self.source_records_map = {r.record_id: r for r in source_records}
        self.match_results_map = match_results
        self.column_mappings = column_mappings
        self.render_results_map = {r.record_id: r for r in generation_results}

        self.manager.initialize_from_generation(
            source_records=source_records,
            generation_results=generation_results,
            saved_states=saved_states,
        )
        self._update_display()

    def _on_filter_clicked(self, status: Optional[ReviewStatus]) -> None:
        """Filter the queue by the review state."""
        self.manager.filter_status = status
        self._update_display()

    def _on_quality_filter(self, kind: str) -> None:
        """Filter the queue by the quality of the records."""
        self._quality_filter = kind
        self._update_display()

    def _on_search_changed(self, text: str) -> None:
        self.manager.search_query = text
        self._update_display()

    def _on_record_selected(self, record_id: str) -> None:
        """Jump to the record that was picked in the queue."""
        for index, record in enumerate(self.manager.get_filtered_records()):
            if record.record_id == record_id:
                self.manager.current_index = index
                self._update_display()
                return

    # -- the quality of a record --------------------------------------
    def _classify(self, record: ReviewRecord) -> tuple:
        """Return the severity and the flags of a record."""
        flags: List[str] = []
        severity = SEVERITY_OK

        source = self.source_records_map.get(record.record_id)
        if source is not None:
            for error in source.validation_errors:
                flags.append(f"Validation error: {error}")
            for warning in source.validation_warnings:
                flags.append(f"Validation warning: {warning}")

        result = self.render_results_map.get(record.record_id)
        if result is not None:
            for warning in result.warnings:
                flags.append(warning)
            if not result.success:
                flags.append(
                    f"Generation failed: {result.error_message or 'unknown error'}"
                )

        match = self.match_results_map.get(record.record_id)
        if match is not None and match.status in (
            MatchStatus.MISSING,
            MatchStatus.AMBIGUOUS,
        ):
            flags.append(
                "Missing photo - fallback applied"
                if match.status == MatchStatus.MISSING
                else f"Ambiguous photo match: {match.details or match.matched_filename or ''}"
            )

        if any(flag.startswith("Generation failed") for flag in flags):
            severity = SEVERITY_ERROR
        elif any(flag.startswith("Validation error") for flag in flags):
            severity = SEVERITY_ERROR
        elif flags:
            severity = SEVERITY_WARN

        return severity, tuple(flags)

    def _build_entries(self) -> List[RecordListEntry]:
        """Build the rows of the queue."""
        entries: List[RecordListEntry] = []

        for record in self.manager.get_filtered_records():
            severity, flags = self._classify(record)

            if self._quality_filter == QUALITY_VALID and severity != SEVERITY_OK:
                continue
            if self._quality_filter == QUALITY_WARN and severity != SEVERITY_WARN:
                continue
            if self._quality_filter == QUALITY_ERROR and severity != SEVERITY_ERROR:
                continue

            entries.append(
                RecordListEntry(
                    record_id=record.record_id,
                    pin=record.pin,
                    name=record.name,
                    status=record.status.value,
                    severity=severity,
                    flags=flags,
                )
            )

        return entries

    def _quality_counts(self) -> Dict[str, int]:
        """Count the records per quality."""
        counts = {
            QUALITY_ALL: 0,
            QUALITY_VALID: 0,
            QUALITY_WARN: 0,
            QUALITY_ERROR: 0,
        }
        for record in self.manager.get_filtered_records():
            severity, _ = self._classify(record)
            counts[QUALITY_ALL] += 1
            if severity == SEVERITY_OK:
                counts[QUALITY_VALID] += 1
            elif severity == SEVERITY_WARN:
                counts[QUALITY_WARN] += 1
            else:
                counts[QUALITY_ERROR] += 1
        return counts

    # -- the display ----------------------------------------------------
    def _update_display(self) -> None:
        record = self.manager.get_current_record()
        filtered = self.manager.get_filtered_records()

        entries = self._build_entries()
        self.record_model.set_entries(entries)

        counts = self._quality_counts()
        captions = {
            QUALITY_ALL: "All",
            QUALITY_VALID: "Valid",
            QUALITY_WARN: "Warn",
            QUALITY_ERROR: "Err",
        }
        for kind, button in self.quality_buttons.items():
            button.setText(f"{captions[kind]} ({counts[kind]})")

        total = len(self.manager.records)
        if total:
            self.lbl_list_info.setText(f"{len(entries):,} of {total:,} cards")
        else:
            self.lbl_list_info.setText("No cards yet - launch the batch")

        if not record or not filtered:
            self.lbl_nav_index.setText("Card 0 of 0")
            self.lbl_card_preview.setPixmap(QPixmap())
            self.lbl_card_preview.setText(
                "<i>No card to preview yet.\nLaunch the batch to produce the cards.</i>"
            )
            self.lbl_status_badge.setText("NO CARD")
            self.lbl_photo_status.setText("Photo: -")
            self.lbl_record_details.setText("")
            self._clear_field_editors()
            self.btn_apply_fields.setEnabled(False)
            self._set_decisions_enabled(False)
            return

        self.lbl_nav_index.setText(f"Card {self.manager.current_index + 1} of {len(filtered)}")
        self._set_decisions_enabled(True)

        # The status badge.
        status = record.status
        self.lbl_status_badge.setText(f"STATUS: {status.value.upper()}")
        if status == ReviewStatus.APPROVED:
            self.lbl_status_badge.setStyleSheet(self._badge_style(SEMANTIC_SUCCESS))
        elif status == ReviewStatus.REJECTED:
            self.lbl_status_badge.setStyleSheet(self._badge_style(SEMANTIC_ERROR))
        elif status == ReviewStatus.CORRECTION:
            self.lbl_status_badge.setStyleSheet(self._badge_style(SEMANTIC_WARNING))
        else:
            self.lbl_status_badge.setStyleSheet(
                f"background-color: {SURFACE_HIGH}; color: {TEXT_PRIMARY};"
                f" font-weight: bold; padding: 6px; border-radius: 4px;"
            )

        self._update_preview(record)
        self._populate_field_editors(record)
        self._update_metadata(record)

        row = self.record_model.row_for_record(record.record_id)
        if row >= 0:
            self.record_list.setCurrentIndex(self.record_model.index(row, 0))

    def _set_decisions_enabled(self, enabled: bool) -> None:
        """Enable the decisions only when a card is selected."""
        for button in (
            self.btn_approve,
            self.btn_reject,
            self.btn_correction,
            self.btn_skip,
            self.btn_regen,
            self.btn_override_photo,
        ):
            button.setEnabled(enabled)

    @staticmethod
    def _badge_style(color: str) -> str:
        """A soft badge around a semantic colour."""
        tint = QColor(color)
        return (
            f"background-color: rgba({tint.red()}, {tint.green()}, {tint.blue()}, 48);"
            f" border: 1px solid {color}; color: {color};"
            f" font-weight: bold; padding: 6px; border-radius: 4px;"
        )

    # -- the preview -----------------------------------------------------
    def _update_preview(self, record: ReviewRecord) -> None:
        """Show the card of the current record."""
        if self._side == "back":
            self._render_back_side(record)
            return

        if record.rendered_image_path and Path(record.rendered_image_path).exists():
            pixmap = QPixmap(record.rendered_image_path)
            if not pixmap.isNull():
                self._show_pixmap(pixmap)
                self.lbl_preview_meta.setText(Path(record.rendered_image_path).name)
                return
            self.lbl_card_preview.setPixmap(QPixmap())
            self.lbl_card_preview.setText("Failed to load image preview")
            return

        self.lbl_card_preview.setPixmap(QPixmap())
        self.lbl_card_preview.setText(
            f"Card image missing on disk:\n{record.rendered_image_path or 'not rendered'}"
        )

    def _render_back_side(self, record: ReviewRecord) -> None:
        """Render the back face of the current record on demand."""
        if not self.template:
            self.lbl_card_preview.setPixmap(QPixmap())
            self.lbl_card_preview.setText("<i>No template to render the back side</i>")
            return

        source = self.source_records_map.get(record.record_id)
        match = self.match_results_map.get(record.record_id)
        photo_path = match.photo_path if match else None

        try:
            image, _warnings = PillowRenderer.render_card(
                template=self.template,
                record=source,
                photo_path=photo_path,
                column_mappings=self.column_mappings,
                settings=self.settings,
                side="back",
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to render the back side: %s", exc)
            self.lbl_card_preview.setPixmap(QPixmap())
            self.lbl_card_preview.setText(f"Back side could not be rendered:\n{exc}")
            return

        pixmap = QPixmap.fromImage(pil_to_qimage(image))
        self._show_pixmap(pixmap)
        self.lbl_preview_meta.setText("Back side (live render)")

    def _show_pixmap(self, pixmap: QPixmap) -> None:
        """Show a card image, scaled to the viewport and scaled by the zoom."""
        if pixmap.isNull():
            self.lbl_card_preview.setPixmap(QPixmap())
            self._last_pixmap = None
            return

        self._last_pixmap = pixmap

        # 100 % means "the whole card fits into the viewport".
        available = self.preview_scroll.viewport().width() - 24
        if available <= 0:
            available = pixmap.width()
        fit = min(1.0, available / float(pixmap.width()))

        scaled = pixmap.scaled(
            pixmap.size() * (fit * self._zoom),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.lbl_card_preview.setPixmap(scaled)
        self.lbl_zoom.setText(f"{int(self._zoom * 100)}%")

    def _change_zoom(self, delta: float) -> None:
        """Zoom the preview in or out."""
        self._zoom = max(0.25, min(4.0, self._zoom + delta))
        record = self.manager.get_current_record()
        if record:
            self._update_preview(record)
        else:
            self.lbl_zoom.setText(f"{int(self._zoom * 100)}%")

    def _fit_preview(self) -> None:
        """Fit the card into the viewport."""
        self._zoom = 1.0
        record = self.manager.get_current_record()
        if record:
            self._update_preview(record)

    def _on_side_changed(self, side: str) -> None:
        """Flip the card between the front and the back face."""
        self._side = side
        record = self.manager.get_current_record()
        if record:
            self._update_preview(record)

    # -- the field editor ------------------------------------------------
    def _clear_field_editors(self) -> None:
        """Remove the editors of the previous record."""
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._field_editors.clear()

    def _populate_field_editors(self, record: ReviewRecord) -> None:
        """Build the editors for the fields of the current record."""
        self._clear_field_editors()

        source = self.source_records_map.get(record.record_id)
        if source is None:
            return

        for key, value in list(source.data.items())[:MAX_EDITED_FIELDS]:
            row = QWidget()
            row.setProperty("role", "flat")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            caption = QLabel(str(key))
            caption.setProperty("role", "specKey")
            caption.setFixedWidth(120)
            row_layout.addWidget(caption)

            editor = QLineEdit("" if value is None else str(value))
            editor.setProperty("role", "fieldFlat")
            row_layout.addWidget(editor, stretch=1)

            self._field_editors[str(key)] = editor
            self.fields_layout.addWidget(row)

        if not self._field_editors:
            hint = QLabel("This record has no mapped fields.")
            hint.setProperty("role", "specKey")
            self.fields_layout.addWidget(hint)

    def _apply_field_edits(self) -> None:
        """Write the edited values back and re-render the card."""
        record = self.manager.get_current_record()
        if not record:
            return

        source = self.source_records_map.get(record.record_id)
        if source is None:
            return

        changed = 0
        for key, editor in self._field_editors.items():
            if key in source.data:
                new_value = editor.text()
                if str(source.data[key]) != new_value:
                    source.data[key] = new_value
                    changed += 1

        if changed:
            self.notice.set_message(
                f"Updated {changed} field(s) and re-rendered the card.",
                severity="success",
            )
        else:
            self.notice.set_message("Nothing changed on this record.", severity="info")

        self._regenerate_current(keep_notice=True)

    def _override_photo(self) -> None:
        """Pick a different photo for the current record."""
        record = self.manager.get_current_record()
        if not record:
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a photograph",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not path:
            return

        self.match_results_map[record.record_id] = PhotoMatchResult(
            pin=record.pin,
            record_id=record.record_id,
            status=MatchStatus.OVERRIDDEN,
            photo_path=path,
            matched_filename=Path(path).name,
            is_overridden=True,
            details="Photo overridden by the reviewer.",
        )
        self.notice.set_message(
            f"Photo overridden with {Path(path).name}.", severity="success"
        )
        self._regenerate_current(keep_notice=True)

    # -- the metadata ------------------------------------------------------
    def _update_metadata(self, record: ReviewRecord) -> None:
        """Show the metadata of the current record."""
        source = self.source_records_map.get(record.record_id)
        match = self.match_results_map.get(record.record_id)

        details = [f"PIN {record.pin or '(None)'}"]
        if source is not None:
            details.append(f"Row {source.row_index + 1}")

        if match is not None:
            if match.status in (MatchStatus.MATCHED, MatchStatus.OVERRIDDEN):
                self.lbl_photo_status.setText(
                    f"Photo: {match.status.value} · {Path(match.photo_path or '').name or '-'}"
                )
            else:
                self.lbl_photo_status.setText(
                    f"Photo: {match.status.value} · fallback used"
                )
        else:
            self.lbl_photo_status.setText("Photo: not matched")

        self.lbl_record_details.setText(" · ".join(details))

    # -----------------------------------------------------------------
    # The decisions
    # -----------------------------------------------------------------
    def _set_current_status(self, status: ReviewStatus) -> None:
        record = self.manager.get_current_record()
        if not record:
            return
        self.manager.update_status(record.record_id, status)
        self.review_updated.emit(self.manager)
        self.manager.next_record()
        self._update_display()

    def _batch_approve(self) -> None:
        count = self.manager.batch_approve_all_valid()
        self.review_updated.emit(self.manager)
        self._update_display()
        self.notice.set_message(
            f"Approved {count} valid cards. Cards with missing photos or critical "
            f"errors stay pending review.",
            severity="success",
        )

    def _regenerate_current(self, keep_notice: bool = False) -> None:
        record = self.manager.get_current_record()
        if not record or not self.template:
            return
        source = self.source_records_map.get(record.record_id)
        if not source:
            return

        match = self.match_results_map.get(record.record_id)
        photo_path = match.photo_path if match else None

        try:
            res = BatchGenerator.generate_single_card(
                template=self.template,
                record=source,
                match_result=match,
                column_mappings=self.column_mappings,
                settings=self.settings,
                target_dir=get_staging_dir(),
            )
            if res.success and res.image_path:
                record.rendered_image_path = str(res.image_path)
                self.render_results_map[record.record_id] = res
                self.manager.update_status(record.record_id, ReviewStatus.PENDING)
                self.review_updated.emit(self.manager)
                self._update_display()
                if not keep_notice:
                    self.notice.set_message(
                        f"Re-rendered the card for PIN {record.pin}.", severity="success"
                    )
            else:
                self.notice.set_message(
                    f"Failed to re-render: {res.error_message}", severity="error"
                )
        except Exception as e:
            logger.error("Failed to regenerate card: %s", e)
            self.notice.set_message(f"Failed to re-render card: {e}", severity="error")

    # -----------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------
    def _first(self) -> None:
        self.manager.first_record()
        self._update_display()

    def _prev(self) -> None:
        self.manager.prev_record()
        self._update_display()

    def _next(self) -> None:
        self.manager.next_record()
        self._update_display()

    def _last(self) -> None:
        self.manager.last_record()
        self._update_display()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Keep the preview fitted when the window is resized."""
        super().resizeEvent(event)
        pixmap = getattr(self, "_last_pixmap", None)
        if pixmap is not None and not pixmap.isNull():
            self._show_pixmap(pixmap)
