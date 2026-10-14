"""Sequential card review and approval workspace."""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import ReviewStatus
from id_card_generator.core.models import (
    PhotoMatchResult,
    RenderResult,
    ReviewRecord,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.generation.batch_generator import BatchGenerator
from id_card_generator.rendering.pillow_renderer import PillowRenderer
from id_card_generator.review.review_manager import ReviewManager

logger = logging.getLogger(__name__)


class ReviewPage(QWidget):
    """Sequential review interface ensuring cards are inspected and explicitly approved."""

    review_updated = Signal(object)  # ReviewManager
    goto_export_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = ReviewManager()
        self.template: Optional[TemplateDefinition] = None
        self.source_records_map: Dict[str, SourceRecord] = {}
        self.match_results_map: Dict[str, PhotoMatchResult] = {}
        self.column_mappings: Dict[str, str] = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Top Bar: Status metrics & Batch actions
        top_bar = QHBoxLayout()
        self.lbl_counts = QLabel("Review: 0 Approved • 0 Pending • 0 Rejected")
        self.lbl_counts.setStyleSheet("font-size: 14px; font-weight: bold; color: #38BDF8;")
        top_bar.addWidget(self.lbl_counts)
        top_bar.addStretch()

        self.btn_batch_approve = QPushButton("Approve All Valid Cards")
        self.btn_batch_approve.setObjectName("btn_success")
        self.btn_batch_approve.clicked.connect(self._batch_approve)
        top_bar.addWidget(self.btn_batch_approve)

        self.btn_goto_export = QPushButton("Proceed to Final Export ▶")
        self.btn_goto_export.setObjectName("btn_primary")
        self.btn_goto_export.clicked.connect(lambda: self.goto_export_requested.emit())
        top_bar.addWidget(self.btn_goto_export)
        layout.addLayout(top_bar)

        # Main Splitter: Large Preview in center, Sidebar controls & metadata on right
        splitter = QSplitter(Qt.Horizontal)

        # Card Preview Container
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setAlignment(Qt.AlignCenter)

        self.lbl_card_preview = QLabel("<i>No generated card to preview</i>")
        self.lbl_card_preview.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(self.lbl_card_preview)
        preview_scroll.setWidget(preview_container)
        splitter.addWidget(preview_scroll)

        # Right Inspector & Navigation Card
        right_panel = QFrame()
        right_panel.setObjectName("card_panel")
        right_panel.setMinimumWidth(320)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(12)

        # Navigation Bar
        nav_box = QVBoxLayout()
        self.lbl_nav_index = QLabel("Card 0 of 0")
        self.lbl_nav_index.setStyleSheet("font-weight: bold; font-size: 15px;")
        nav_box.addWidget(self.lbl_nav_index)

        nav_btns = QHBoxLayout()
        self.btn_first = QPushButton("⏮ First")
        self.btn_first.clicked.connect(self._first)
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.clicked.connect(self._prev)
        self.btn_next = QPushButton("Next ▶")
        self.btn_next.clicked.connect(self._next)
        self.btn_last = QPushButton("Last ⏭")
        self.btn_last.clicked.connect(self._last)

        nav_btns.addWidget(self.btn_first)
        nav_btns.addWidget(self.btn_prev)
        nav_btns.addWidget(self.btn_next)
        nav_btns.addWidget(self.btn_last)
        nav_box.addLayout(nav_btns)
        right_layout.addLayout(nav_box)

        # Filter & Search
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter by PIN or Name...")
        self.txt_search.textChanged.connect(self._on_search_changed)
        right_layout.addWidget(self.txt_search)

        # Status Badge
        self.lbl_status_badge = QLabel("STATUS: PENDING")
        self.lbl_status_badge.setStyleSheet(
            "background-color: #334155; color: #FFFFFF; font-weight: bold; padding: 6px; border-radius: 4px;"
        )
        self.lbl_status_badge.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.lbl_status_badge)

        # Individual Approval Action Buttons
        act_box = QVBoxLayout()
        self.btn_approve = QPushButton("✓ Approve Card")
        self.btn_approve.setObjectName("btn_success")
        self.btn_approve.clicked.connect(lambda: self._set_current_status(ReviewStatus.APPROVED))
        act_box.addWidget(self.btn_approve)

        self.btn_reject = QPushButton("✗ Reject Card")
        self.btn_reject.setObjectName("btn_danger")
        self.btn_reject.clicked.connect(lambda: self._set_current_status(ReviewStatus.REJECTED))
        act_box.addWidget(self.btn_reject)

        self.btn_correction = QPushButton("⚠ Mark for Correction")
        self.btn_correction.clicked.connect(lambda: self._set_current_status(ReviewStatus.CORRECTION))
        act_box.addWidget(self.btn_correction)

        self.btn_skip = QPushButton("Skip Card")
        self.btn_skip.clicked.connect(lambda: self._set_current_status(ReviewStatus.SKIPPED))
        act_box.addWidget(self.btn_skip)

        self.btn_regen = QPushButton("⟳ Regenerate Card")
        self.btn_regen.clicked.connect(self._regenerate_current)
        act_box.addWidget(self.btn_regen)

        right_layout.addLayout(act_box)

        # Record Details
        self.lbl_record_details = QLabel("")
        self.lbl_record_details.setWordWrap(True)
        self.lbl_record_details.setStyleSheet("color: #94A3B8; font-size: 12px;")
        right_layout.addWidget(self.lbl_record_details)

        right_layout.addStretch()
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

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

    def _update_display(self) -> None:
        rec = self.manager.get_current_record()
        filtered = self.manager.get_filtered_records()

        # Update KPI
        c = self.manager.counts
        self.lbl_counts.setText(
            f"Review: {c['approved']} Approved • {c['pending']} Pending • "
            f"{c['rejected']} Rejected • {c['correction']} Correction"
        )

        if not rec or not filtered:
            self.lbl_nav_index.setText("No records match filter")
            self.lbl_card_preview.setText("<i>No cards to display</i>")
            self.lbl_status_badge.setText("STATUS: NONE")
            self.lbl_record_details.setText("")
            return

        self.lbl_nav_index.setText(f"Card {self.manager.current_index + 1} of {len(filtered)}")

        # Status badge
        st = rec.status
        self.lbl_status_badge.setText(f"STATUS: {st.value.upper()}")
        if st == ReviewStatus.APPROVED:
            self.lbl_status_badge.setStyleSheet("background-color: #059669; color: #FFFFFF; font-weight: bold; padding: 6px; border-radius: 4px;")
        elif st == ReviewStatus.REJECTED:
            self.lbl_status_badge.setStyleSheet("background-color: #DC2626; color: #FFFFFF; font-weight: bold; padding: 6px; border-radius: 4px;")
        elif st == ReviewStatus.CORRECTION:
            self.lbl_status_badge.setStyleSheet("background-color: #D97706; color: #FFFFFF; font-weight: bold; padding: 6px; border-radius: 4px;")
        else:
            self.lbl_status_badge.setStyleSheet("background-color: #334155; color: #FFFFFF; font-weight: bold; padding: 6px; border-radius: 4px;")

        # Card Image Preview
        if rec.rendered_image_path and Path(rec.rendered_image_path).exists():
            pix = QPixmap(rec.rendered_image_path)
            if not pix.isNull():
                # Scale preview to fit comfortably
                scaled = pix.scaled(400, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.lbl_card_preview.setPixmap(scaled)
            else:
                self.lbl_card_preview.setText("Failed to load image preview")
        else:
            self.lbl_card_preview.setText("Card image not generated")

        # Record Details
        src_rec = self.source_records_map.get(rec.record_id)
        match_res = self.match_results_map.get(rec.record_id)
        details = [
            f"<b>PIN:</b> {rec.pin}",
            f"<b>Name:</b> {rec.name}",
        ]
        if src_rec:
            details.extend([
                f"<b>Designation:</b> {src_rec.get_value('Designation')}",
                f"<b>Office:</b> {src_rec.get_value('Office Name')}",
                f"<b>Constituency:</b> {src_rec.get_value('Constituency')}",
                f"<b>Source PDF:</b> {src_rec.get_value('Source PDF')}",
            ])
        if match_res:
            details.append(f"<b>Photo Match:</b> {match_res.status.value} ({Path(match_res.photo_path).name if match_res.photo_path else 'None'})")

        self.lbl_record_details.setText("<br>".join(details))

    def _next(self) -> None:
        self.manager.next_record()
        self._update_display()

    def _prev(self) -> None:
        self.manager.prev_record()
        self._update_display()

    def _first(self) -> None:
        self.manager.first_record()
        self._update_display()

    def _last(self) -> None:
        self.manager.last_record()
        self._update_display()

    def _set_current_status(self, status: ReviewStatus) -> None:
        rec = self.manager.get_current_record()
        if rec:
            self.manager.update_status(rec.record_id, status)
            self.review_updated.emit(self.manager)
            # Advance to next automatically for fluid review
            self.manager.next_record()
            self._update_display()

    def _regenerate_current(self) -> None:
        rec = self.manager.get_current_record()
        if not rec or not self.template:
            return

        src_rec = self.source_records_map.get(rec.record_id)
        if not src_rec:
            return

        match_res = self.match_results_map.get(rec.record_id)

        # Invalidate approval
        self.manager.invalidate_approval(rec.record_id)

        # Regenerate card
        from id_card_generator.resources.resource_loader import get_staging_dir
        res = BatchGenerator.generate_single_card(
            template=self.template,
            record=src_rec,
            match_result=match_res,
            column_mappings=self.column_mappings,
            settings=None,
            target_dir=get_staging_dir(),
        )

        if res.success:
            rec.rendered_image_path = res.image_path
            QMessageBox.information(self, "Regenerated", f"Card for PIN '{rec.pin}' regenerated successfully.")
        else:
            QMessageBox.warning(self, "Regeneration Error", f"Failed to regenerate: {res.error_message}")

        self._update_display()

    def _batch_approve(self) -> None:
        count = self.manager.batch_approve_all_valid()
        self.review_updated.emit(self.manager)
        self._update_display()
        QMessageBox.information(self, "Batch Approved", f"Approved {count} valid ID cards.")

    def _on_search_changed(self, text: str) -> None:
        self.manager.search_query = text
        self.manager.current_index = 0
        self._update_display()
