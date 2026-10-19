"""Project Hub & Onboarding launcher view featuring preset template cards, recent projects, and quick actions."""

from pathlib import Path
from typing import List, Optional
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
from id_card_generator.core.constants import APP_NAME, APP_VERSION
from id_card_generator.core.models import ProjectConfiguration
from id_card_generator.resources.resource_loader import get_projects_dir
from id_card_generator.ui.studio_tokens import COLORS, TYPOGRAPHY


class PresetCard(QFrame):
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
        icon_char: str = "🪪",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("preset_card")
        self._key = key
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # Header row: Icon + Badge
        header = QHBoxLayout()
        lbl_icon = QLabel(icon_char)
        lbl_icon.setStyleSheet("font-size: 20px;")
        header.addWidget(lbl_icon)
        header.addStretch()

        lbl_badge = QLabel(badge)
        lbl_badge.setStyleSheet(
            f"background-color: {COLORS.SURFACE_HIGHEST}; color: {COLORS.PRIMARY_CONTAINER}; "
            f"font-family: {TYPOGRAPHY.FONT_FAMILY_MONO}; font-size: 10px; font-weight: 600; "
            f"padding: 2px 6px; border-radius: 4px;"
        )
        header.addWidget(lbl_badge)
        layout.addLayout(header)

        # Titles
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(
            f"color: {COLORS.ON_SURFACE}; font-family: {TYPOGRAPHY.FONT_FAMILY_UI}; "
            f"font-size: 13px; font-weight: 700;"
        )
        layout.addWidget(lbl_title)

        lbl_sub = QLabel(subtitle)
        lbl_sub.setStyleSheet(
            f"color: {COLORS.SECONDARY}; font-family: {TYPOGRAPHY.FONT_FAMILY_MONO}; "
            f"font-size: 10px;"
        )
        layout.addWidget(lbl_sub)

        # Description
        lbl_desc = QLabel(description)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(
            f"color: {COLORS.ON_SURFACE_VARIANT}; font-size: 11px; line-height: 14px;"
        )
        layout.addWidget(lbl_desc, stretch=1)

        # Bottom Bar: Tech note + Arrow
        bottom = QHBoxLayout()
        lbl_tech = QLabel(tech_note)
        lbl_tech.setStyleSheet(
            f"color: {COLORS.TEXT_MUTED}; font-family: {TYPOGRAPHY.FONT_FAMILY_MONO}; "
            f"font-size: 10px;"
        )
        bottom.addWidget(lbl_tech)
        bottom.addStretch()

        lbl_arrow = QLabel("➔")
        lbl_arrow.setStyleSheet(f"color: {COLORS.PRIMARY_CONTAINER}; font-size: 13px;")
        bottom.addWidget(lbl_arrow)
        layout.addLayout(bottom)

        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"QFrame#preset_card {{"
            f"  background-color: {COLORS.SURFACE_CONTAINER};"
            f"  border: 1px solid {COLORS.BORDER_HAIRLINE};"
            f"  border-radius: 6px;"
            f"}}"
            f"QFrame#preset_card:hover {{"
            f"  background-color: {COLORS.SURFACE_HIGH};"
            f"  border-color: {COLORS.PRIMARY_CONTAINER};"
            f"}}"
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.selected.emit(self._key)
        super().mousePressEvent(event)


