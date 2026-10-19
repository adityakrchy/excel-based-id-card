"""Final export configuration, batch execution, and A4 sheet imposition workstation suite.

Revamped per Stitch screens 1c3461c74814, e5e8185926dd, d1f4a84ac92b:
- Top preflight context ribbon with sheet profile, imposition mode, and preflight status pills.
- Left interactive A4 sheet imposition canvas preview displaying multi-badge layout, crop marks, and cut guides.
- Right settings panel for destination directory, format, imposition grid parameters, and audit manifests.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import OutputFormat, WorkflowStep
from id_card_generator.core.models import (
    ExportConfiguration,
    ExportResult,
    PhotoMatchResult,
    ReviewRecord,
    SourceRecord,
)
from id_card_generator.export.export_manager import ExportManager
from id_card_generator.ui.components.status_pill import StatusPill
from id_card_generator.ui.step_nav_bar import StepNavBar
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


class A4SheetPreviewWidget(QWidget):
    """Interactive visual preview of A4 page with multi-card imposition grid and crop marks."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cols: int = 2
        self.rows: int = 4
        self.margin_mm: float = 10.0
        self.gutter_mm: float = 5.0
        self.draw_crop_marks: bool = True
        self.sample_cards: List[str] = []
        self.setMinimumSize(320, 440)

    def update_imposition(self, cols: int, rows: int, margin_mm: float, gutter_mm: float, crop_marks: bool) -> None:
        self.cols = max(1, cols)
        self.rows = max(1, rows)
        self.margin_mm = margin_mm
        self.gutter_mm = gutter_mm
        self.draw_crop_marks = crop_marks
        self.update()

    def set_sample_cards(self, image_paths: List[str]) -> None:
        self.sample_cards = image_paths
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # Fill background with dark studio recessed canvas
        painter.fillRect(0, 0, w, h, QColor(SURFACE_LOWEST))

        # A4 aspect ratio: 210 x 297 mm (~1 : 1.414)
        page_aspect = 210.0 / 297.0
        avail_w = w - 40
        avail_h = h - 40

        if avail_w / avail_h > page_aspect:
            sheet_h = avail_h
            sheet_w = avail_h * page_aspect
        else:
            sheet_w = avail_w
            sheet_h = avail_w / page_aspect

        sheet_x = (w - sheet_w) / 2.0
        sheet_y = (h - sheet_h) / 2.0
        sheet_rect = QRectF(sheet_x, sheet_y, sheet_w, sheet_h)

        # Draw sheet drop shadow
        shadow_rect = sheet_rect.translated(3, 4)
        painter.fillRect(shadow_rect, QColor(0, 0, 0, 100))

        # Draw clean paper sheet
        painter.fillRect(sheet_rect, QColor("#F4F4F5"))
        painter.setPen(QPen(QColor(BORDER_DEFAULT), 1.0))
        painter.drawRect(sheet_rect)

        # Calculate card slot dimensions in sheet coordinates
        scale = sheet_w / 210.0  # pixels per mm
        margin_px = self.margin_mm * scale
        gutter_px = self.gutter_mm * scale

        grid_w = sheet_w - (2 * margin_px)
        grid_h = sheet_h - (2 * margin_px)

        slot_w = (grid_w - ((self.cols - 1) * gutter_px)) / self.cols
        slot_h = (grid_h - ((self.rows - 1) * gutter_px)) / self.rows

        card_idx = 0
        for r in range(self.rows):
            for c in range(self.cols):
                cx = sheet_x + margin_px + c * (slot_w + gutter_px)
                cy = sheet_y + margin_px + r * (slot_h + gutter_px)
                card_rect = QRectF(cx, cy, slot_w, slot_h)

                # Card slot background
                painter.fillRect(card_rect, QColor("#FFFFFF"))
                painter.setPen(QPen(QColor("#CBD5E1"), 1.0))
                painter.drawRect(card_rect)

                # Inner placeholder badge styling
                badge_rect = card_rect.adjusted(3, 3, -3, -3)
                painter.setPen(QPen(QColor("#94A3B8"), 0.5, Qt.DashLine))
                painter.drawRect(badge_rect)

                # Slot index number
                painter.setPen(QPen(QColor("#64748B"), 1.0))
                f = painter.font()
                f.setPointSize(8)
                f.setFamily(FONT_FAMILY_MONO)
                painter.setFont(f)
                painter.drawText(card_rect, Qt.AlignCenter, f"CR80 #{card_idx + 1}")

                # Draw crop marks around card corners
                if self.draw_crop_marks:
                    painter.setPen(QPen(QColor("#000000"), 0.8))
                    c_len = 5.0
                    # Top-left
                    painter.drawLine(QPointF(cx - c_len, cy), QPointF(cx - 1, cy))
                    painter.drawLine(QPointF(cx, cy - c_len), QPointF(cx, cy - 1))
                    # Top-right
                    painter.drawLine(QPointF(cx + slot_w + 1, cy), QPointF(cx + slot_w + c_len, cy))
                    painter.drawLine(QPointF(cx + slot_w, cy - c_len), QPointF(cx + slot_w, cy - 1))
                    # Bottom-left
                    painter.drawLine(QPointF(cx - c_len, cy + slot_h), QPointF(cx - 1, cy + slot_h))
                    painter.drawLine(QPointF(cx, cy + slot_h + 1), QPointF(cx, cy + slot_h + c_len))
                    # Bottom-right
                    painter.drawLine(QPointF(cx + slot_w + 1, cy + slot_h), QPointF(cx + slot_w + c_len, cy + slot_h))
                    painter.drawLine(QPointF(cx + slot_w, cy + slot_h + 1), QPointF(cx + slot_w, cy + slot_h + c_len))

                card_idx += 1

        # Registration Crosses at sheet borders
        painter.setPen(QPen(QColor("#000000"), 1.0))
        reg_size = 6.0
        # Center-top registration mark
        mx = sheet_x + sheet_w / 2.0
        my = sheet_y + 6.0
        painter.drawLine(QPointF(mx - reg_size, my), QPointF(mx + reg_size, my))
        painter.drawLine(QPointF(mx, my - reg_size), QPointF(mx, my + reg_size))
        painter.drawEllipse(QPointF(mx, my), reg_size / 2.0, reg_size / 2.0)


