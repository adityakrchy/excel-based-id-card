"""Project dashboard page displaying overview metrics, alerts, and quick actions."""

from typing import Callable, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from id_card_generator.core.constants import WorkflowStep


class DashboardPage(QWidget):
    """Dashboard summarizing current project status, validation alerts, and quick workflows."""

    navigate_requested = Signal(str)  # WorkflowStep

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Header Title
        title_box = QVBoxLayout()
        lbl_heading = QLabel("<h2>Project Overview & Workflow Status</h2>")
        lbl_sub = QLabel("Welcome to the Excel-Based ID Card Generator. Monitor your dataset, templates, and batch progress below.")
        lbl_sub.setStyleSheet("color: #64748B; font-size: 13px;")
        title_box.addWidget(lbl_heading)
        title_box.addWidget(lbl_sub)
        layout.addLayout(title_box)

        # KPI Metric Cards Grid
        grid = QGridLayout()
        grid.setSpacing(16)

        self.card_records = self._create_kpi_card("Spreadsheet Records", "0 Records", "No Excel data loaded yet", "#3B82F6")
        self.card_photos = self._create_kpi_card("Photographs Matched", "0 Photos", "No folder selected", "#10B981")
        self.card_template = self._create_kpi_card("Active Template", "None Selected", "Choose starter or custom template", "#8B5CF6")
        self.card_review = self._create_kpi_card("Review & Approvals", "0 / 0 Approved", "Ready for generation", "#F59E0B")

        grid.addWidget(self.card_records, 0, 0)
        grid.addWidget(self.card_photos, 0, 1)
        grid.addWidget(self.card_template, 1, 0)
        grid.addWidget(self.card_review, 1, 1)
        layout.addLayout(grid)

        # Validation Alerts Box
        self.alert_frame = QFrame()
        self.alert_frame.setObjectName("card_panel")
        alert_layout = QVBoxLayout(self.alert_frame)
        self.lbl_alert_title = QLabel("<b>Validation & Integrity Status</b>")
        self.lbl_alert_body = QLabel("✓ System ready. Please import your Excel file to begin.")
        self.lbl_alert_body.setStyleSheet("color: #10B981; font-weight: 500;")
        alert_layout.addWidget(self.lbl_alert_title)
        alert_layout.addWidget(self.lbl_alert_body)
        layout.addWidget(self.alert_frame)

        # Quick Actions Row
        actions_frame = QFrame()
        actions_frame.setObjectName("card_panel")
        actions_layout = QVBoxLayout(actions_frame)
        lbl_actions_title = QLabel("<b>Guided Next Actions</b>")
        actions_layout.addWidget(lbl_actions_title)

        btn_row = QHBoxLayout()
        self.btn_goto_data = QPushButton("1. Import Data Source")
        self.btn_goto_data.setObjectName("btn_primary")
        self.btn_goto_data.clicked.connect(lambda: self.navigate_requested.emit(WorkflowStep.DATA_SOURCE.value))

        self.btn_goto_photos = QPushButton("2. Select Photo Folder")
        self.btn_goto_photos.clicked.connect(lambda: self.navigate_requested.emit(WorkflowStep.PHOTOS.value))

        self.btn_goto_template = QPushButton("3. Choose Template")
        self.btn_goto_template.clicked.connect(lambda: self.navigate_requested.emit(WorkflowStep.TEMPLATES.value))

        self.btn_goto_editor = QPushButton("4. Visual Canvas Editor")
        self.btn_goto_editor.clicked.connect(lambda: self.navigate_requested.emit(WorkflowStep.CANVAS_EDITOR.value))

        self.btn_goto_generate = QPushButton("5. Batch Generate")
        self.btn_goto_generate.clicked.connect(lambda: self.navigate_requested.emit(WorkflowStep.GENERATE.value))

        btn_row.addWidget(self.btn_goto_data)
        btn_row.addWidget(self.btn_goto_photos)
        btn_row.addWidget(self.btn_goto_template)
        btn_row.addWidget(self.btn_goto_editor)
        btn_row.addWidget(self.btn_goto_generate)
        actions_layout.addLayout(btn_row)

        layout.addWidget(actions_frame)
        layout.addStretch()

        scroll.setWidget(container)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(scroll)

    def _create_kpi_card(self, title: str, main_val: str, subtitle: str, color_hex: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card_panel")
        layout = QVBoxLayout(card)
        layout.setSpacing(6)

        lbl_t = QLabel(title.upper())
        lbl_t.setStyleSheet("font-size: 11px; font-weight: bold; color: #64748B; letter-spacing: 0.5px;")

        lbl_val = QLabel(main_val)
        lbl_val.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {color_hex};")
        card.lbl_val = lbl_val

        lbl_sub = QLabel(subtitle)
        lbl_sub.setStyleSheet("font-size: 12px; color: #94A3B8;")
        card.lbl_sub = lbl_sub

        layout.addWidget(lbl_t)
        layout.addWidget(lbl_val)
        layout.addWidget(lbl_sub)
        return card

    def update_metrics(
        self,
        record_count: int,
        matched_photos: int,
        missing_photos: int,
        template_name: str,
        approved_count: int,
        total_review: int,
        validation_warnings: int,
        validation_errors: int,
    ) -> None:
        """Refresh dashboard KPI values."""
        self.card_records.lbl_val.setText(f"{record_count:,} Records")
        self.card_records.lbl_sub.setText(f"{validation_errors} errors • {validation_warnings} warnings")

        self.card_photos.lbl_val.setText(f"{matched_photos:,} Photos")
        self.card_photos.lbl_sub.setText(f"{missing_photos} missing photo(s)")

        self.card_template.lbl_val.setText(template_name or "None Selected")
        self.card_template.lbl_sub.setText("Ready for canvas editing")

        self.card_review.lbl_val.setText(f"{approved_count:,} / {total_review:,} Approved")
        self.card_review.lbl_sub.setText("Ready for export" if approved_count > 0 else "Review cards to approve")

        # Update status banner
        if validation_errors > 0 or missing_photos > 0:
            self.lbl_alert_body.setText(
                f"⚠ Attention required: {validation_errors} record validation errors, "
                f"{missing_photos} missing photo matches."
            )
            self.lbl_alert_body.setStyleSheet("color: #EF4444; font-weight: 600;")
        else:
            self.lbl_alert_body.setText("✓ All records and photographs validated successfully.")
            self.lbl_alert_body.setStyleSheet("color: #10B981; font-weight: 600;")
