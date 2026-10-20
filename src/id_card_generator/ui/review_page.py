"""Sequential card review and approval workstation suite.

Revamped per Stitch screen 6a3b4424b3f2:
- Top metrics ribbon with StatusPill counts and filter tabs (All, Pending, Approved, Rejected, Correction).
- Central viewport with high-resolution card preview and zoom navigation.
- Right inspector with record details, photo match status, and one-click approval buttons.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import MatchStatus, ReviewStatus, WorkflowStep
from id_card_generator.core.models import (
    RenderSettings,
    PhotoMatchResult,
    RenderResult,
    ReviewRecord,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.generation.batch_generator import BatchGenerator
from id_card_generator.resources.resource_loader import get_staging_dir
from id_card_generator.review.review_manager import ReviewManager
from id_card_generator.ui.components.status_pill import StatusPill
from id_card_generator.ui import workflow
from id_card_generator.ui.components.layout_blocks import StatLine
from id_card_generator.ui.components.page_scaffold import InlineNotice, PageFooter, PageHeader
from id_card_generator.ui.studio_tokens import SIZES
from id_card_generator.ui.studio_tokens import (
    BORDER_DEFAULT,
    BORDER_SUBTLE,
    FONT_FAMILY_MONO,
    FONT_FAMILY_UI,
    PRIMARY,
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

# Every control in a toolbar row uses the same height.
CONTROL_HEIGHT = SIZES.CONTROL_HEIGHT


class ReviewPage(QWidget):
    """Sequential review interface ensuring cards are inspected and explicitly approved."""

    review_updated = Signal(object)  # ReviewManager
    goto_export_requested = Signal()
    navigate_requested = Signal(str)  # WorkflowStep value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = ReviewManager()
        self.template: Optional[TemplateDefinition] = None
        self.source_records_map: Dict[str, SourceRecord] = {}
        self.match_results_map: Dict[str, PhotoMatchResult] = {}
        self.settings = RenderSettings()
        self.column_mappings: Dict[str, str] = {}
        self._current_filter: Optional[ReviewStatus] = None

        self._setup_ui()

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
        # 1. Top Ribbon: Status metrics, Filter buttons, Batch actions
        # ---------------------------------------------------------
        top_card = QFrame()
        top_card.setObjectName("card_panel")
        top_card.setObjectName("workspace_panel")
        top_layout = QVBoxLayout(top_card)
        top_layout.setContentsMargins(8, 8, 8, 8)
        top_layout.setSpacing(8)

        # Row 1: Status Pills + Actions
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

        # Row 2: Status Filter Segmented Controls
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        lbl_filt = QLabel("Show:")
        lbl_filt.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
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
            btn.setFixedHeight(24)
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {SURFACE_LOWEST}; border: 1px solid {BORDER_SUBTLE}; color: {TEXT_SECONDARY}; font-size: 11px; padding: 4px 10px; border-radius: 3px; }}"
                f"QPushButton:checked {{ background-color: {SURFACE_HIGH}; border: 1px solid {PRIMARY}; color: {PRIMARY}; font-weight: 600; }}"
            )
            if fid == "all":
                btn.setChecked(True)
            btn.clicked.connect(lambda chk, v=fval: self._on_filter_clicked(v))
            self.filter_group.addButton(btn)
            row2.addWidget(btn)

        row2.addStretch()
        top_layout.addLayout(row2)

        body.addWidget(top_card)

        # ---------------------------------------------------------
        # 2. Main Workstation Splitter (Preview Center, Inspector Right)
        # ---------------------------------------------------------
        splitter = QSplitter(Qt.Horizontal)

        # Card Preview Container
        preview_panel = QFrame()
        preview_panel.setObjectName("recessed_panel")
        prev_panel_layout = QVBoxLayout(preview_panel)
        prev_panel_layout.setContentsMargins(12, 12, 12, 12)

        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        preview_container = QWidget()
        preview_container.setStyleSheet("background: transparent;")
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setAlignment(Qt.AlignCenter)

        self.lbl_card_preview = QLabel("<i>No generated card to preview</i>")
        self.lbl_card_preview.setAlignment(Qt.AlignCenter)
        self.lbl_card_preview.setStyleSheet(
            f"border: 1px dashed {BORDER_SUBTLE}; border-radius: 6px; padding: 20px; color: {TEXT_MUTED};"
        )
        preview_layout.addWidget(self.lbl_card_preview)
        preview_scroll.setWidget(preview_container)
        prev_panel_layout.addWidget(preview_scroll)

        splitter.addWidget(preview_panel)

        # Right Inspector & Navigation Card
        right_panel = QFrame()
        right_panel.setObjectName("card_panel")
        right_panel.setObjectName("workspace_panel")
        right_panel.setMinimumWidth(320)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(10)

        # Navigation Stepper Box
        nav_box = QVBoxLayout()
        self.lbl_nav_index = QLabel("Card 0 of 0")
        self.lbl_nav_index.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {TEXT_PRIMARY}; font-family: {FONT_FAMILY_MONO};")
        nav_box.addWidget(self.lbl_nav_index)

        nav_btns = QHBoxLayout()
        nav_btns.setSpacing(4)
        self.btn_first = QPushButton("⏮ First")
        self.btn_first.clicked.connect(self._first)
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.clicked.connect(self._prev)
        self.btn_next = QPushButton("Next ▶")
        self.btn_next.clicked.connect(self._next)
        self.btn_last = QPushButton("Last ⏭")
        self.btn_last.clicked.connect(self._last)

        for b in [self.btn_first, self.btn_prev, self.btn_next, self.btn_last]:
            b.setFixedHeight(26)
            nav_btns.addWidget(b)
        nav_box.addLayout(nav_btns)
        right_layout.addLayout(nav_box)

        # Filter & Search
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter cards by PIN or Name...")
        self.txt_search.textChanged.connect(self._on_search_changed)
        self.txt_search.setStyleSheet(
            f"background-color: {SURFACE_LOWEST}; border: 1px solid {BORDER_SUBTLE}; color: {TEXT_PRIMARY}; border-radius: 4px; padding: 4px 8px; font-size: 11px;"
        )
        right_layout.addWidget(self.txt_search)

        # Status Badge
        self.lbl_status_badge = QLabel("STATUS: PENDING")
        self.lbl_status_badge.setStyleSheet(
            f"background-color: {SURFACE_HIGH}; color: {TEXT_PRIMARY}; font-weight: bold; padding: 6px; border-radius: 4px; font-family: {FONT_FAMILY_MONO};"
        )
        self.lbl_status_badge.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.lbl_status_badge)

        # Individual Approval Action Buttons
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
        self.btn_correction.setStyleSheet(f"border-color: {SEMANTIC_WARNING}; color: {SEMANTIC_WARNING}; padding: 4px 10px;")
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
        self.btn_regen.clicked.connect(self._regenerate_current)
        secondary_row.addWidget(self.btn_regen)

        act_box.addLayout(secondary_row)

        right_layout.addLayout(act_box)

        # Record Details Display
        lbl_details_title = QLabel("<b>RECORD METADATA</b>")
        lbl_details_title.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 0.5px;")
        right_layout.addWidget(lbl_details_title)

        self.lbl_record_details = QLabel("")
        self.lbl_record_details.setWordWrap(True)
        self.lbl_record_details.setStyleSheet(
            f"background-color: {SURFACE_LOWEST}; border: 1px solid {BORDER_SUBTLE}; border-radius: 4px; padding: 8px; color: {TEXT_SECONDARY}; font-size: 11px; line-height: 1.4;"
        )
        right_layout.addWidget(self.lbl_record_details)

        right_layout.addStretch()
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        body.addWidget(splitter, stretch=1)

        # ---------------------------------------------------------
        # 3. Bottom Step Navigation Bar (Preserved for compatibility)
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

        self.manager.initialize_from_generation(
            source_records=source_records,
            generation_results=generation_results,
            saved_states=saved_states,
        )
        self._update_display()

    def _on_filter_clicked(self, status: Optional[ReviewStatus]) -> None:
        self._current_filter = status
        self.manager.filter_status = status
        self._update_display()

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

        if not rec or not filtered:
            self.lbl_nav_index.setText("No records match filter")
            self.lbl_card_preview.setText("<i>No cards to display</i>")
            self.lbl_status_badge.setText("No status")
            self.lbl_status_badge.setStyleSheet(f"background-color: {SURFACE_HIGH}; color: {TEXT_MUTED}; padding: 6px; border-radius: 4px;")
            self.lbl_record_details.setText("<i>Select or clear filters to view cards.</i>")
            return

        self.lbl_nav_index.setText(f"Card {self.manager.current_index + 1} of {len(filtered)}")

        # Status badge
        st = rec.status
        self.lbl_status_badge.setText(f"STATUS: {st.value.upper()}")
        if st == ReviewStatus.APPROVED:
            self.lbl_status_badge.setStyleSheet(f"background-color: #064E3B; border: 1px solid {SEMANTIC_SUCCESS}; color: {SEMANTIC_SUCCESS}; font-weight: bold; padding: 6px; border-radius: 4px;")
        elif st == ReviewStatus.REJECTED:
            self.lbl_status_badge.setStyleSheet(f"background-color: #7F1D1D; border: 1px solid {SEMANTIC_ERROR}; color: {SEMANTIC_ERROR}; font-weight: bold; padding: 6px; border-radius: 4px;")
        elif st == ReviewStatus.CORRECTION:
            self.lbl_status_badge.setStyleSheet(f"background-color: #78350F; border: 1px solid {SEMANTIC_WARNING}; color: {SEMANTIC_WARNING}; font-weight: bold; padding: 6px; border-radius: 4px;")
        else:
            self.lbl_status_badge.setStyleSheet(f"background-color: {SURFACE_HIGH}; border: 1px solid {BORDER_SUBTLE}; color: {TEXT_PRIMARY}; font-weight: bold; padding: 6px; border-radius: 4px;")

        # Card Image Preview
        if rec.rendered_image_path and Path(rec.rendered_image_path).exists():
            pix = QPixmap(rec.rendered_image_path)
            if not pix.isNull():
                scaled = pix.scaled(440, 680, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.lbl_card_preview.setPixmap(scaled)
            else:
                self.lbl_card_preview.setText("Failed to load image preview")
        else:
            self.lbl_card_preview.setText(f"Card image missing on disk:\n{rec.rendered_image_path}")

        # Record Details
        src_rec = self.source_records_map.get(rec.record_id)
        match_res = self.match_results_map.get(rec.record_id)

        lines = [
            f"<b>PIN:</b> {rec.pin or '(None)'}",
            f"<b>Source ID:</b> {rec.record_id}",
        ]
        if src_rec:
            for k, v in list(src_rec.data.items())[:6]:
                lines.append(f"<b>{k}:</b> {v or '-'}")

        if match_res:
            lines.append("<hr>")
            status_color = (
                SEMANTIC_SUCCESS
                if match_res.status in (MatchStatus.MATCHED, MatchStatus.OVERRIDDEN)
                else SEMANTIC_ERROR
            )
            lines.append(f"<b>Photo Match:</b> <font color='{status_color}'>{match_res.status.value.upper()}</font>")
            if match_res.photo_path:
                lines.append(f"<b>File:</b> {Path(match_res.photo_path).name}")

        self.lbl_record_details.setText("<br>".join(lines))

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

    def _regenerate_current(self) -> None:
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
                self.manager.update_status(rec.record_id, ReviewStatus.PENDING)
                self.review_updated.emit(self.manager)
                self._update_display()
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

    def _on_search_changed(self, text: str) -> None:
        self.manager.search_query = text
        self._update_display()

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
