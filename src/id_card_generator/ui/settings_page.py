"""Settings page allowing theme selection, missing photo policy, and diagnostic exports."""

import logging
from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import (
    APP_NAME,
    APP_VERSION,
    MissingPhotoPolicy,
    WorkflowStep,
)
from id_card_generator.core.logging_config import export_diagnostic_logs, get_current_log_path
from id_card_generator.ui import workflow
from id_card_generator.ui.components.page_scaffold import InlineNotice, PageHeader

logger = logging.getLogger(__name__)


class SettingsPage(QWidget):
    """Application preferences and diagnostics."""

    theme_changed = Signal(str)  # "dark" or "light"
    policy_changed = Signal(object)  # MissingPhotoPolicy

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        badge, title, subtitle = workflow.page_header_text(WorkflowStep.SETTINGS)
        self.page_header = PageHeader(title, subtitle, badge)
        layout.addWidget(self.page_header)

        self.notice = InlineNotice()
        notice_row = QHBoxLayout()
        notice_row.setContentsMargins(16, 8, 16, 0)
        notice_row.addWidget(self.notice)
        layout.addLayout(notice_row)

        body = QVBoxLayout()
        body.setContentsMargins(24, 20, 24, 24)
        body.setSpacing(16)
        layout.addLayout(body, stretch=1)

        # 1. UI Appearance
        app_card = QFrame()
        app_card.setObjectName("card_panel")
        app_layout = QVBoxLayout(app_card)
        app_layout.addWidget(self._section_label("APPEARANCE"))

        theme_row = QHBoxLayout()
        self.cmb_theme = QComboBox()
        self.cmb_theme.setPlaceholderText("Application theme")
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
        app_layout.addLayout(theme_row)
        body.addWidget(app_card)

        # 2. Processing Defaults
        proc_card = QFrame()
        proc_card.setObjectName("card_panel")
        proc_layout = QVBoxLayout(proc_card)
        proc_layout.addWidget(self._section_label("GENERATION"))

        policy_row = QHBoxLayout()
        self.cmb_policy = QComboBox()
        self.cmb_policy.setPlaceholderText("Missing photograph policy")
        self.cmb_policy.addItem("Generate with Silhouette Placeholder", MissingPhotoPolicy.GENERATE_WITH_PLACEHOLDER)
        self.cmb_policy.addItem("Skip Record During Batch Generation", MissingPhotoPolicy.SKIP_RECORD)
        self.cmb_policy.addItem("Fail Record and Halt Card Creation", MissingPhotoPolicy.FAIL_RECORD)
        self.cmb_policy.currentIndexChanged.connect(self._on_policy_changed)
        policy_row.addWidget(self.cmb_policy)
        policy_row.addStretch()
        proc_layout.addLayout(policy_row)

        dpi_row = QHBoxLayout()
        self.spin_dpi = QSpinBox()
        self.spin_dpi.setPrefix("Default print DPI ")
        self.spin_dpi.setRange(72, 1200)
        self.spin_dpi.setValue(300)
        dpi_row.addWidget(self.spin_dpi)
        dpi_row.addStretch()
        proc_layout.addLayout(dpi_row)

        body.addWidget(proc_card)

        # 3. Diagnostics & Logs
        diag_card = QFrame()
        diag_card.setObjectName("card_panel")
        diag_layout = QVBoxLayout(diag_card)
        diag_layout.addWidget(self._section_label("DIAGNOSTICS"))

        lbl_log_path = QLabel(f"Active Log File: {get_current_log_path()}")
        lbl_log_path.setStyleSheet("color: #94A3B8; font-family: monospace; font-size: 11px;")
        lbl_log_path.setWordWrap(True)
        diag_layout.addWidget(lbl_log_path)

        self.btn_export_logs = QPushButton("Export Diagnostic Logs...")
        self.btn_export_logs.clicked.connect(self._export_logs)
        diag_layout.addWidget(self.btn_export_logs)
        body.addWidget(diag_card)

        # 4. About Info
        about_card = QFrame()
        about_card.setObjectName("card_panel")
        about_layout = QVBoxLayout(about_card)
        about_layout.addWidget(QLabel(f"<b>{APP_NAME} v{APP_VERSION}</b>"))
        lbl_about = QLabel(
            "Designed for batch ID card generation from Excel data and photo libraries.\n"
            "Authoritative Pillow rendering engine • Qt PySide6 native interface.\n"
            "All data processing remains 100% local."
        )
        lbl_about.setStyleSheet("color: #64748B; font-size: 12px;")
        about_layout.addWidget(lbl_about)
        body.addWidget(about_card)

        body.addStretch()

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "sectionLabel")
        return label

    def _on_theme_changed(self, idx: int) -> None:
        theme = self.cmb_theme.currentData() or "black"
        from id_card_generator.ui.theme_manager import ThemeManager
        ThemeManager.instance().set_theme(theme)
        self.theme_changed.emit(theme)

    def _on_policy_changed(self) -> None:
        policy = self.cmb_policy.currentData()
        self.policy_changed.emit(policy)

    def _export_logs(self) -> None:
        dest, _ = QFileDialog.getSaveFileName(self, "Export Diagnostic Logs", "id_card_generator_diagnostics.log", "Log Files (*.log)")
        if dest:
            try:
                export_diagnostic_logs(Path(dest))
                self.notice.set_message(
                    f"Diagnostic logs exported to {dest}.", severity="success"
                )
            except Exception as e:
                logger.error("Failed to export logs: %s", e)
                self.notice.set_message(f"Failed to export logs: {e}", severity="error")
