"""Card review and approval workstation.

The screen follows the Stitch "record preview & live data inspector" layout:

* a left column with the virtual record list, a search field and the data
  quality filters (all / valid / warn / error),
* a centre column with the high resolution card preview, the zoom controls
  and the front / back switch,
* a right column with the record field editor, the photo override and the
  approval controls of the selected card.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QToolButton,
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
from id_card_generator.generation.batch_generator import BatchGenerator
from id_card_generator.rendering.pillow_renderer import PillowRenderer
from id_card_generator.resources.resource_loader import get_staging_dir
from id_card_generator.review.review_manager import ReviewManager
from id_card_generator.ui import workflow
from id_card_generator.ui.components.layout_blocks import StatLine
from id_card_generator.ui.components.page_scaffold import InlineNotice, PageFooter, PageHeader
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

# The four data quality filters of the record list.
QUALITY_ALL = "all"
QUALITY_VALID = "valid"
QUALITY_WARN = "warn"
QUALITY_ERROR = "error"

# How many fields of a record the editor shows at once.
MAX_EDITED_FIELDS = 24


class ReviewPage(QWidget):
    """Review interface ensuring cards are inspected and explicitly approved."""

    review_updated = Signal(object)  # ReviewManager
    goto_export_requested = Signal()
    navigate_requested = Signal(str)  # WorkflowStep value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = ReviewManager()
        self.template: Optional[TemplateDefinition] = None
        self.source_records_map: Dict[str, SourceRecord] = {}
        self.match_results_map: Dict[str, PhotoMatchResult] = {}
        self.render_results_map: Dict[str, RenderResult] = {}
        self.settings = RenderSettings()
        self.column_mappings: Dict[str, str] = {}
        self._current_filter: Optional[ReviewStatus] = None
        self._quality_filter: str = QUALITY_ALL
        self._side: str = "front"
        self._zoom: float = 1.0
        self._last_pixmap: Optional[QPixmap] = None
        self._field_editors: Dict[str, QLineEdit] = {}

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
        badge, title, subtitle = workflow.page_header_text(WorkflowStep.REVIEW)
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

        # ---------------------------------------------------------
        # 1. Status ribbon: counts, review filters, batch actions
        # ---------------------------------------------------------
        top_card = QFrame()
        top_card.setObjectName("workspace_panel")
        top_layout = QVBoxLayout(top_card)
        top_layout.setContentsMargins(10, 8, 10, 8)
        top_layout.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(8)

        # Compatibility label for any test expecting lbl_counts
        self.lbl_counts = QLabel("Review Summary")
        self.lbl_counts.setVisible(False)
        row1.addWidget(self.lbl_counts)

        self.pill_approved = StatusPill("APPROVED: 0", color=SEMANTIC_SUCCESS)
        self.pill_pending = StatusPill("PENDING: 0", color=SEMANTIC_WARNING)
        self.pill_rejected = StatusPill("REJECTED: 0", color=SEMANTIC_ERROR)
        self.pill_correction = StatusPill("CORRECTION: 0", color=PRIMARY)

        for pill in (
            self.pill_approved,
            self.pill_pending,
            self.pill_rejected,
            self.pill_correction,
        ):
            pill.setVisible(False)

        self.stat_line = StatLine()
        row1.addWidget(self.stat_line)
        row1.addStretch()

        self.btn_batch_approve = QPushButton("✓ Approve All Valid")
        self.btn_batch_approve.setObjectName("btn_success")
        self.btn_batch_approve.clicked.connect(self._batch_approve)
        row1.addWidget(self.btn_batch_approve)

        self.btn_goto_export = QPushButton("Proceed to Sheet Export ▶")
        self.btn_goto_export.setObjectName("btn_primary")
        self.btn_goto_export.clicked.connect(lambda: self.goto_export_requested.emit())
        row1.addWidget(self.btn_goto_export)

        top_layout.addLayout(row1)

        # Row 2: review status filters
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        lbl_filt = QLabel("Show:")
        lbl_filt.setProperty("role", "specKey")
        row2.addWidget(lbl_filt)

        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)

        filters = [
            ("all", "All Records", None),
            ("pending", "Pending", ReviewStatus.PENDING),
            ("approved", "Approved", ReviewStatus.APPROVED),
            ("rejected", "Rejected", ReviewStatus.REJECTED),
            ("correction", "Needs Correction", ReviewStatus.CORRECTION),
        ]

        for fid, flabel, fval in filters:
            btn = QPushButton(flabel)
            btn.setCheckable(True)
            btn.setFixedHeight(CONTROL_HEIGHT)
            btn.setObjectName("btn_stepper")
            if fid == "all":
                btn.setChecked(True)
            btn.clicked.connect(lambda chk, v=fval: self._on_filter_clicked(v))
            self.filter_group.addButton(btn)
            row2.addWidget(btn)

        row2.addStretch()
        top_layout.addLayout(row2)

        body.addWidget(top_card)

        # ---------------------------------------------------------
        # 2. The three column workstation
        # ---------------------------------------------------------
        splitter = QSplitter(Qt.Horizontal)

        splitter.addWidget(self._build_record_column())
        splitter.addWidget(self._build_preview_column())
        splitter.addWidget(self._build_inspector_column())

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([300, 620, 340])
        body.addWidget(splitter, stretch=1)

        # ---------------------------------------------------------
        # 3. Bottom Step Navigation Bar
        # ---------------------------------------------------------
        back_label, next_label, badge = workflow.footer_labels(WorkflowStep.REVIEW)
        self.nav_bar = PageFooter(
            prev_label=back_label,
            next_label=next_label,
            step_badge=badge,
            parent=self,
        )
        self.nav_bar.back_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.GENERATE.value))
        self.nav_bar.next_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.EXPORT.value))
        layout.addWidget(self.nav_bar)

    # -- left column --------------------------------------------------
    def _build_record_column(self) -> QWidget:
        """The virtual record list with its search and quality filters."""
        card = SurfaceCard("Records")
        card.setMinimumWidth(240)
        card.setMaximumWidth(380)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter by PIN or name...")
        self.txt_search.setProperty("role", "fieldFlat")
        self.txt_search.textChanged.connect(self._on_search_changed)
        card.add(self.txt_search)

        # Data quality filters.
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
            btn = QPushButton(caption)
            btn.setCheckable(True)
            btn.setFixedHeight(CONTROL_HEIGHT)
            btn.setObjectName("btn_stepper")
            btn.setToolTip(f"Show the {caption.lower()} records")
            if kind == QUALITY_ALL:
                btn.setChecked(True)
            btn.clicked.connect(lambda chk, k=kind: self._on_quality_filter(k))
            self.quality_group.addButton(btn)
            self.quality_buttons[kind] = btn
            quality_row.addWidget(btn)

        quality_row.addStretch()
        card.add_layout(quality_row)

        self.record_model = RecordListModel(self)
        self.record_list = RecordListView()
        self.record_list.setModel(self.record_model)
        self.record_list.record_selected.connect(self._on_record_selected)
        card.add(self.record_list, stretch=1)

        self.lbl_list_info = QLabel("No records")
        self.lbl_list_info.setProperty("role", "specKey")
        card.add(self.lbl_list_info)

        return card

    # -- centre column ------------------------------------------------
    def _build_preview_column(self) -> QWidget:
        """The card preview with the zoom controls and the front / back switch."""
        card = SurfaceCard("Card Preview")
        card.setMinimumWidth(320)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        # Front / back switch.
        self.side_group = QButtonGroup(self)
        self.side_group.setExclusive(True)

        for side, caption in (("front", "Front"), ("back", "Back")):
            btn = QPushButton(caption)
            btn.setCheckable(True)
            btn.setFixedHeight(CONTROL_HEIGHT)
            btn.setObjectName("btn_stepper")
            if side == "front":
                btn.setChecked(True)
            btn.clicked.connect(lambda chk, s=side: self._on_side_changed(s))
            self.side_group.addButton(btn)
            toolbar.addWidget(btn)

        toolbar.addSpacing(10)

        self.btn_zoom_out = QToolButton()
        self.btn_zoom_out.setText("−")
        self.btn_zoom_out.setToolTip("Zoom out")
        self.btn_zoom_out.setFixedSize(CONTROL_HEIGHT, CONTROL_HEIGHT)
        self.btn_zoom_out.setObjectName("btn_ghost")
        self.btn_zoom_out.clicked.connect(lambda: self._change_zoom(-0.25))
        toolbar.addWidget(self.btn_zoom_out)

        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setProperty("role", "monoMuted")
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        self.lbl_zoom.setFixedWidth(52)
        toolbar.addWidget(self.lbl_zoom)

        self.btn_zoom_in = QToolButton()
        self.btn_zoom_in.setText("+")
        self.btn_zoom_in.setToolTip("Zoom in")
        self.btn_zoom_in.setFixedSize(CONTROL_HEIGHT, CONTROL_HEIGHT)
        self.btn_zoom_in.setObjectName("btn_ghost")
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

        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setObjectName("recessed_panel")
        preview_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.preview_scroll = preview_scroll

        preview_container = QWidget()
        preview_container.setProperty("role", "flat")
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setAlignment(Qt.AlignCenter)

        self.lbl_card_preview = QLabel("<i>No generated card to preview</i>")
        self.lbl_card_preview.setAlignment(Qt.AlignCenter)
        self.lbl_card_preview.setStyleSheet(
            f"border: 1px dashed {BORDER_SUBTLE}; border-radius: 6px; padding: 20px; color: {TEXT_MUTED};"
        )
        preview_layout.addWidget(self.lbl_card_preview)
        preview_scroll.setWidget(preview_container)
        card.add(preview_scroll, stretch=1)

        return card

    # -- right column -------------------------------------------------
    def _build_inspector_column(self) -> QWidget:
        """The record editor, the photo override and the approval controls."""
        card = SurfaceCard("Inspector")
        card.setMinimumWidth(280)
        card.setMaximumWidth(420)

        # Navigation stepper.
        self.lbl_nav_index = QLabel("Card 0 of 0")
        self.lbl_nav_index.setProperty("role", "cardTitle")
        card.add(self.lbl_nav_index)

        nav_btns = QHBoxLayout()
        nav_btns.setSpacing(4)
        self.btn_first = QPushButton("⏮")
        self.btn_first.setToolTip("First card")
        self.btn_first.clicked.connect(self._first)
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setToolTip("Previous card")
        self.btn_prev.clicked.connect(self._prev)
        self.btn_next = QPushButton("▶")
        self.btn_next.setToolTip("Next card")
        self.btn_next.clicked.connect(self._next)
        self.btn_last = QPushButton("⏭")
        self.btn_last.setToolTip("Last card")
        self.btn_last.clicked.connect(self._last)

        for button in (self.btn_first, self.btn_prev, self.btn_next, self.btn_last):
            button.setFixedHeight(CONTROL_HEIGHT)
            button.setObjectName("btn_ghost")
            nav_btns.addWidget(button)
        nav_btns.addStretch()
        card.add_layout(nav_btns)

        # Status badge.
        self.lbl_status_badge = QLabel("STATUS: PENDING")
        self.lbl_status_badge.setAlignment(Qt.AlignCenter)
        self.lbl_status_badge.setProperty("role", "badgeAccent")
        card.add(self.lbl_status_badge)

        # Record fields.
        fields_title = QLabel("RECORD FIELDS")
        fields_title.setProperty("role", "sectionLabel")
        card.add(fields_title)

        fields_scroll = QScrollArea()
        fields_scroll.setWidgetResizable(True)
        fields_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        fields_scroll.setMaximumHeight(240)

        self.fields_container = QWidget()
        self.fields_container.setProperty("role", "flat")
        self.fields_layout = QVBoxLayout(self.fields_container)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        self.fields_layout.setSpacing(6)
        fields_scroll.setWidget(self.fields_container)
        card.add(fields_scroll)

        self.lbl_photo_status = QLabel("Photo: -")
        self.lbl_photo_status.setWordWrap(True)
        self.lbl_photo_status.setProperty("role", "specKey")
        card.add(self.lbl_photo_status)

        photo_row = QHBoxLayout()
        photo_row.setSpacing(6)

        self.btn_override_photo = QPushButton("Override photo…")
        self.btn_override_photo.setObjectName("btn_secondary")
        self.btn_override_photo.setFixedHeight(CONTROL_HEIGHT)
        self.btn_override_photo.clicked.connect(self._override_photo)
        photo_row.addWidget(self.btn_override_photo)

        self.btn_apply_fields = QPushButton("Apply & re-render")
        self.btn_apply_fields.setObjectName("btn_secondary")
        self.btn_apply_fields.setFixedHeight(CONTROL_HEIGHT)
        self.btn_apply_fields.clicked.connect(self._apply_field_edits)
        photo_row.addWidget(self.btn_apply_fields)

        photo_row.addStretch()
        card.add_layout(photo_row)

        # Approval controls.
        act_box = QVBoxLayout()
        act_box.setSpacing(8)

        self.btn_approve = QPushButton("✓ Approve Card")
        self.btn_approve.setObjectName("btn_success")
        self.btn_approve.setFixedHeight(CONTROL_HEIGHT)
        self.btn_approve.setStyleSheet("font-weight: 600; padding: 4px 10px;")
        self.btn_approve.clicked.connect(lambda: self._set_current_status(ReviewStatus.APPROVED))
        act_box.addWidget(self.btn_approve)

        self.btn_reject = QPushButton("✗ Reject Card")
        self.btn_reject.setObjectName("btn_danger")
        self.btn_reject.setFixedHeight(CONTROL_HEIGHT)
        self.btn_reject.setStyleSheet("font-weight: 600; padding: 4px 10px;")
        self.btn_reject.clicked.connect(lambda: self._set_current_status(ReviewStatus.REJECTED))
        act_box.addWidget(self.btn_reject)

        self.btn_correction = QPushButton("⚠ Mark for Correction")
        self.btn_correction.setFixedHeight(CONTROL_HEIGHT)
        self.btn_correction.setStyleSheet(
            f"border-color: {SEMANTIC_WARNING}; color: {SEMANTIC_WARNING}; padding: 4px 10px;"
        )
        self.btn_correction.clicked.connect(lambda: self._set_current_status(ReviewStatus.CORRECTION))
        act_box.addWidget(self.btn_correction)

        # The secondary decisions sit in one compact row.
        secondary_row = QHBoxLayout()
        secondary_row.setSpacing(6)

        self.btn_skip = QPushButton("Skip")
        self.btn_skip.setObjectName("btn_secondary")
        self.btn_skip.setFixedHeight(CONTROL_HEIGHT)
        self.btn_skip.clicked.connect(lambda: self._set_current_status(ReviewStatus.SKIPPED))
        secondary_row.addWidget(self.btn_skip)

        self.btn_regen = QPushButton("⟳ Re-render")
        self.btn_regen.setObjectName("btn_secondary")
        self.btn_regen.setFixedHeight(CONTROL_HEIGHT)
        self.btn_regen.clicked.connect(lambda: self._regenerate_current())
        secondary_row.addWidget(self.btn_regen)

        act_box.addLayout(secondary_row)
        card.add_layout(act_box)

        # Record metadata.
        lbl_details_title = QLabel("RECORD METADATA")
        lbl_details_title.setProperty("role", "sectionLabel")
        card.add(lbl_details_title)

        self.lbl_record_details = QLabel("")
        self.lbl_record_details.setWordWrap(True)
        self.lbl_record_details.setProperty("role", "specValue")
        card.add(self.lbl_record_details)

        return card

    # -----------------------------------------------------------------
    # Session
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
        """Initialize sequential review dataset."""
        self.template = template
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

    # -----------------------------------------------------------------
    # Filtering
    # -----------------------------------------------------------------
    def _on_filter_clicked(self, status: Optional[ReviewStatus]) -> None:
        self._current_filter = status
        self.manager.filter_status = status
        self._update_display()

    def _on_quality_filter(self, kind: str) -> None:
        """Filter the record list by the quality of the record."""
        self._quality_filter = kind
        self._update_display()

    def _on_search_changed(self, text: str) -> None:
        self.manager.search_query = text
        self._update_display()

    def _on_record_selected(self, record_id: str) -> None:
        """Jump to the record that was picked in the list."""
        for index, record in enumerate(self.manager.get_filtered_records()):
            if record.record_id == record_id:
                self.manager.current_index = index
                self._update_display()
                return

    # -----------------------------------------------------------------
    # Quality of a record
    # -----------------------------------------------------------------
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
        elif any(
            flag.startswith("Validation error") for flag in flags
        ):
            severity = SEVERITY_ERROR
        elif flags:
            severity = SEVERITY_WARN

        return severity, tuple(flags)

    def _build_entries(self) -> List[RecordListEntry]:
        """Build the rows of the record list."""
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
        """Count the records per quality, ignoring the quality filter itself."""
        counts = {QUALITY_ALL: 0, QUALITY_VALID: 0, QUALITY_WARN: 0, QUALITY_ERROR: 0}
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

    # -----------------------------------------------------------------
    # Display
    # -----------------------------------------------------------------
    def _update_display(self) -> None:
        rec = self.manager.get_current_record()
        filtered = self.manager.get_filtered_records()

        # Update KPI Pills
        c = self.manager.counts
        self.pill_approved.set_status(f"APPROVED: {c['approved']}", color=SEMANTIC_SUCCESS)
        self.pill_pending.set_status(f"PENDING: {c['pending']}", color=SEMANTIC_WARNING)
        self.pill_rejected.set_status(f"REJECTED: {c['rejected']}", color=SEMANTIC_ERROR)
        self.pill_correction.set_status(f"CORRECTION: {c['correction']}", color=PRIMARY)

        self.stat_line.set_stats([
            ("Approved", c["approved"], SEMANTIC_SUCCESS if c["approved"] else None),
            ("Pending", c["pending"], SEMANTIC_WARNING if c["pending"] else None),
            ("Rejected", c["rejected"], SEMANTIC_ERROR if c["rejected"] else None),
            ("Correction", c["correction"], PRIMARY if c["correction"] else None),
        ])

        # Compatibility text
        self.lbl_counts.setText(
            f"Review: {c['approved']} Approved • {c['pending']} Pending • "
            f"{c['rejected']} Rejected • {c['correction']} Correction"
        )

        # The record list.
        entries = self._build_entries()
        self.record_model.set_entries(entries)

        counts = self._quality_counts()
        for kind, button in self.quality_buttons.items():
            caption = {
                QUALITY_ALL: "All",
                QUALITY_VALID: "Valid",
                QUALITY_WARN: "Warn",
                QUALITY_ERROR: "Err",
            }[kind]
            button.setText(f"{caption} ({counts[kind]})")
        self.lbl_list_info.setText(
            f"{len(entries):,} of {len(self.manager.records):,} records shown"
        )

        if not rec or not filtered:
            self.lbl_nav_index.setText("No records match filter")
            self.lbl_card_preview.setPixmap(QPixmap())
            self.lbl_card_preview.setText("<i>No cards to display</i>")
            self.lbl_status_badge.setText("No status")
            self.lbl_record_details.setText(
                "<i>Select or clear filters to view cards.</i>"
            )
            self._clear_field_editors()
            self.lbl_photo_status.setText("Photo: -")
            return

        self.lbl_nav_index.setText(f"Card {self.manager.current_index + 1} of {len(filtered)}")

        # Status badge
        st = rec.status
        self.lbl_status_badge.setText(f"STATUS: {st.value.upper()}")
        if st == ReviewStatus.APPROVED:
            self.lbl_status_badge.setStyleSheet(self._badge_style(SEMANTIC_SUCCESS))
        elif st == ReviewStatus.REJECTED:
            self.lbl_status_badge.setStyleSheet(self._badge_style(SEMANTIC_ERROR))
        elif st == ReviewStatus.CORRECTION:
            self.lbl_status_badge.setStyleSheet(self._badge_style(SEMANTIC_WARNING))
        else:
            self.lbl_status_badge.setStyleSheet(
                f"background-color: {SURFACE_HIGH}; color: {TEXT_PRIMARY}; font-weight: bold; padding: 6px; border-radius: 4px;"
            )

        self._update_preview(rec)
        self._populate_field_editors(rec)
        self._update_metadata(rec)

        # Keep the selection of the list in sync with the current record.
        row = self.record_model.row_for_record(rec.record_id)
        if row >= 0:
            index = self.record_model.index(row, 0)
            self.record_list.setCurrentIndex(index)

    @staticmethod
    def _badge_style(color: str) -> str:
        """A soft badge around a semantic colour."""
        tint = QColor(color)
        return (
            f"background-color: rgba({tint.red()}, {tint.green()}, {tint.blue()}, 48);"
            f" border: 1px solid {color}; color: {color};"
            f" font-weight: bold; padding: 6px; border-radius: 4px;"
        )

    # -- preview ------------------------------------------------------
    def _update_preview(self, rec: ReviewRecord) -> None:
        """Show the card of the current record."""
        if self._side == "back":
            self._render_back_side(rec)
            return

        if rec.rendered_image_path and Path(rec.rendered_image_path).exists():
            pix = QPixmap(rec.rendered_image_path)
            if not pix.isNull():
                self._show_pixmap(pix)
                self.lbl_preview_meta.setText(
                    f"{Path(rec.rendered_image_path).name}"
                )
                return
            self.lbl_card_preview.setPixmap(QPixmap())
            self.lbl_card_preview.setText("Failed to load image preview")
            return

        self.lbl_card_preview.setPixmap(QPixmap())
        self.lbl_card_preview.setText(
            f"Card image missing on disk:\n{rec.rendered_image_path or 'not rendered'}"
        )

    def _render_back_side(self, rec: ReviewRecord) -> None:
        """Render the back face of the current record on demand."""
        if not self.template:
            self.lbl_card_preview.setPixmap(QPixmap())
            self.lbl_card_preview.setText("<i>No template to render the back side</i>")
            return

        source = self.source_records_map.get(rec.record_id)
        match = self.match_results_map.get(rec.record_id)
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
        rec = self.manager.get_current_record()
        if rec:
            self._update_preview(rec)
        else:
            self.lbl_zoom.setText(f"{int(self._zoom * 100)}%")

    def _fit_preview(self) -> None:
        """Fit the card into the viewport."""
        rec = self.manager.get_current_record()
        if not rec:
            return
        self._zoom = 1.0
        self._update_preview(rec)

    def _on_side_changed(self, side: str) -> None:
        """Flip the card between the front and the back face."""
        self._side = side
        rec = self.manager.get_current_record()
        if rec:
            self._update_preview(rec)

    # -- field editor -------------------------------------------------
    def _clear_field_editors(self) -> None:
        """Remove the editors of the previous record."""
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._field_editors.clear()

    def _populate_field_editors(self, rec: ReviewRecord) -> None:
        """Build the editors for the fields of the current record."""
        self._clear_field_editors()

        source = self.source_records_map.get(rec.record_id)
        if source is None:
            return

        for key, value in list(source.data.items())[:MAX_EDITED_FIELDS]:
            row = QWidget()
            row.setProperty("role", "flat")
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)

            caption = QLabel(str(key))
            caption.setProperty("role", "specKey")
            row_layout.addWidget(caption)

            editor = QLineEdit("" if value is None else str(value))
            editor.setProperty("role", "fieldFlat")
            row_layout.addWidget(editor)

            self._field_editors[str(key)] = editor
            self.fields_layout.addWidget(row)

        if not self._field_editors:
            hint = QLabel("This record has no mapped fields.")
            hint.setProperty("role", "specKey")
            self.fields_layout.addWidget(hint)

    def _apply_field_edits(self) -> None:
        """Write the edited values back and re-render the card."""
        rec = self.manager.get_current_record()
        if not rec:
            return

        source = self.source_records_map.get(rec.record_id)
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
        rec = self.manager.get_current_record()
        if not rec:
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a photograph",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not path:
            return

        self.match_results_map[rec.record_id] = PhotoMatchResult(
            pin=rec.pin,
            record_id=rec.record_id,
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

    # -- metadata -----------------------------------------------------
    def _update_metadata(self, rec: ReviewRecord) -> None:
        """Show the metadata of the current record."""
        src_rec = self.source_records_map.get(rec.record_id)
        match_res = self.match_results_map.get(rec.record_id)

        lines = [
            f"<b>PIN:</b> {rec.pin or '(None)'}",
            f"<b>Source ID:</b> {rec.record_id}",
        ]
        if src_rec:
            lines.append(f"<b>Row:</b> {src_rec.row_index + 1}")

        if match_res:
            lines.append("<hr>")
            status_color = (
                SEMANTIC_SUCCESS
                if match_res.status in (MatchStatus.MATCHED, MatchStatus.OVERRIDDEN)
                else SEMANTIC_ERROR
            )
            lines.append(
                f"<b>Photo Match:</b> <font color='{status_color}'>{match_res.status.value.upper()}</font>"
            )
            if match_res.photo_path:
                lines.append(f"<b>File:</b> {Path(match_res.photo_path).name}")

        self.lbl_record_details.setText("<br>".join(lines))

        if match_res:
            if match_res.status in (MatchStatus.MATCHED, MatchStatus.OVERRIDDEN):
                self.lbl_photo_status.setText(
                    f"Photo: {match_res.status.value} · {Path(match_res.photo_path or '').name or '-'}"
                )
            else:
                self.lbl_photo_status.setText(
                    f"Photo: {match_res.status.value} · fallback used"
                )
        else:
            self.lbl_photo_status.setText("Photo: not matched")

    # -----------------------------------------------------------------
    # Decisions
    # -----------------------------------------------------------------
    def _set_current_status(self, status: ReviewStatus) -> None:
        rec = self.manager.get_current_record()
        if not rec:
            return
        self.manager.update_status(rec.record_id, status)
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
        rec = self.manager.get_current_record()
        if not rec or not self.template:
            return
        src_rec = self.source_records_map.get(rec.record_id)
        if not src_rec:
            return

        match_res = self.match_results_map.get(rec.record_id)
        photo_path = match_res.photo_path if match_res else None

        try:
            # Re-render through the batch generator so the card is written
            # to the staging folder exactly like during the batch run.
            res = BatchGenerator.generate_single_card(
                template=self.template,
                record=src_rec,
                match_result=match_res,
                column_mappings=self.column_mappings,
                settings=self.settings,
                target_dir=get_staging_dir(),
            )
            if res.success and res.image_path:
                rec.rendered_image_path = str(res.image_path)
                self.render_results_map[rec.record_id] = res
                self.manager.update_status(rec.record_id, ReviewStatus.PENDING)
                self.review_updated.emit(self.manager)
                self._update_display()
                if not keep_notice:
                    self.notice.set_message(
                        f"Re-rendered the card for PIN {rec.pin}.", severity="success"
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
