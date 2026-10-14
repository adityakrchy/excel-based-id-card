"""Final export configuration, batch execution, and audit summary page."""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
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
from id_card_generator.ui.step_nav_bar import StepNavBar

logger = logging.getLogger(__name__)


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
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        layout.addWidget(QLabel("<h2>Final ID Card Export</h2>"))

        # 1. Destination Directory Card
        dest_card = QFrame()
        dest_card.setObjectName("card_panel")
        dest_layout = QHBoxLayout(dest_card)

        self.btn_browse_dest = QPushButton("Select Output Directory...")
        self.btn_browse_dest.setObjectName("btn_primary")
        self.btn_browse_dest.clicked.connect(self._browse_destination)

        self.lbl_dest_dir = QLabel("<i>No output directory selected</i>")
        self.lbl_dest_dir.setStyleSheet("color: #94A3B8; font-weight: 500;")

        dest_layout.addWidget(self.btn_browse_dest)
        dest_layout.addWidget(self.lbl_dest_dir, stretch=1)
        layout.addWidget(dest_card)

        # 2. Export Configuration Card
        opt_card = QFrame()
        opt_card.setObjectName("card_panel")
        opt_layout = QVBoxLayout(opt_card)
        opt_layout.setSpacing(12)
        opt_layout.addWidget(QLabel("<b>Export Settings & Artifacts:</b>"))

        # Output format & quality
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Image Format:"))
        self.cmb_format = QComboBox()
        self.cmb_format.addItems(["PNG (Lossless)", "JPEG"])
        self.cmb_format.currentIndexChanged.connect(self._on_format_changed)
        fmt_row.addWidget(self.cmb_format)

        fmt_row.addSpacing(20)
        self.lbl_quality = QLabel("JPEG Quality: 95%")
        fmt_row.addWidget(self.lbl_quality)
        self.slider_quality = QSlider(Qt.Horizontal)
        self.slider_quality.setRange(50, 100)
        self.slider_quality.setValue(95)
        self.slider_quality.valueChanged.connect(
            lambda v: self.lbl_quality.setText(f"JPEG Quality: {v}%")
        )
        self.slider_quality.setEnabled(False)
        fmt_row.addWidget(self.slider_quality)
        opt_layout.addLayout(fmt_row)

        # Approved only checkbox
        self.chk_approved_only = QCheckBox("Export Approved Cards Only (Recommended)")
        self.chk_approved_only.setChecked(True)
        opt_layout.addWidget(self.chk_approved_only)

        # Audit manifest CSV checkbox
        self.chk_manifest = QCheckBox("Generate Audit CSV Manifest (export_manifest.csv)")
        self.chk_manifest.setChecked(True)
        opt_layout.addWidget(self.chk_manifest)

        # PDF contact sheet checkbox
        self.chk_contact_sheet = QCheckBox("Generate Printable PDF Contact Sheet (contact_sheet.pdf)")
        self.chk_contact_sheet.setChecked(True)
        opt_layout.addWidget(self.chk_contact_sheet)

        layout.addWidget(opt_card)

        # 3. Primary Export Action & Result Card
        action_card = QFrame()
        action_card.setObjectName("card_panel")
        act_layout = QVBoxLayout(action_card)

        self.btn_execute_export = QPushButton("Export Cards Now")
        self.btn_execute_export.setObjectName("btn_success")
        self.btn_execute_export.setStyleSheet("font-size: 16px; padding: 12px 24px;")
        self.btn_execute_export.clicked.connect(self._run_export)
        act_layout.addWidget(self.btn_execute_export)

        self.lbl_export_result = QLabel("")
        self.lbl_export_result.setWordWrap(True)
        act_layout.addWidget(self.lbl_export_result)

        self.btn_open_folder = QPushButton("Open Destination in File Explorer")
        self.btn_open_folder.setVisible(False)
        self.btn_open_folder.clicked.connect(self._open_in_explorer)
        act_layout.addWidget(self.btn_open_folder)

        layout.addWidget(action_card)
        layout.addStretch()

        # Bottom Step Navigation Bar
        self.nav_bar = StepNavBar(
            prev_label="Review Cards",
            next_label="Complete & Return to Dashboard",
            step_badge="Step 7 of 7: Export Cards",
            parent=self,
        )
        self.nav_bar.back_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.REVIEW.value))
        self.nav_bar.next_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.DASHBOARD.value))
        layout.addWidget(self.nav_bar)

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
