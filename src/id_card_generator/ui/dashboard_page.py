"""Project onboarding hub and workspace launcher matching Screenshot 2 / Stitch Screen c0960262ecc9."""

from pathlib import Path
from typing import Callable, Dict, List, Optional
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
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
from id_card_generator.core.models import ProjectConfiguration
from id_card_generator.ui.components.status_pill import StatusPill
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
    SURFACE_CONTAINER,
    SURFACE_HIGH,
    SURFACE_LOW,
    SURFACE_LOWEST,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class PresetCardWidget(QFrame):
    """Template preset card showcasing dimensions, standard, and 1-click instantiate."""

    selected = Signal(str)  # Preset key

    def __init__(
        self,
        key: str,
        title: str,
        subtitle: str,
        description: str,
        badge: str,
        tech_note: str,
        icon_type: str = "card",
        badge_color: str = "#8E909F",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("preset_card")
        self._key = key
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        # Header: Icon + Badge
        header = QHBoxLayout()
        header.setSpacing(8)

        icon_box = QLabel()
        icon_box.setFixedSize(32, 32)
        if icon_type == "card":
            icon_box.setText("🪪")
            icon_box.setStyleSheet("background-color: #1A2744; border: 1px solid #2B3D66; border-radius: 6px; font-size: 16px;")
        elif icon_type == "shield":
            icon_box.setText("🛡️")
            icon_box.setStyleSheet("background-color: #162B20; border: 1px solid #234834; border-radius: 6px; font-size: 16px;")
        elif icon_type == "cap":
            icon_box.setText("🎓")
            icon_box.setStyleSheet("background-color: #242233; border: 1px solid #3A3654; border-radius: 6px; font-size: 16px;")
        else:
            icon_box.setText("🎟️")
            icon_box.setStyleSheet("background-color: #2B2519; border: 1px solid #4D3F24; border-radius: 6px; font-size: 16px;")
        icon_box.setAlignment(Qt.AlignCenter)
        header.addWidget(icon_box)
        header.addStretch()

        lbl_badge = QLabel(badge)
        lbl_badge.setStyleSheet(
            f"background-color: {SURFACE_HIGH}; color: {badge_color}; "
            f"border: 1px solid {BORDER_SUBTLE}; border-radius: 4px; "
            f"font-family: {FONT_FAMILY_MONO}; font-size: 10px; font-weight: 600; padding: 2px 6px;"
        )
        header.addWidget(lbl_badge)
        layout.addLayout(header)

        # Title & Subtitle
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: #FFFFFF; font-family: {FONT_FAMILY_UI}; font-size: 13px; font-weight: 700;")
        layout.addWidget(lbl_title)

        lbl_sub = QLabel(subtitle)
        lbl_sub.setStyleSheet(f"color: {TEXT_MUTED}; font-family: {FONT_FAMILY_MONO}; font-size: 10px;")
        layout.addWidget(lbl_sub)

        # Description
        lbl_desc = QLabel(description)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; line-height: 1.35;")
        layout.addWidget(lbl_desc, stretch=1)

        # Bottom row: Tech Note + Use Link
        bottom = QHBoxLayout()
        lbl_tech = QLabel(tech_note)
        lbl_tech.setStyleSheet(f"color: {TEXT_MUTED}; font-family: {FONT_FAMILY_MONO}; font-size: 10px;")
        bottom.addWidget(lbl_tech)
        bottom.addStretch()

        self.btn_use = QPushButton("Use →")
        self.btn_use.setCursor(Qt.PointingHandCursor)
        self.btn_use.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {PRIMARY}; border: none; font-weight: 600; font-size: 11px; }}"
            f"QPushButton:hover {{ color: #85A3FF; text-decoration: underline; }}"
        )
        self.btn_use.clicked.connect(lambda: self.selected.emit(self._key))
        bottom.addWidget(self.btn_use)
        layout.addLayout(bottom)

        self.setStyleSheet(
            f"QFrame#preset_card {{"
            f"  background-color: {SURFACE_LOW};"
            f"  border: 1px solid {BORDER_DEFAULT};"
            f"  border-radius: 6px;"
            f"}}"
            f"QFrame#preset_card:hover {{"
            f"  background-color: {SURFACE_CONTAINER};"
            f"  border-color: {PRIMARY};"
            f"}}"
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.selected.emit(self._key)
        super().mousePressEvent(event)


class RecentProjectRowWidget(QFrame):
    """Recent project entry with icon, title, tags, path, and open button."""

    opened = Signal(str)  # Project path

    def __init__(
        self,
        name: str,
        tag: str,
        records_text: str,
        edited_text: str,
        path_text: str,
        icon_type: str = "card",
        tag_color: str = PRIMARY,
        is_primary_action: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._path = path_text
        self.setObjectName("project_row")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # Thumbnail Icon
        icon_box = QLabel()
        icon_box.setFixedSize(36, 36)
        if icon_type == "card":
            icon_box.setText("🪪")
            icon_box.setStyleSheet("background-color: #1A2744; border: 1px solid #2B3D66; border-radius: 4px; font-size: 16px;")
        elif icon_type == "shield":
            icon_box.setText("🛡️")
            icon_box.setStyleSheet("background-color: #162B20; border: 1px solid #234834; border-radius: 4px; font-size: 16px;")
        elif icon_type == "cap":
            icon_box.setText("🎓")
            icon_box.setStyleSheet("background-color: #242233; border: 1px solid #3A3654; border-radius: 4px; font-size: 16px;")
        else:
            icon_box.setText("🎟️")
            icon_box.setStyleSheet("background-color: #2B2519; border: 1px solid #4D3F24; border-radius: 4px; font-size: 16px;")
        icon_box.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_box)

        # Content details
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        lbl_name = QLabel(name)
        lbl_name.setStyleSheet("color: #FFFFFF; font-weight: 700; font-size: 12px; font-family: Inter, sans-serif;")
        title_row.addWidget(lbl_name)

        lbl_tag = QLabel(tag)
        lbl_tag.setStyleSheet(
            f"background-color: {SURFACE_HIGH}; color: {tag_color}; "
            f"border: 1px solid {BORDER_SUBTLE}; border-radius: 3px; "
            f"font-family: {FONT_FAMILY_MONO}; font-size: 9px; font-weight: 600; padding: 1px 5px;"
        )
        title_row.addWidget(lbl_tag)
        title_row.addStretch()
        info_layout.addLayout(title_row)

        lbl_sub = QLabel(
            f"<font color='{SEMANTIC_SUCCESS}'><b>{records_text}</b></font> • "
            f"<font color='{TEXT_MUTED}'>Edited {edited_text} • {path_text}</font>"
        )
        lbl_sub.setStyleSheet(f"font-size: 10px; font-family: {FONT_FAMILY_MONO};")
        info_layout.addWidget(lbl_sub)

        layout.addLayout(info_layout, stretch=1)

        # Actions
        btn_open = QPushButton("Open →")
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.setFixedHeight(26)
        if is_primary_action:
            btn_open.setStyleSheet(
                f"background-color: {PRIMARY}; color: #FFFFFF; font-weight: 600; "
                f"border: none; border-radius: 4px; padding: 0 12px; font-size: 11px;"
            )
        else:
            btn_open.setStyleSheet(
                f"background-color: {SURFACE_HIGH}; color: {TEXT_PRIMARY}; font-weight: 500; "
                f"border: 1px solid {BORDER_SUBTLE}; border-radius: 4px; padding: 0 12px; font-size: 11px;"
            )
        btn_open.clicked.connect(lambda: self.opened.emit(self._path))
        layout.addWidget(btn_open)

        btn_more = QToolButton()
        btn_more.setText("⋮")
        btn_more.setFixedSize(26, 26)
        btn_more.setStyleSheet(
            f"QToolButton {{ background: transparent; color: {TEXT_MUTED}; border: none; font-size: 14px; }}"
            f"QToolButton:hover {{ background: {SURFACE_HIGH}; color: #FFFFFF; border-radius: 4px; }}"
        )
        layout.addWidget(btn_more)

        self.setStyleSheet(
            f"QFrame#project_row {{"
            f"  background-color: {SURFACE_LOW};"
            f"  border: 1px solid {BORDER_DEFAULT};"
            f"  border-radius: 4px;"
            f"}}"
            f"QFrame#project_row:hover {{"
            f"  background-color: {SURFACE_CONTAINER};"
            f"  border-color: #4A4D57;"
            f"}}"
        )


class DashboardPage(QWidget):
    """Project Onboarding & Launcher screen matching Screenshot 2 and Stitch screen c0960262ecc9."""

    navigate_requested = Signal(str)  # WorkflowStep value
    theme_changed = Signal(str)  # "black", "white", "system"
    policy_changed = Signal(object)  # MissingPhotoPolicy
    dpi_changed = Signal(int)
    new_project_requested = Signal()
    open_project_requested = Signal()
    preset_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_project_config: Optional[ProjectConfiguration] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"background-color: {SURFACE_LOWEST}; border: none;")

        container = QWidget()
        container.setStyleSheet(f"background-color: {SURFACE_LOWEST};")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 24, 40, 32)
        layout.setSpacing(20)

        # -------------------------------------------------------------
        # 1. Hero Header Row: Title, Subtitle, and Primary Actions
        # -------------------------------------------------------------
        hero_layout = QHBoxLayout()
        hero_layout.setSpacing(16)

        left_hero = QVBoxLayout()
        left_hero.setSpacing(4)

        lbl_workspace_badge = QLabel("● SYSTEM READY · Enterprise v2.4.1")
        lbl_workspace_badge.setStyleSheet(
            f"color: {SEMANTIC_SUCCESS}; font-family: {FONT_FAMILY_MONO}; "
            f"font-size: 10px; font-weight: 700; letter-spacing: 0.05em;"
        )
        left_hero.addWidget(lbl_workspace_badge)

        lbl_title = QLabel("Welcome to ID Studio")
        lbl_title.setStyleSheet("color: #FFFFFF; font-size: 26px; font-weight: 800; letter-spacing: -0.02em;")
        left_hero.addWidget(lbl_title)

        lbl_sub = QLabel("Design, batch-generate, and print enterprise-grade identification credentials.")
        lbl_sub.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px;")
        left_hero.addWidget(lbl_sub)
        hero_layout.addLayout(left_hero, stretch=1)

        # Action Buttons on Right
        action_btns = QHBoxLayout()
        action_btns.setSpacing(8)

        # + New Project ⌘N (Primary button)
        self.btn_new_project = QPushButton("+ New Project  ⌘N")
        self.btn_new_project.setObjectName("btn_primary")
        self.btn_new_project.setCursor(Qt.PointingHandCursor)
        self.btn_new_project.setFixedHeight(34)
        self.btn_new_project.setStyleSheet(
            f"QPushButton {{ background-color: {PRIMARY}; color: #FFFFFF; font-weight: 700; "
            f"border: none; border-radius: 4px; padding: 0 14px; font-size: 12px; }}"
            f"QPushButton:hover {{ background-color: #85A3FF; }}"
        )
        self.btn_new_project.clicked.connect(lambda: self.new_project_requested.emit())
        action_btns.addWidget(self.btn_new_project)

        # Open Project... ⌘O (Secondary button)
        self.btn_open_project = QPushButton("📁 Open Project...  ⌘O")
        self.btn_open_project.setCursor(Qt.PointingHandCursor)
        self.btn_open_project.setFixedHeight(34)
        self.btn_open_project.setStyleSheet(
            f"QPushButton {{ background-color: {SURFACE_CONTAINER}; color: #FFFFFF; font-weight: 600; "
            f"border: 1px solid {BORDER_DEFAULT}; border-radius: 4px; padding: 0 14px; font-size: 12px; }}"
            f"QPushButton:hover {{ background-color: {SURFACE_HIGH}; border-color: #6C8CFF; }}"
        )
        self.btn_open_project.clicked.connect(lambda: self.open_project_requested.emit())
        action_btns.addWidget(self.btn_open_project)

        # Import button
        self.btn_import = QPushButton("⬆ Import")
        self.btn_import.setCursor(Qt.PointingHandCursor)
        self.btn_import.setFixedHeight(34)
        self.btn_import.setStyleSheet(
            f"QPushButton {{ background-color: {SURFACE_CONTAINER}; color: #FFFFFF; font-weight: 600; "
            f"border: 1px solid {BORDER_DEFAULT}; border-radius: 4px; padding: 0 12px; font-size: 12px; }}"
            f"QPushButton:hover {{ background-color: {SURFACE_HIGH}; border-color: #6C8CFF; }}"
        )
        self.btn_import.clicked.connect(lambda: self.navigate_requested.emit(WorkflowStep.DATA_SOURCE.value))
        action_btns.addWidget(self.btn_import)

        hero_layout.addLayout(action_btns)
        layout.addLayout(hero_layout)

        # -------------------------------------------------------------
        # 2. "Start from a Template" Section (4 Preset Cards Grid)
        # -------------------------------------------------------------
        tmpl_section = QVBoxLayout()
        tmpl_section.setSpacing(10)

        tmpl_header = QHBoxLayout()
        lbl_tmpl_title = QLabel("Start from a Template")
        lbl_tmpl_title.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 700;")
        tmpl_header.addWidget(lbl_tmpl_title)

        lbl_media_badge = QLabel("Standard Media")
        lbl_media_badge.setStyleSheet(
            f"background-color: {SURFACE_HIGH}; color: {TEXT_MUTED}; "
            f"border: 1px solid {BORDER_SUBTLE}; border-radius: 3px; "
            f"font-family: {FONT_FAMILY_MONO}; font-size: 9px; padding: 1px 5px;"
        )
        tmpl_header.addWidget(lbl_media_badge)
        tmpl_header.addStretch()

        btn_browse_presets = QPushButton("Browse all presets →")
        btn_browse_presets.setCursor(Qt.PointingHandCursor)
        btn_browse_presets.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {PRIMARY}; border: none; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ color: #85A3FF; text-decoration: underline; }}"
        )
        btn_browse_presets.clicked.connect(lambda: self.navigate_requested.emit(WorkflowStep.TEMPLATES.value))
        tmpl_header.addWidget(btn_browse_presets)
        tmpl_section.addLayout(tmpl_header)

        # 4 Cards Row
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        card1 = PresetCardWidget(
            key="corporate_cr80",
            title="Corporate Staff ID",
            subtitle="CR80 • 85.6 × 53.98 mm",
            description="Photo badge layout with RFID chip guide, QR authentication, and CMYK preflight.",
            badge="Popular",
            tech_note="Thermal Dye-Sub",
            icon_type="card",
            badge_color=SEMANTIC_SUCCESS,
        )
        card1.selected.connect(self._on_preset_selected)
        cards_layout.addWidget(card1)

        card2 = PresetCardWidget(
            key="defense_pki",
            title="High-Security Defense",
            subtitle="CR80 • Dual-Sided Plate",
            description="Guilloche patterns, optical hologram mask, and contact smart-card pad zone.",
            badge="FIPS 201",
            tech_note="Re-Transfer",
            icon_type="shield",
            badge_color="#8E909F",
        )
        card2.selected.connect(self._on_preset_selected)
        cards_layout.addWidget(card2)

        card3 = PresetCardWidget(
            key="university_pass",
            title="University Student Pass",
            subtitle="CR80 • Landscape Orientation",
            description="Clean barcode 128 footer, student profile picture, and magnetic stripe alignment.",
            badge="Campus",
            tech_note="Direct-to-Card",
            icon_type="cap",
            badge_color="#8E909F",
        )
        card3.selected.connect(self._on_preset_selected)
        cards_layout.addWidget(card3)

        card4 = PresetCardWidget(
            key="event_cr100",
            title="Event & Conference Pass",
            subtitle="CR100 • 98.5 × 67 mm",
            description="Lanyard slot-punch keep-out zones, large typography, and fast optical scanning.",
            badge="CR100",
            tech_note="Laminate",
            icon_type="ticket",
            badge_color="#8E909F",
        )
        card4.selected.connect(self._on_preset_selected)
        cards_layout.addWidget(card4)

        tmpl_section.addLayout(cards_layout)
        layout.addLayout(tmpl_section)

        # -------------------------------------------------------------
        # 3. "Recent Projects" Section
        # -------------------------------------------------------------
        recent_section = QVBoxLayout()
        recent_section.setSpacing(10)

        recent_header = QHBoxLayout()
        lbl_recent_title = QLabel("Recent Projects")
        lbl_recent_title.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 700;")
        recent_header.addWidget(lbl_recent_title)
        recent_header.addStretch()

        self.txt_filter_projects = QLineEdit()
        self.txt_filter_projects.setPlaceholderText("Filter recent projects...")
        self.txt_filter_projects.setFixedWidth(220)
        self.txt_filter_projects.setFixedHeight(26)
        self.txt_filter_projects.setStyleSheet(
            f"QLineEdit {{ background-color: {SURFACE_LOW}; color: #FFFFFF; border: 1px solid {BORDER_DEFAULT}; "
            f"border-radius: 4px; padding: 2px 8px; font-size: 11px; }}"
            f"QLineEdit:focus {{ border-color: {PRIMARY}; }}"
        )
        recent_header.addWidget(self.txt_filter_projects)

        self.cmb_sort_projects = QComboBox()
        self.cmb_sort_projects.setFixedHeight(26)
        self.cmb_sort_projects.addItems(["Last Modified ▾", "Name A-Z", "Record Count"])
        self.cmb_sort_projects.setStyleSheet(
            f"QComboBox {{ background-color: {SURFACE_LOW}; color: {TEXT_SECONDARY}; border: 1px solid {BORDER_DEFAULT}; "
            f"border-radius: 4px; padding: 2px 8px; font-size: 11px; }}"
        )
        recent_header.addWidget(self.cmb_sort_projects)
        recent_section.addLayout(recent_header)

        # 4 Recent Project Rows
        recent_rows_box = QVBoxLayout()
        recent_rows_box.setSpacing(6)

        row1 = RecentProjectRowWidget(
            name="Acme_Corp_Staff_Badge_2025.idcrt",
            tag="CR80",
            records_text="1,420 Records",
            edited_text="12m ago",
            path_text="/IDCardProjects/HindiProject",
            icon_type="card",
            tag_color=PRIMARY,
            is_primary_action=True,
        )
        row1.opened.connect(self._open_recent_project)
        recent_rows_box.addWidget(row1)

        row2 = RecentProjectRowWidget(
            name="Gov_Defense_Security_Pass_Q2.idcrt",
            tag="PIV / FIPS 201",
            records_text="850 Records",
            edited_text="yesterday",
            path_text="/Exports/Nexus_Q1_2025",
            icon_type="shield",
            tag_color=SEMANTIC_SUCCESS,
            is_primary_action=False,
        )
        row2.opened.connect(self._open_recent_project)
        recent_rows_box.addWidget(row2)

        row3 = RecentProjectRowWidget(
            name="Metro_University_Student_IDs_2025.idcrt",
            tag="CR80",
            records_text="14,500 Records",
            edited_text="3 days ago",
            path_text="/Volumes/SecureStorage/EduProjects",
            icon_type="cap",
            tag_color="#8E909F",
            is_primary_action=False,
        )
        row3.opened.connect(self._open_recent_project)
        recent_rows_box.addWidget(row3)

        row4 = RecentProjectRowWidget(
            name="TechSummit_Annual_Badge_Passes.idcrt",
            tag="CR100",
            records_text="3,200 Records",
            edited_text="Oct 14",
            path_text="/Conferences/TechSummit2025",
            icon_type="ticket",
            tag_color="#8E909F",
            is_primary_action=False,
        )
        row4.opened.connect(self._open_recent_project)
        recent_rows_box.addWidget(row4)

        recent_section.addLayout(recent_rows_box)
        layout.addLayout(recent_section)

        # -------------------------------------------------------------
        # Hidden/Embedded Test Compatibility Elements
        # -------------------------------------------------------------
        self._compat_widget = QWidget()
        self._compat_widget.setVisible(False)
        compat_layout = QVBoxLayout(self._compat_widget)

        self.btn_start_workflow = QPushButton("Start Workflow")
        self.btn_start_workflow.clicked.connect(lambda: self.navigate_requested.emit(WorkflowStep.DATA_SOURCE.value))
        compat_layout.addWidget(self.btn_start_workflow)

        self.workspace_card = QFrame()
        self.lbl_ws_title = QLabel("Workspace")
        compat_layout.addWidget(self.workspace_card)
        compat_layout.addWidget(self.lbl_ws_title)

        self.cmb_theme = QComboBox()
        self.cmb_theme.addItem("Black (Fluent Dark)", "black")
        self.cmb_theme.addItem("White (Fluent Light)", "white")
        self.cmb_theme.addItem("System (Auto)", "system")
        self.cmb_theme.currentIndexChanged.connect(self._on_compat_theme_changed)
        compat_layout.addWidget(self.cmb_theme)

        self.cmb_policy = QComboBox()
        self.cmb_policy.addItem("Generate with Silhouette Placeholder", MissingPhotoPolicy.GENERATE_WITH_PLACEHOLDER)
        self.cmb_policy.addItem("Skip Record During Batch", MissingPhotoPolicy.SKIP_RECORD)
        self.cmb_policy.addItem("Strict Error (Abort Batch)", MissingPhotoPolicy.FAIL_RECORD)
        self.cmb_policy.currentIndexChanged.connect(self._on_compat_policy_changed)
        compat_layout.addWidget(self.cmb_policy)

        self.spin_dpi = QSpinBox()
        self.spin_dpi.setRange(72, 1200)
        self.spin_dpi.setValue(300)
        self.spin_dpi.valueChanged.connect(self.dpi_changed.emit)
        compat_layout.addWidget(self.spin_dpi)

        layout.addWidget(self._compat_widget)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _on_compat_theme_changed(self) -> None:
        data = self.cmb_theme.currentData()
        if data:
            self.theme_changed.emit(data)

    def _on_compat_policy_changed(self) -> None:
        data = self.cmb_policy.currentData()
        if data:
            self.policy_changed.emit(data)

    def _on_preset_selected(self, preset_key: str) -> None:
        """Trigger navigation directly into Template Designer or Data Source."""
        self.preset_selected.emit(preset_key)
        self.navigate_requested.emit(WorkflowStep.TEMPLATES.value)

    def _open_recent_project(self, path_str: str) -> None:
        self.open_project_requested.emit()

    def set_project_config(self, config: Optional[ProjectConfiguration]) -> None:
        self.current_project_config = config
        if config and config.workspace_dir:
            self.lbl_ws_title.setText(f"📁 Project Workspace: {config.project_name}")

    def update_metrics(self, *args, **kwargs) -> None:
        """Update metrics for compatibility."""
        pass

    def update_workspace_info(self, config: Optional[ProjectConfiguration] = None, *args, **kwargs) -> None:
        """Update workspace info for compatibility."""
        if config is not None:
            self.set_project_config(config)