class ProjectHubView(QWidget):
    """Screen c0960262ecc9: Project Hub & Onboarding Launcher."""

    new_project_requested = Signal(str)  # Preset key or "blank"
    open_project_requested = Signal()
    import_spreadsheet_requested = Signal()
    project_selected = Signal(Path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("project_hub_view")
        self._setup_ui()

    def _setup_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 28, 36, 32)
        layout.setSpacing(24)

        # 1. Hero Header Banner
        hero_layout = QVBoxLayout()
        hero_layout.setSpacing(6)

        lbl_hero_badge = QLabel("STUDIO ONBOARDING & WORKSPACE LAUNCHER")
        lbl_hero_badge.setStyleSheet(
            f"color: {COLORS.PRIMARY_CONTAINER}; font-family: {TYPOGRAPHY.FONT_FAMILY_MONO}; "
            f"font-size: 10px; font-weight: bold; letter-spacing: 0.05em;"
        )
        hero_layout.addWidget(lbl_hero_badge)

        lbl_hero_title = QLabel("Credential Studio Workstation")
        lbl_hero_title.setStyleSheet(
            f"color: {COLORS.ON_SURFACE}; font-family: {TYPOGRAPHY.FONT_FAMILY_UI}; "
            f"font-size: 22px; font-weight: 700; letter-spacing: -0.02em;"
        )
        hero_layout.addWidget(lbl_hero_title)

        lbl_hero_sub = QLabel(
            "Batch-render high-resolution photo ID badges, security credentials, and multi-up print imposition sheets from Excel data."
        )
        lbl_hero_sub.setStyleSheet(
            f"color: {COLORS.ON_SURFACE_VARIANT}; font-size: 12px;"
        )
        hero_layout.addWidget(lbl_hero_sub)
        layout.addLayout(hero_layout)

        # 2. Quick Action Bar
        action_bar = QFrame()
        action_bar.setObjectName("card_panel")
        ab_layout = QHBoxLayout(action_bar)
        ab_layout.setContentsMargins(14, 12, 14, 12)
        ab_layout.setSpacing(10)

        lbl_quick = QLabel("<b>⚡ Quick Actions:</b>")
        lbl_quick.setStyleSheet(f"color: {COLORS.ON_SURFACE}; font-size: 12px;")
        ab_layout.addWidget(lbl_quick)

        self.btn_new = QPushButton("New Blank Workspace")
        self.btn_new.setObjectName("btn_primary")
        self.btn_new.clicked.connect(lambda: self.new_project_requested.emit("blank"))
        ab_layout.addWidget(self.btn_new)

        self.btn_open = QPushButton("Open Workspace...")
        self.btn_open.clicked.connect(self.open_project_requested.emit)
        ab_layout.addWidget(self.btn_open)

        self.btn_import = QPushButton("Import Excel / CSV...")
        self.btn_import.clicked.connect(self.import_spreadsheet_requested.emit)
        ab_layout.addWidget(self.btn_import)

        ab_layout.addStretch()
        layout.addWidget(action_bar)

        # 3. Enterprise Template Presets Section
        presets_box = QVBoxLayout()
        presets_box.setSpacing(10)

        lbl_sec1 = QLabel("ENTERPRISE CREDENTIAL PRESETS")
        lbl_sec1.setStyleSheet(
            f"color: {COLORS.TEXT_MUTED}; font-family: {TYPOGRAPHY.FONT_FAMILY_MONO}; "
            f"font-size: 10px; font-weight: bold; letter-spacing: 0.05em;"
        )
        presets_box.addWidget(lbl_sec1)

        grid = QGridLayout()
        grid.setSpacing(12)

        # Preset 1: Corporate Staff Badge CR80
        p1 = PresetCard(
            key="corporate_cr80",
            title="Corporate Staff Badge",
            subtitle="ISO/IEC 7810 CR80 Standard",
            description="85.60 × 53.98 mm • 300 DPI layout with portrait headshot frame, QR authentication vector, and dynamic text fields.",
            badge="Most Popular",
            tech_note="Thermal Dye-Sub",
            icon_char="🪪",
        )
        p1.selected.connect(self.new_project_requested.emit)
        grid.addWidget(p1, 0, 0)

        # Preset 2: High-Security Defense ID
        p2 = PresetCard(
            key="high_security",
            title="High-Security Defense ID",
            subtitle="CR80 Dual-Sided Secure Plate",
            description="Guilloche security background wave pattern, optical holographic overlay plate, Level 4 clearance color band, and barcode.",
            badge="FIPS 201 / PIV",
            tech_note="Dual Re-Transfer",
            icon_char="🛡️",
        )
        p2.selected.connect(self.new_project_requested.emit)
        grid.addWidget(p2, 0, 1)

        # Preset 3: A4 Multi-Badge Imposition
        p3 = PresetCard(
            key="a4_imposition",
            title="A4 Multi-Badge Imposition",
            subtitle="8-Up Duplex Sheet (210×297 mm)",
            description="Commercial press layout with automated 3mm bleed margins, crop marks, registration crosshairs & CMYK color wedges.",
            badge="Prepress Ready",
            tech_note="Offset / Indigo",
            icon_char="📑",
        )
        p3.selected.connect(self.new_project_requested.emit)
        grid.addWidget(p3, 1, 0)

        # Preset 4: Visitor & Event Pass CR100
        p4 = PresetCard(
            key="visitor_cr100",
            title="Visitor & Event Pass",
            subtitle="CR100 Oversized (98.5×67 mm)",
            description="High-throughput conference pass layout with bold attendee designation, schedule QR token, and sponsor brand block.",
            badge="High-Throughput",
            tech_note="Direct-to-Card",
            icon_char="🎟️",
        )
        p4.selected.connect(self.new_project_requested.emit)
        grid.addWidget(p4, 1, 1)

        presets_box.addLayout(grid)
        layout.addLayout(presets_box)

        # 4. Recent Project Workspaces Section
        recents_box = QVBoxLayout()
        recents_box.setSpacing(10)

        lbl_sec2 = QLabel("RECENT WORKSPACES")
        lbl_sec2.setStyleSheet(
            f"color: {COLORS.TEXT_MUTED}; font-family: {TYPOGRAPHY.FONT_FAMILY_MONO}; "
            f"font-size: 10px; font-weight: bold; letter-spacing: 0.05em;"
        )
        recents_box.addWidget(lbl_sec2)

        self.recents_container = QFrame()
        self.recents_container.setObjectName("card_panel")
        self.recents_layout = QVBoxLayout(self.recents_container)
        self.recents_layout.setContentsMargins(14, 12, 14, 12)
        self.recents_layout.setSpacing(6)

        self.lbl_no_recents = QLabel("<i>No recent projects found. Create a new workspace above to begin.</i>")
        self.lbl_no_recents.setStyleSheet(f"color: {COLORS.TEXT_MUTED}; font-size: 12px;")
        self.recents_layout.addWidget(self.lbl_no_recents)

        recents_box.addWidget(self.recents_container)
        layout.addLayout(recents_box)
        layout.addStretch()

        scroll_layout = QVBoxLayout(self)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.addWidget(scroll)

        self.load_recent_projects()

    def load_recent_projects(self) -> None:
        """Scan standard projects directory for existing workspace project.json files."""
        proj_dir = get_projects_dir()
        projects: List[Path] = []
        if proj_dir.exists():
            for p in proj_dir.glob("*/project.json"):
                projects.append(p)

        if not projects:
            return

        self.lbl_no_recents.setVisible(False)
        for proj_path in sorted(projects, key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
            row = QFrame()
            row.setCursor(Qt.PointingHandCursor)
            row.setStyleSheet(
                f"QFrame {{ background-color: {COLORS.SURFACE_LOW}; border-radius: 4px; padding: 6px; }}"
                f"QFrame:hover {{ background-color: {COLORS.SURFACE_HIGH}; }}"
            )
            r_layout = QHBoxLayout(row)
            r_layout.setContentsMargins(8, 4, 8, 4)

            lbl_folder = QLabel("📁")
            lbl_folder.setStyleSheet("font-size: 14px;")
            r_layout.addWidget(lbl_folder)

            lbl_name = QLabel(f"<b>{proj_path.parent.name}</b>")
            lbl_name.setStyleSheet(f"color: {COLORS.ON_SURFACE}; font-size: 12px;")
            r_layout.addWidget(lbl_name)

            lbl_path = QLabel(str(proj_path.parent))
            lbl_path.setStyleSheet(
                f"color: {COLORS.TEXT_MUTED}; font-family: {TYPOGRAPHY.FONT_FAMILY_MONO}; font-size: 10px;"
            )
            r_layout.addWidget(lbl_path, stretch=1)

            btn_open_item = QPushButton("Open")
            btn_open_item.setFixedHeight(22)
            btn_open_item.clicked.connect(lambda ch=False, p=proj_path: self.project_selected.emit(p))
            r_layout.addWidget(btn_open_item)

            self.recents_layout.addWidget(row)
