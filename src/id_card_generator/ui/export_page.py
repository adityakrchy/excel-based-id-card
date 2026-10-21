"""Final export configuration and batch execution for individual ID cards.

The export writes **one file per card**.  The left pane previews the actual
card that will be written (and lists the files that are about to be
produced), the right pane holds the real export settings:

* output destination,
* image format and JPEG quality,
* the file name pattern with a live example,
* which cards are included (approved only),
* optional audit artifacts (CSV manifest, printable contact sheet).
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PIL import Image
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QLayout,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import OutputFormat, ReviewStatus, WorkflowStep
from id_card_generator.core.models import (
    ExportConfiguration,
    ExportResult,
    PhotoMatchResult,
    ReviewRecord,
    SourceRecord,
)
from id_card_generator.export.export_manager import ExportManager
from id_card_generator.ui.components.status_pill import StatusPill
from id_card_generator.ui import workflow
from id_card_generator.ui.components.page_scaffold import InlineNotice, PageFooter, PageHeader
from id_card_generator.ui.studio_tokens import SIZES
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

# Every control in a toolbar row uses the same height.
CONTROL_HEIGHT = SIZES.CONTROL_HEIGHT


class CardPreviewWidget(QWidget):
    """Preview of the individual card that is about to be exported."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_path: Optional[str] = None
        self.caption: str = ""
        self.sub_caption: str = ""
        self.setMinimumSize(320, 360)

    def set_card(self, image_path: Optional[str], caption: str = "", sub_caption: str = "") -> None:
        """Show a card image with its caption."""
        self.image_path = image_path
        self.caption = caption
        self.sub_caption = sub_caption
        if sub_caption and image_path:
            self.sub_caption = f"{sub_caption} · {self._describe(image_path)}"
        self.update()

    @staticmethod
    def _describe(image_path: str) -> str:
        """Describe the card: pixel size, DPI and the physical size."""
        try:
            with Image.open(image_path) as image:
                width, height = image.size
                dpi = image.info.get("dpi", (300, 300))
        except Exception:
            return ""

        try:
            dpi_x = float(dpi[0]) or 300.0
        except (TypeError, ValueError, IndexError):
            dpi_x = 300.0

        mm_w = width / dpi_x * 25.4
        mm_h = height / dpi_x * 25.4
        return f"{width} × {height} px · {dpi_x:.0f} DPI · {mm_w:.1f} × {mm_h:.1f} mm"

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(SURFACE_LOWEST))

        if not self.image_path or not Path(self.image_path).exists():
            self._paint_placeholder(painter, w, h)
            return

        pixmap = QPixmap(self.image_path)
        if pixmap.isNull():
            self._paint_placeholder(painter, w, h)
            return

        avail_w = w - 48
        avail_h = h - 48 - 54
        scaled = pixmap.scaled(
            QSize(max(1, avail_w), max(1, avail_h)),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        card_x = (w - scaled.width()) / 2.0
        card_y = 24
        card_rect = QRectF(card_x, card_y, scaled.width(), scaled.height())

        # Drop shadow
        painter.fillRect(card_rect.translated(3, 4), QColor(0, 0, 0, 110))
        painter.drawPixmap(int(card_x), int(card_y), scaled)
        painter.setPen(QPen(QColor(BORDER_DEFAULT), 1.0))
        painter.drawRect(card_rect)

        # Caption below the card
        caption_y = card_y + scaled.height() + 22
        font = painter.font()
        font.setPointSize(9)
        font.setFamily(FONT_FAMILY_MONO)
        painter.setFont(font)
        painter.setPen(QPen(QColor(TEXT_PRIMARY)))
        painter.drawText(
            QRectF(24, caption_y, w - 48, 18),
            Qt.AlignHCenter | Qt.AlignTop,
            self.caption,
        )
        if self.sub_caption:
            painter.setPen(QPen(QColor(TEXT_MUTED)))
            painter.drawText(
                QRectF(24, caption_y + 20, w - 48, 18),
                Qt.AlignHCenter | Qt.AlignTop,
                self.sub_caption,
            )

    def _paint_placeholder(self, painter: QPainter, w: int, h: int) -> None:
        """Draw the empty state when no card is available yet."""
        rect = QRectF(40, 40, max(1, w - 80), max(1, h - 120))
        painter.setPen(QPen(QColor(BORDER_SUBTLE), 1.0, Qt.DashLine))
        painter.drawRoundedRect(rect, 8, 8)

        font = painter.font()
        font.setPointSize(10)
        font.setFamily(FONT_FAMILY_UI)
        painter.setFont(font)
        painter.setPen(QPen(QColor(TEXT_MUTED)))
        painter.drawText(
            rect,
            Qt.AlignCenter,
            "No card selected\nApprove a card in the review step to preview it here.",
        )


class ExportFileListWidget(QScrollArea):
    """List of the files the export is going to write."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("background: transparent; border: none;")

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        # The scroll area must not squeeze the rows into each other.
        self._layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.setWidget(self._container)

    def set_entries(self, entries: List[str]) -> None:
        """Replace the list with the given file names."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Detach it right away - deleteLater would keep it visible
                # until the event loop runs.
                widget.setParent(None)
                widget.deleteLater()

        for name in entries:
            label = QLabel(name)
            label.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-family: {FONT_FAMILY_MONO}; font-size: 11px;"
            )
            label.setToolTip(name)
            self._layout.addWidget(label)

        if not entries:
            label = QLabel("No cards to export yet.")
            label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            self._layout.addWidget(label)

        self._layout.addStretch(1)