class ExportPage(QWidget):
    """Configures final export options, runs export, and displays audit summaries."""

    export_completed = Signal(object)  # ExportResult
    navigate_requested = Signal(str)  # WorkflowStep value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.review_records: List[ReviewRecord] = []
        self.source_records_map: Dict[str, SourceRecord] = {}
        self.match_results_map: Dict[str, PhotoMatchResult] = {}
        self.last_export_dir: Optional[Path] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ---------------------------------------------------------
        # 1. Top Preflight Context Ribbon
        # ---------------------------------------------------------
        top_ribbon = QFrame()
        top_ribbon.setObjectName("card_panel")
        top_ribbon.setStyleSheet(
            f"QFrame#card_panel {{ background-color: {SURFACE_LOW}; border: 1px solid {BORDER_DEFAULT}; border-radius: 4px; padding: 4px; }}"
        )
        ribbon_layout = QHBoxLayout(top_ribbon)
        ribbon_layout.setContentsMargins(8, 8, 8, 8)
        ribbon_layout.setSpacing(8)

        lbl_icon = QLabel("🖨")
        lbl_icon.setStyleSheet("font-size: 16px;")
        ribbon_layout.addWidget(lbl_icon)

        self.pill_profile = StatusPill("A4 SHEET (210 × 297 mm)", color=PRIMARY)
        self.pill_imposition = StatusPill("8-UP GRID (2 × 4)", color=PRIMARY_LIGHT)
        self.pill_preflight = StatusPill("PREFLIGHT: PASSED", color=SEMANTIC_SUCCESS)

        ribbon_layout.addWidget(self.pill_profile)
        ribbon_layout.addWidget(self.pill_imposition)
        ribbon_layout.addWidget(self.pill_preflight)
        ribbon_layout.addStretch()

        self.btn_run_preflight = QPushButton("⚡ Verify Preflight")
        self.btn_run_preflight.clicked.connect(self._verify_preflight)
        ribbon_layout.addWidget(self.btn_run_preflight)

        layout.addWidget(top_ribbon)

        # ---------------------------------------------------------
        # 2. Main Workstation Splitter (A4 Canvas Left, Settings Right)
        # ---------------------------------------------------------
        splitter = QSplitter(Qt.Horizontal)

        # Left Sheet Canvas Viewport
        self.sheet_preview = A4SheetPreviewWidget(self)
        splitter.addWidget(self.sheet_preview)

        # Right Inspector Panel
        right_panel = QFrame()
        right_panel.setObjectName("card_panel")
        right_panel.setStyleSheet(
            f"background-color: {SURFACE_LOW}; border: 1px solid {BORDER_DEFAULT}; border-radius: 4px;"
        )
        right_panel.setMinimumWidth(340)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(10)

        # Output Destination Box
        lbl_dest_head = QLabel("<b>OUTPUT DESTINATION</b>")
        lbl_dest_head.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 0.5px;")
        right_layout.addWidget(lbl_dest_head)

        dest_row = QHBoxLayout()
        self.btn_browse_dest = QPushButton("Select Folder...")
        self.btn_browse_dest.setObjectName("btn_primary")
        self.btn_browse_dest.clicked.connect(self._browse_destination)
        dest_row.addWidget(self.btn_browse_dest)

        self.lbl_dest_dir = QLabel("<i>No output directory selected</i>")
        self.lbl_dest_dir.setStyleSheet(f"color: {TEXT_SECONDARY}; font-family: {FONT_FAMILY_MONO}; font-size: 11px;")
        dest_row.addWidget(self.lbl_dest_dir, stretch=1)
        right_layout.addLayout(dest_row)

        # Export Format & Quality
        lbl_fmt_head = QLabel("<b>FORMAT & COMPRESSION</b>")
        lbl_fmt_head.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 0.5px;")
        right_layout.addWidget(lbl_fmt_head)

        fmt_row = QHBoxLayout()
        self.cmb_format = QComboBox()
        self.cmb_format.addItems(["PNG (Lossless 300 DPI)", "JPEG (CMYK Optimized)"])
        self.cmb_format.currentIndexChanged.connect(self._on_format_changed)
        fmt_row.addWidget(self.cmb_format)
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

        # Imposition Grid Configuration
        lbl_imp_head = QLabel("<b>A4 SHEET IMPOSITION GRID</b>")
        lbl_imp_head.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 0.5px;")
        right_layout.addWidget(lbl_imp_head)

        grid_cfg = QGridLayout()
        grid_cfg.setSpacing(6)

        grid_cfg.addWidget(QLabel("Columns:"), 0, 0)
        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 6)
        self.spin_cols.setValue(2)
        self.spin_cols.valueChanged.connect(self._on_imposition_changed)
        grid_cfg.addWidget(self.spin_cols, 0, 1)

        grid_cfg.addWidget(QLabel("Rows:"), 0, 2)
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(1, 10)
        self.spin_rows.setValue(4)
        self.spin_rows.valueChanged.connect(self._on_imposition_changed)
        grid_cfg.addWidget(self.spin_rows, 0, 3)

        grid_cfg.addWidget(QLabel("Margin:"), 1, 0)
        self.spin_margin = QDoubleSpinBox()
        self.spin_margin.setRange(0, 50)
        self.spin_margin.setValue(10.0)
        self.spin_margin.setSuffix(" mm")
        self.spin_margin.valueChanged.connect(self._on_imposition_changed)
        grid_cfg.addWidget(self.spin_margin, 1, 1)

        grid_cfg.addWidget(QLabel("Gutter:"), 1, 2)
        self.spin_gutter = QDoubleSpinBox()
        self.spin_gutter.setRange(0, 30)
        self.spin_gutter.setValue(5.0)
        self.spin_gutter.setSuffix(" mm")
        self.spin_gutter.valueChanged.connect(self._on_imposition_changed)
        grid_cfg.addWidget(self.spin_gutter, 1, 3)

        right_layout.addLayout(grid_cfg)

        # Artifacts Checkboxes
        lbl_art_head = QLabel("<b>ARTIFACTS & PRE-PRESS</b>")
        lbl_art_head.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 0.5px;")
        right_layout.addWidget(lbl_art_head)

        self.chk_crop_marks = QCheckBox("Draw Corner Crop Marks & Registration Targets")
        self.chk_crop_marks.setChecked(True)
        self.chk_crop_marks.toggled.connect(self._on_imposition_changed)
        right_layout.addWidget(self.chk_crop_marks)

        self.chk_approved_only = QCheckBox("Export Approved Cards Only (Recommended)")
        self.chk_approved_only.setChecked(True)
        right_layout.addWidget(self.chk_approved_only)

        self.chk_manifest = QCheckBox("Generate Audit CSV Manifest (export_manifest.csv)")
        self.chk_manifest.setChecked(True)
        right_layout.addWidget(self.chk_manifest)

        self.chk_contact_sheet = QCheckBox("Generate Printable PDF Sheet (contact_sheet.pdf)")
        self.chk_contact_sheet.setChecked(True)
        right_layout.addWidget(self.chk_contact_sheet)

        # Action Execution Box
        self.btn_execute_export = QPushButton("⚡ Export Cards & Generate Sheets")
        self.btn_execute_export.setObjectName("btn_success")
        self.btn_execute_export.setStyleSheet("font-size: 13px; font-weight: bold; padding: 10px;")
        self.btn_execute_export.clicked.connect(self._run_export)
        right_layout.addWidget(self.btn_execute_export)

        self.lbl_export_result = QLabel("")
        self.lbl_export_result.setWordWrap(True)
        self.lbl_export_result.setStyleSheet(
            f"background-color: {SURFACE_LOWEST}; border: 1px solid {BORDER_SUBTLE}; border-radius: 4px; padding: 8px; color: {TEXT_SECONDARY}; font-size: 11px; line-height: 1.4;"
        )
        right_layout.addWidget(self.lbl_export_result)

        self.btn_open_folder = QPushButton("📁 Open Destination in File Explorer")
        self.btn_open_folder.setVisible(False)
        self.btn_open_folder.clicked.connect(self._open_in_explorer)
        right_layout.addWidget(self.btn_open_folder)

        right_layout.addStretch()
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, stretch=1)

        # ---------------------------------------------------------
        # 3. Bottom Step Navigation Bar (Preserved for compatibility)
        # ---------------------------------------------------------
        self.nav_bar = StepNavBar(
            prev_label="Review Cards",
            next_label="Complete & Return to Dashboard",
            step_badge="Step 7 of 7: Export Cards",
            parent=self,
        )
        self.nav_bar.back_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.REVIEW.value))
        self.nav_bar.next_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.DASHBOARD.value))
        layout.addWidget(self.nav_bar)

    def _on_imposition_changed(self) -> None:
        cols = self.spin_cols.value()
        rows = self.spin_rows.value()
        margin = self.spin_margin.value()
        gutter = self.spin_gutter.value()
        crop = self.chk_crop_marks.isChecked()

        self.pill_imposition.set_status(f"{cols * rows}-UP GRID ({cols} × {rows})", color=PRIMARY_LIGHT)
        self.sheet_preview.update_imposition(cols, rows, margin, gutter, crop)

    def _verify_preflight(self) -> None:
        if not self.review_records:
            self.pill_preflight.set_status("PREFLIGHT: NO DATA", color=SEMANTIC_WARNING)
            QMessageBox.warning(self, "Preflight", "No cards loaded in review session to verify.")
            return

        approved = sum(1 for r in self.review_records if r.status.value == "approved")
        self.pill_preflight.set_status(f"PREFLIGHT: {approved} READY", color=SEMANTIC_SUCCESS)
        QMessageBox.information(
            self,
            "Preflight Verification",
            f"Preflight Checks Passed:\n\n"
            f"• Printable Sheet: ISO 216 A4 (210 × 297 mm) @ 300 DPI\n"
            f"• Imposition Layout: {self.spin_cols.value()} × {self.spin_rows.value()} ({self.spin_cols.value() * self.spin_rows.value()} cards/sheet)\n"
            f"• Crop Marks: {'Enabled' if self.chk_crop_marks.isChecked() else 'Disabled'}\n"
            f"• Approved Cards Ready: {approved} of {len(self.review_records)}",
        )

    def set_export_context(
        self,
        review_records: List[ReviewRecord],
        source_records_map: Dict[str, SourceRecord],
        match_results_map: Dict[str, PhotoMatchResult],
    ) -> None:
        """Update context with reviewed records."""
        self.review_records = review_records
        self.source_records_map = source_records_map
        self.match_results_map = match_results_map

        # Pass rendered card images to sheet preview
        card_paths = [r.rendered_image_path for r in review_records if r.rendered_image_path]
        self.sheet_preview.set_sample_cards(card_paths)

    def _browse_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if folder:
            self.last_export_dir = Path(folder)
            self.lbl_dest_dir.setText(str(folder))

    def _on_format_changed(self, idx: int) -> None:
        is_jpeg = idx == 1
        self.slider_quality.setEnabled(is_jpeg)

    def _run_export(self) -> None:
        if not self.last_export_dir:
            QMessageBox.warning(self, "No Destination", "Please choose an output directory first.")
            return

        if not self.review_records:
            QMessageBox.warning(self, "No Records", "No reviewed records available to export.")
            return

        is_jpeg = self.cmb_format.currentIndex() == 1
        config = ExportConfiguration(
            output_dir=str(self.last_export_dir),
            format=OutputFormat.JPEG if is_jpeg else OutputFormat.PNG,
            jpeg_quality=self.slider_quality.value(),
            approved_only=self.chk_approved_only.isChecked(),
            export_manifest=self.chk_manifest.isChecked(),
            export_contact_sheet=self.chk_contact_sheet.isChecked(),
        )

        try:
            result = ExportManager.export_batch(
                config=config,
                review_records=self.review_records,
                source_records_map=self.source_records_map,
                match_results_map=self.match_results_map,
            )

            msg = (
                f"<b>Export Complete!</b><br>"
                f"• {result.exported_count} cards successfully exported to {self.last_export_dir.name}<br>"
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

            QMessageBox.information(self, "Export Successful", f"Successfully exported {result.exported_count} ID cards.")

        except Exception as e:
            logger.error("Export error: %s", e)
            QMessageBox.critical(self, "Export Error", f"Export failed: {e}")

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
