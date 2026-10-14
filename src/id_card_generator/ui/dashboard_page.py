"""Project dashboard page displaying overview metrics, alerts, workflow launcher, and embedded settings."""

from typing import Callable, Optional
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import APP_NAME, APP_VERSION, MissingPhotoPolicy, WorkflowStep
from id_card_generator.core.logging_config import export_diagnostic_logs, get_current_log_path


class DashboardPage(QWidget):
    """Dashboard summarizing current project status, validation alerts, step-by-step launcher, and settings."""

    navigate_requested = Signal(str)  # WorkflowStep
    theme_changed = Signal(str)  # "black", "white", "system"
    policy_changed = Signal(object)  # MissingPhotoPolicy
    dpi_changed = Signal(int)

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

        # 1. Header Title
        title_box = QVBoxLayout()
        lbl_heading = QLabel(f"<h2>{APP_NAME}</h2>")
        lbl_sub = QLabel("Batch design and generate high-resolution ID cards step-by-step from Excel spreadsheets.")
        lbl_sub.setStyleSheet("color: #64748B; font-size: 13px;")
        title_box.addWidget(lbl_heading)
        title_box.addWidget(lbl_sub)
        layout.addLayout(title_box)

        # 2. Workflow Launcher Hero Card
        hero_card = QFrame()
        hero_card.setObjectName("card_panel")
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(20, 18, 20, 18)
        hero_layout.setSpacing(10)

        lbl_hero_title = QLabel("<b>🚀 Step-by-Step ID Card Generation</b>")
        lbl_hero_title.setStyleSheet("font-size: 16px; color: #38BDF8;")
        lbl_hero_desc = QLabel(
            "Execute the generation pipeline sequentially: import spreadsheet records, link photographs with "
            "streaming background queues, design or select an ID template, bind columns, batch generate, and review."
        )
        lbl_hero_desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        lbl_hero_desc.setWordWrap(True)

        hero_btn_row = QHBoxLayout()
        self.btn_start_workflow = QPushButton("Start Generation Workflow ➔ (1. Data Source)")
        self.btn_start_workflow.setObjectName("btn_primary")
        self.btn_start_workflow.setFixedHeight(42)
        self.btn_start_workflow.setCursor(Qt.PointingHandCursor)
        self.btn_start_workflow.setStyleSheet("font-size: 14px; font-weight: bold; padding: 0 24px;")
        self.btn_start_workflow.clicked.connect(lambda: self.navigate_requested.emit(WorkflowStep.DATA_SOURCE.value))
        hero_btn_row.addWidget(self.btn_start_workflow)
        hero_btn_row.addStretch()

        hero_layout.addWidget(lbl_hero_title)
        hero_layout.addWidget(lbl_hero_desc)
        hero_layout.addLayout(hero_btn_row)
        layout.addWidget(hero_card)

        # 3. KPI Metric Cards Grid
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

        # 4. Validation & Integrity Alerts Box
        self.alert_frame = QFrame()
        self.alert_frame.setObjectName("card_panel")
        alert_layout = QVBoxLayout(self.alert_frame)
        self.lbl_alert_title = QLabel("<b>Validation & Integrity Status</b>")
        self.lbl_alert_body = QLabel("✓ System ready. Click 'Start Generation Workflow' to begin.")
        self.lbl_alert_body.setStyleSheet("color: #10B981; font-weight: 500;")
        alert_layout.addWidget(self.lbl_alert_title)
        alert_layout.addWidget(self.lbl_alert_body)
        layout.addWidget(self.alert_frame)

        # 5. Application & Generation Settings (Embedded directly in Dashboard)
        settings_title = QLabel("<h3>⚙ Application & Project Settings</h3>")
        layout.addWidget(settings_title)

        # Appearance & Theme Card
        theme_card = QFrame()
        theme_card.setObjectName("card_panel")
        theme_layout = QVBoxLayout(theme_card)
        theme_layout.setContentsMargins(16, 14, 16, 14)
        theme_layout.addWidget(QLabel("<b>Appearance & Theme:</b>"))

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Interface Theme:"))
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItem("Black (Fluent Dark)", "black")
        self.cmb_theme.addItem("White (Fluent Light)", "white")
        self.cmb_theme.addItem("System (Follow Windows)", "system")
        from id_card_generator.ui.theme_manager import ThemeManager
        current_pref = ThemeManager.instance().get_preference()
        idx = self.cmb_theme.findData(current_pref)
        if idx >= 0:
            self.cmb_theme.setCurrentIndex(idx)
        self.cmb_theme.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self.cmb_theme)
        theme_row.addStretch()
        theme_layout.addLayout(theme_row)
        layout.addWidget(theme_card)

        # Processing & Missing Photo Policy Card
        proc_card = QFrame()
        proc_card.setObjectName("card_panel")
        proc_layout = QVBoxLayout(proc_card)
        proc_layout.setContentsMargins(16, 14, 16, 14)
        proc_layout.setSpacing(10)
        proc_layout.addWidget(QLabel("<b>Generation & Rendering Rules:</b>"))

        policy_row = QHBoxLayout()
        policy_row.addWidget(QLabel("Missing Photograph Policy:"))
        self.cmb_policy = QComboBox()
        self.cmb_policy.addItem("Generate with Silhouette Placeholder", MissingPhotoPolicy.GENERATE_WITH_PLACEHOLDER)
        self.cmb_policy.addItem("Skip Record During Batch Generation", MissingPhotoPolicy.SKIP_RECORD)
        self.cmb_policy.addItem("Fail Record and Halt Card Creation", MissingPhotoPolicy.FAIL_RECORD)
        self.cmb_policy.currentIndexChanged.connect(self._on_policy_changed)
        policy_row.addWidget(self.cmb_policy)
        policy_row.addStretch()
        proc_layout.addLayout(policy_row)

        dpi_row = QHBoxLayout()
        dpi_row.addWidget(QLabel("Default Print DPI:"))
        self.spin_dpi = QSpinBox()
        self.spin_dpi.setRange(72, 1200)
        self.spin_dpi.setValue(300)
        self.spin_dpi.valueChanged.connect(self.dpi_changed.emit)
        dpi_row.addWidget(self.spin_dpi)
        dpi_row.addStretch()
        proc_layout.addLayout(dpi_row)

        layout.addWidget(proc_card)

        # Diagnostics & Logs Card
        diag_card = QFrame()
        diag_card.setObjectName("card_panel")
        diag_layout = QVBoxLayout(diag_card)
        diag_layout.setContentsMargins(16, 14, 16, 14)
        diag_layout.setSpacing(8)
        diag_layout.addWidget(QLabel("<b>Diagnostics & Troubleshooting:</b>"))

        lbl_log_path = QLabel(f"Active Log File: {get_current_log_path()}")
        lbl_log_path.setStyleSheet("color: #94A3B8; font-family: monospace; font-size: 11px;")
        lbl_log_path.setWordWrap(True)
        diag_layout.addWidget(lbl_log_path)

        diag_btn_row = QHBoxLayout()
        self.btn_export_logs = QPushButton("Export Diagnostic Logs...")
        self.btn_export_logs.clicked.connect(self._export_logs)
        diag_btn_row.addWidget(self.btn_export_logs)
        diag_btn_row.addStretch()
        diag_layout.addLayout(diag_btn_row)

        layout.addWidget(diag_card)

        # About Info
        about_card = QFrame()
        about_card.setObjectName("card_panel")
        about_layout = QVBoxLayout(about_card)
        about_layout.setContentsMargins(16, 14, 16, 14)
        about_layout.addWidget(QLabel(f"<b>{APP_NAME} v{APP_VERSION}</b>"))
        lbl_about = QLabel(
            "Designed for batch ID card generation from Excel data and high-speed photo matching.\n"
            "Authoritative Pillow rendering engine • Qt PySide6 native interface.\n"
            "All data processing remains 100% local."
        )
        lbl_about.setStyleSheet("color: #64748B; font-size: 12px;")
        about_layout.addWidget(lbl_about)
        layout.addWidget(about_card)

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

    def _on_theme_changed(self) -> None:
        theme = self.cmb_theme.currentData()
        self.theme_changed.emit(theme)

    def _on_policy_changed(self) -> None:
        policy = self.cmb_policy.currentData()
        self.policy_changed.emit(policy)

    def _export_logs(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Diagnostic Log Package",
            "cardforge_diagnostic_logs.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if path:
            try:
                dest = export_diagnostic_logs(Path(path))
                QMessageBox.information(
                    self,
                    "Logs Exported",
                    f"Diagnostic logs successfully written to:\n{dest}",
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Export Failed",
                    f"Could not export diagnostic logs:\n{e}",
                )