class ExportPage(QWidget):
    """Configures the export of individual cards, runs it, and reports the result."""

    export_completed = Signal(object)  # ExportResult
    navigate_requested = Signal(str)  # WorkflowStep value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.review_records: List[ReviewRecord] = []
        self.source_records_map: Dict[str, SourceRecord] = {}
        self.match_results_map: Dict[str, PhotoMatchResult] = {}
        self.last_export_dir: Optional[Path] = None

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---------------------------------------------------------
        # Page header (step badge, title, subtitle)
        # ---------------------------------------------------------
        badge, title, subtitle = workflow.page_header_text(WorkflowStep.EXPORT)
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
        # 1. Top status ribbon
        # ---------------------------------------------------------
        top_ribbon = QFrame()
        top_ribbon.setObjectName("workspace_panel")
        ribbon_layout = QHBoxLayout(top_ribbon)
        ribbon_layout.setContentsMargins(8, 8, 8, 8)
        ribbon_layout.setSpacing(8)

        lbl_icon = QLabel("💾")
        lbl_icon.setStyleSheet("font-size: 16px;")
        ribbon_layout.addWidget(lbl_icon)

        self.pill_output = StatusPill("INDIVIDUAL CARD FILES", color=PRIMARY)
        self.pill_format = StatusPill("PNG · LOSSLESS", color=PRIMARY_LIGHT)
        self.pill_preflight = StatusPill("PREFLIGHT: NOT RUN", color=SEMANTIC_WARNING)

        ribbon_layout.addWidget(self.pill_output)
        ribbon_layout.addWidget(self.pill_format)
        ribbon_layout.addWidget(self.pill_preflight)
        ribbon_layout.addStretch()

        self.btn_run_preflight = QPushButton("⚡ Verify Preflight")
        self.btn_run_preflight.setFixedHeight(CONTROL_HEIGHT)
        self.btn_run_preflight.clicked.connect(self._verify_preflight)
        ribbon_layout.addWidget(self.btn_run_preflight)

        body.addWidget(top_ribbon)

        # ---------------------------------------------------------
        # 2. Main splitter (card preview left, settings right)
        # ---------------------------------------------------------
        splitter = QSplitter(Qt.Horizontal)

        # --- LEFT: the card that will be written + the file list ---
        left_panel = QFrame()
        left_panel.setObjectName("workspace_panel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        lbl_preview_head = QLabel("<b>CARD PREVIEW</b>")
        lbl_preview_head.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 0.5px;"
        )
        left_layout.addWidget(lbl_preview_head)

        self.card_preview = CardPreviewWidget()
        left_layout.addWidget(self.card_preview, stretch=1)

        lbl_files_head = QLabel("<b>FILES TO BE WRITTEN</b>")
        lbl_files_head.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 0.5px;"
        )
        left_layout.addWidget(lbl_files_head)

        self.file_list = ExportFileListWidget()
        self.file_list.setMaximumHeight(150)
        left_layout.addWidget(self.file_list)

        splitter.addWidget(left_panel)

        # --- RIGHT: the export settings ---
        right_panel = QFrame()
        right_panel.setObjectName("workspace_panel")
        right_panel.setMinimumWidth(340)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(10)

        # Output Destination
        lbl_dest_head = QLabel("<b>OUTPUT DESTINATION</b>")
        lbl_dest_head.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 0.5px;"
        )
        right_layout.addWidget(lbl_dest_head)

        dest_row = QHBoxLayout()
        self.btn_browse_dest = QPushButton("Select Folder...")
        self.btn_browse_dest.setObjectName("btn_primary")
        self.btn_browse_dest.setFixedHeight(CONTROL_HEIGHT)
        self.btn_browse_dest.clicked.connect(self._browse_destination)
        dest_row.addWidget(self.btn_browse_dest)

        self.lbl_dest_dir = QLabel("<i>No output directory selected</i>")
        self.lbl_dest_dir.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-family: {FONT_FAMILY_MONO}; font-size: 11px;"
        )
        dest_row.addWidget(self.lbl_dest_dir, stretch=1)
        right_layout.addLayout(dest_row)

        # Card settings
        lbl_fmt_head = QLabel("<b>CARD SETTINGS</b>")
        lbl_fmt_head.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 0.5px;"
        )
        right_layout.addWidget(lbl_fmt_head)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Format:"))
        self.cmb_format = QComboBox()
        self.cmb_format.addItem("PNG (lossless)", "png")
        self.cmb_format.addItem("JPEG (compressed)", "jpeg")
        self.cmb_format.currentIndexChanged.connect(self._on_format_changed)
        fmt_row.addWidget(self.cmb_format, stretch=1)
        right_layout.addLayout(fmt_row)

        quality_row = QHBoxLayout()
        self.lbl_quality = QLabel("JPEG Quality: 95%")
        self.lbl_quality.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        quality_row.addWidget(self.lbl_quality)

        self.slider_quality = QSlider(Qt.Horizontal)
        self.slider_quality.setRange(50, 100)
        self.slider_quality.setValue(95)
        self.slider_quality.setEnabled(False)
        self.slider_quality.valueChanged.connect(
            lambda v: self.lbl_quality.setText(f"JPEG Quality: {v}%")
        )
        quality_row.addWidget(self.slider_quality)
        right_layout.addLayout(quality_row)

        # File name pattern
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("File name:"))
        self.txt_pattern = QLineEdit("{PIN_NUMBER}_{NAME}")
        self.txt_pattern.setPlaceholderText("{PIN_NUMBER}_{NAME}")
        self.txt_pattern.setFixedHeight(CONTROL_HEIGHT)
        self.txt_pattern.textChanged.connect(self._refresh_pattern_preview)
        name_row.addWidget(self.txt_pattern, stretch=1)
        right_layout.addLayout(name_row)

        self.lbl_pattern_hint = QLabel("")
        self.lbl_pattern_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        right_layout.addWidget(self.lbl_pattern_hint)

        # Which cards
        self.chk_approved_only = QCheckBox("Export approved cards only (recommended)")
        self.chk_approved_only.setChecked(True)
        self.chk_approved_only.toggled.connect(self._refresh_export_list)
        right_layout.addWidget(self.chk_approved_only)

        # Artifacts
        lbl_art_head = QLabel("<b>OPTIONAL ARTIFACTS</b>")
        lbl_art_head.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 0.5px;"
        )
        right_layout.addWidget(lbl_art_head)

        self.chk_manifest = QCheckBox("Audit CSV manifest (export_manifest.csv)")
        self.chk_manifest.setChecked(True)
        right_layout.addWidget(self.chk_manifest)

        self.chk_contact_sheet = QCheckBox("Printable contact sheet PDF (contact_sheet.pdf)")
        self.chk_contact_sheet.setChecked(False)
        self.chk_contact_sheet.toggled.connect(self._on_contact_sheet_toggled)
        right_layout.addWidget(self.chk_contact_sheet)

        # The sheet layout only matters for the optional PDF.
        self.sheet_box = QFrame()
        sheet_layout = QGridLayout(self.sheet_box)
        sheet_layout.setSpacing(6)

        sheet_layout.addWidget(QLabel("Columns:"), 0, 0)
        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 6)
        self.spin_cols.setValue(2)
        self.spin_cols.setFixedHeight(CONTROL_HEIGHT)
        sheet_layout.addWidget(self.spin_cols, 0, 1)

        sheet_layout.addWidget(QLabel("Rows:"), 0, 2)
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(1, 10)
        self.spin_rows.setValue(3)
        self.spin_rows.setFixedHeight(CONTROL_HEIGHT)
        sheet_layout.addWidget(self.spin_rows, 0, 3)

        sheet_layout.addWidget(QLabel("Margin:"), 1, 0)
        self.spin_margin = QDoubleSpinBox()
        self.spin_margin.setRange(4, 50)
        self.spin_margin.setValue(12.7)
        self.spin_margin.setSuffix(" mm")
        self.spin_margin.setFixedHeight(CONTROL_HEIGHT)
        sheet_layout.addWidget(self.spin_margin, 1, 1)
        sheet_layout.setColumnStretch(2, 1)
        sheet_layout.setColumnStretch(3, 1)

        right_layout.addWidget(self.sheet_box)
        self.sheet_box.setVisible(False)

        # Action
        self.btn_execute_export = QPushButton("⚡ Export Cards")
        self.btn_execute_export.setObjectName("btn_success")
        self.btn_execute_export.setFixedHeight(CONTROL_HEIGHT)
        self.btn_execute_export.setStyleSheet(
            f"font-size: 13px; font-weight: bold; padding: 4px 12px;"
        )
        self.btn_execute_export.clicked.connect(self._run_export)
        right_layout.addWidget(self.btn_execute_export)

        self.lbl_export_result = QLabel("")
        self.lbl_export_result.setWordWrap(True)
        self.lbl_export_result.setStyleSheet(
            f"background-color: {SURFACE_LOWEST}; border: 1px solid {BORDER_SUBTLE}; "
            f"border-radius: 4px; padding: 8px; color: {TEXT_SECONDARY}; font-size: 11px; line-height: 1.4;"
        )
        right_layout.addWidget(self.lbl_export_result)

        self.btn_open_folder = QPushButton("📁 Open Destination in File Explorer")
        self.btn_open_folder.setFixedHeight(CONTROL_HEIGHT)
        self.btn_open_folder.setVisible(False)
        self.btn_open_folder.clicked.connect(self._open_in_explorer)
        right_layout.addWidget(self.btn_open_folder)

        right_layout.addStretch()
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        body.addWidget(splitter, stretch=1)

        # ---------------------------------------------------------
        # 3. Bottom Step Navigation Bar
        # ---------------------------------------------------------
        back_label, next_label, badge = workflow.footer_labels(WorkflowStep.EXPORT)
        self.nav_bar = PageFooter(
            prev_label=back_label,
            next_label=next_label,
            step_badge=badge,
            parent=self,
        )
        self.nav_bar.back_requested.connect(
            lambda: self.navigate_requested.emit(WorkflowStep.GENERATE.value)
        )
        self.nav_bar.next_requested.connect(
            lambda: self.navigate_requested.emit(WorkflowStep.DASHBOARD.value)
        )
        layout.addWidget(self.nav_bar)

        self._refresh_format_pill()
        self._refresh_pattern_preview()
        self._refresh_export_list()

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------
    def _on_format_changed(self, idx: int) -> None:
        """The quality slider only applies to JPEG."""
        is_jpeg = self.cmb_format.currentData() == "jpeg"
        self.slider_quality.setEnabled(is_jpeg)
        self._refresh_format_pill()

    def _refresh_format_pill(self) -> None:
        """Show the effective output format in the ribbon."""
        is_jpeg = self.cmb_format.currentData() == "jpeg"
        if is_jpeg:
            self.pill_format.set_status(
                f"JPEG · Q{self.slider_quality.value()}", color=PRIMARY_LIGHT
            )
        else:
            self.pill_format.set_status("PNG · LOSSLESS", color=PRIMARY_LIGHT)

    def _on_contact_sheet_toggled(self, checked: bool) -> None:
        """The sheet layout only matters for the optional PDF."""
        self.sheet_box.setVisible(checked)

    def _selected_records(self) -> List[ReviewRecord]:
        """Return the records that will be exported with the current policy."""
        if self.chk_approved_only.isChecked():
            return [r for r in self.review_records if r.status == ReviewStatus.APPROVED]
        return list(self.review_records)

    def _build_config(self) -> ExportConfiguration:
        """Build the export configuration from the current settings."""
        is_jpeg = self.cmb_format.currentData() == "jpeg"
        return ExportConfiguration(
            output_dir=str(self.last_export_dir or ""),
            format=OutputFormat.JPEG if is_jpeg else OutputFormat.PNG,
            jpeg_quality=self.slider_quality.value(),
            naming_pattern=self.txt_pattern.text().strip() or "{PIN_NUMBER}_{NAME}",
            approved_only=self.chk_approved_only.isChecked(),
            export_manifest=self.chk_manifest.isChecked(),
            export_contact_sheet=self.chk_contact_sheet.isChecked(),
            sheet_columns=self.spin_cols.value(),
            sheet_rows=self.spin_rows.value(),
            sheet_margin_mm=self.spin_margin.value(),
        )

    def _refresh_pattern_preview(self) -> None:
        """Show what the file name of a card will look like."""
        records = self._selected_records()
        if not records:
            self.lbl_pattern_hint.setText(
                "Tokens: {PIN_NUMBER} · {NAME} · {ROW} · {ID}"
            )
            return

        sample = records[0]
        source = self.source_records_map.get(sample.record_id)
        config = self._build_config()
        name = ExportManager.build_filename(config, sample, source, 0)
        self.lbl_pattern_hint.setText(f"Example: {name}")

    def _refresh_export_list(self) -> None:
        """Update the file list, the card preview and the export button."""
        records = self._selected_records()
        config = self._build_config()

        names: List[str] = []
        for index, record in enumerate(records):
            source = self.source_records_map.get(record.record_id)
            names.append(ExportManager.build_filename(config, record, source, index))
        self.file_list.set_entries(names)

        # Preview the first card that is going to be written.
        if records:
            first = records[0]
            source = self.source_records_map.get(first.record_id)
            name = ExportManager.build_filename(config, first, source, 0)
            details = ""
            if first.rendered_image_path:
                details = f"{first.pin} · {first.name or 'Unnamed'}"
            self.card_preview.set_card(first.rendered_image_path, name, details)
        else:
            self.card_preview.set_card(None, "No card selected", "")

        count = len(records)
        self.btn_execute_export.setText(
            f"⚡ Export {count} Card{'s' if count != 1 else ''}"
        )
        self.btn_execute_export.setEnabled(count > 0 and self.last_export_dir is not None)

    # ------------------------------------------------------------------
    # Preflight
    # ------------------------------------------------------------------
    def _verify_preflight(self) -> None:
        """Check that the cards can be exported before running the export."""
        if not self.review_records:
            self.pill_preflight.set_status("PREFLIGHT: NO DATA", color=SEMANTIC_WARNING)
            self.notice.set_message(
                "No cards loaded in the review session to verify.", severity="warning"
            )
            return

        if not self.last_export_dir:
            self.pill_preflight.set_status("PREFLIGHT: NO FOLDER", color=SEMANTIC_WARNING)
            self.notice.set_message(
                "Choose an output folder before running the preflight.", severity="warning"
            )
            return

        selected = self._selected_records()
        missing = [
            r for r in selected if not r.rendered_image_path or not Path(r.rendered_image_path).exists()
        ]

        if missing:
            self.pill_preflight.set_status(
                f"PREFLIGHT: {len(missing)} MISSING", color=SEMANTIC_ERROR
            )
            self.notice.set_message(
                f"{len(missing)} of {len(selected)} cards have no rendered image yet.",
                severity="error",
            )
            return

        self.pill_preflight.set_status(
            f"PREFLIGHT: {len(selected)} READY", color=SEMANTIC_SUCCESS
        )
        self.notice.set_message(
            f"Preflight passed - {len(selected)} card image(s) ready to be written "
            f"as individual files.",
            severity="success",
        )

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------
    def set_export_context(
        self,
        review_records: List[ReviewRecord],
        source_records_map: Dict[str, SourceRecord],
        match_results_map: Dict[str, PhotoMatchResult],
    ) -> None:
        """Update the context with the reviewed records."""
        self.review_records = review_records
        self.source_records_map = source_records_map
        self.match_results_map = match_results_map
        self._refresh_export_list()
        self._refresh_pattern_preview()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _browse_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if folder:
            self.last_export_dir = Path(folder)
            self.lbl_dest_dir.setText(str(folder))
            self._refresh_export_list()

    def _run_export(self) -> None:
        if not self.last_export_dir:
            self.notice.set_message(
                "Choose an output directory before exporting.", severity="warning"
            )
            return

        if not self.review_records:
            self.notice.set_message(
                "No reviewed records available to export.", severity="warning"
            )
            return

        selected = self._selected_records()
        if not selected:
            self.notice.set_message(
                "No cards match the current filter - approve at least one card.",
                severity="warning",
            )
            return

        config = self._build_config()

        try:
            result = ExportManager.export_batch(
                config=config,
                review_records=self.review_records,
                source_records_map=self.source_records_map,
                match_results_map=self.match_results_map,
            )

            msg = (
                f"<b>Export Complete!</b><br>"
                f"• {result.exported_count} card file(s) written to {self.last_export_dir.name}<br>"
                f"• {result.skipped_count} skipped (unapproved / policy)<br>"
                f"• {result.failed_count} failed"
            )
            if result.manifest_path:
                msg += f"<br>• Audit Manifest: {Path(result.manifest_path).name}"
            if result.contact_sheet_path:
                msg += f"<br>• Printable Contact Sheet: {Path(result.contact_sheet_path).name}"

            self.lbl_export_result.setText(msg)
            self.btn_open_folder.setVisible(True)
            self.export_completed.emit(result)

            self.notice.set_message(
                f"Exported {result.exported_count} individual card file(s) to "
                f"{self.last_export_dir.name}.",
                severity="success" if result.failed_count == 0 else "warning",
            )

        except Exception as e:
            logger.error("Export error: %s", e)
            self.notice.set_message(f"Export failed: {e}", severity="error")

    def _open_in_explorer(self) -> None:
        if not self.last_export_dir or not self.last_export_dir.exists():
            return
        path_str = str(self.last_export_dir)
        if sys.platform == "win32":
            os.startfile(path_str)
        elif sys.platform == "darwin":
            subprocess.run(["open", path_str])
        else:
            subprocess.run(["xdg-open", path_str])
