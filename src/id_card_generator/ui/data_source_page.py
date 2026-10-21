"""Data source import and interactive record preview page.

The screen is the Excel & CSV connector of the Stitch design
(``bd2f3aebf3bb``) and is built as a three column workstation:

* the left column lists the placeholders of the active template with their
  mapping state and whether they are required,
* the centre column shows the connection state of the spreadsheet, the
  mapping tools and a virtual table with the imported records,
* the right column is the column mapping inspector: the source column with
  its inferred type, the transliteration, the photo lookup and the policy
  for missing photographs.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from id_card_generator.core.constants import MissingPhotoPolicy, WorkflowStep
from id_card_generator.core.models import (
    ProjectConfiguration,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.core.project_manager import ProjectManager
from id_card_generator.data.data_validator import DataValidator, ValidationReport
from id_card_generator.data.excel_importer import ExcelImporter
from id_card_generator.data.hindi_converter import HindiConverter
from id_card_generator.ui import workflow
from id_card_generator.ui.components.column_filter import open_column_filter_menu
from id_card_generator.ui.components.elided_label import ElidedLabel
from id_card_generator.ui.components.layout_blocks import OverflowMenu, StatLine
from id_card_generator.ui.components.page_scaffold import InlineNotice, PageFooter, PageHeader
from id_card_generator.ui.components.record_table import RecordTableModel
from id_card_generator.ui.components.status_pill import StatusPill
from id_card_generator.ui.studio_tokens import SIZES
from id_card_generator.ui.studio_tokens import (
    BORDER_DEFAULT,
    BORDER_SUBTLE,
    FONT_FAMILY_MONO,
    PRIMARY,
    SEMANTIC_ERROR,
    SEMANTIC_SUCCESS,
    SEMANTIC_WARNING,
    SURFACE_CONTAINER,
    SURFACE_HIGH,
    SURFACE_LOW,
    SURFACE_LOWEST,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


def _wrap(layout) -> QWidget:
    """Host a layout inside a plain widget."""
    holder = QWidget()
    holder.setProperty("role", "flat")
    holder.setLayout(layout)
    return holder

# Every control in a row uses the same height as the rest of the app.
CONTROL_HEIGHT = SIZES.CONTROL_HEIGHT

# The placeholders that a card cannot do without.
DEFAULT_REQUIRED_TOKENS = ("pin_number", "photo", "employee_name")


class PlaceholderRow(QWidget):
    """One row of the placeholder list: the token, its state and its tag."""

    def __init__(
        self,
        token: str,
        mapped_column: str = "",
        required: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setProperty("role", "flat")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(6)

        name = QLabel(f"{{{{{token}}}}}")
        name.setProperty("role", "specValue")
        top.addWidget(name)

        top.addStretch()

        tag = QLabel("REQ" if required else "OPT")
        tag.setProperty("role", "badgeAccent" if required else "badgeMuted")
        top.addWidget(tag)

        layout.addLayout(top)

        if mapped_column:
            state = QLabel(f"Mapped → {mapped_column}")
            state.setProperty("role", "specKey")
        else:
            state = QLabel("Not mapped")
            state.setStyleSheet(f"color: {SEMANTIC_WARNING}; font-size: 11px;")
        layout.addWidget(state)


class DataSourcePage(QWidget):
    """Import spreadsheet, configure sheet/headers, validate rows, and preview data."""

    data_loaded = Signal(object, object, object)  # (columns, records, validation_report)
    navigate_requested = Signal(str)  # WorkflowStep value
    mappings_changed = Signal(dict)  # token -> column mapping dict
    photo_lookup_changed = Signal(str)  # the column the photos are looked up by
    photo_policy_changed = Signal(object)  # MissingPhotoPolicy

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_config: Optional[ProjectConfiguration] = None
        self.current_file_path: Optional[Path] = None
        self.columns: List[str] = []
        self.records: List[SourceRecord] = []
        self.validation_report: Optional[ValidationReport] = None
        self.field_mappings: Dict[str, str] = {}
        self.template_tokens: List[str] = ["pin_number", "employee_name", "department", "designation", "photo"]
        self.column_types: Dict[str, str] = {}
        self.token_required: Dict[str, bool] = {}
        self.photo_lookup_column: str = ""
        self._error_count = 0

        self._setup_ui()

    def set_project_config(self, config: Optional[ProjectConfiguration]) -> None:
        """Associate active project workspace configuration."""
        self.project_config = config
        if config and config.workspace_dir and config.excel_file_path:
            p = Path(config.excel_file_path)
            if p.exists():
                self.lbl_workspace_badge.setText(f"✓ Stored in Workspace: data/{p.name}")
                self.lbl_workspace_badge.setVisible(True)

    def set_template(self, template: Optional[TemplateDefinition]) -> None:
        """Extract placeholder tokens from active template elements."""
        if not template:
            return
        tokens = set()
        for elem in template.elements:
            if getattr(elem, "field_name", None):
                tokens.add(elem.field_name.strip("{}"))
            if getattr(elem, "text", None):
                # Search for {{token}} in text
                found = re.findall(r"\{\{([^}]+)\}\}", elem.text)
                for f in found:
                    tokens.add(f.strip())
        if tokens:
            self.template_tokens = sorted(list(tokens))
            self._refresh_placeholders_list()

    def setup_ui(self) -> None:
        """Alias kept for the older call sites."""
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---------------------------------------------------------
        # 0. Page Header (step badge, title, contextual actions)
        # ---------------------------------------------------------
        badge, title, subtitle = workflow.page_header_text(WorkflowStep.DATA_SOURCE)
        # The page header block is removed from the shell (its actions live in
        # the app menu bar now).  Kept off-canvas as a state mirror for tests.
        self.page_header = PageHeader(title, subtitle, badge, parent=self)
        self.page_header.hide()

        # Non blocking feedback area (errors / warnings stay in context).
        self.notice = InlineNotice()
        notice_row = QHBoxLayout()
        notice_row.setContentsMargins(16, 8, 16, 0)
        notice_row.addWidget(self.notice)
        main_layout.addLayout(notice_row)

        body = QVBoxLayout()
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(10)
        main_layout.addLayout(body, stretch=1)

        # ---------------------------------------------------------
        # 1. Source bar: the file, one primary action, a quiet stat line
        # ---------------------------------------------------------
        top_card = QFrame()
        top_card.setObjectName("card_panel")
        top_layout = QVBoxLayout(top_card)
        top_layout.setContentsMargins(14, 10, 14, 10)
        top_layout.setSpacing(10)

        file_row = QHBoxLayout()
        file_row.setSpacing(10)

        # The row reads from action to state: the primary import leads the
        # row on the left, the overflow tools follow, and the connection
        # state closes it on the right.
        self.btn_browse = QPushButton("Import Spreadsheet...")
        self.btn_browse.setObjectName("btn_primary")
        self.btn_browse.setFixedHeight(CONTROL_HEIGHT)
        self.btn_browse.clicked.connect(self._browse_file)
        file_row.addWidget(self.btn_browse)

        # Everything secondary lives in the overflow menu.
        self.btn_more = OverflowMenu("More data source actions")
        self.btn_more.add_action("Re-import", self._reimport_data)
        self.btn_more.add_action("Auto-map columns", self._auto_map_columns)
        self.btn_more.add_action("Validate all records", self._validate_all_records)
        file_row.addWidget(self.btn_more)

        self.lbl_path = QLabel("No spreadsheet connected")
        self.lbl_path.setProperty("role", "monoMuted")
        file_row.addWidget(self.lbl_path, stretch=1)

        self.pill_connection = StatusPill("NO DATA", color=TEXT_MUTED)
        file_row.addWidget(self.pill_connection)

        top_layout.addLayout(file_row)

        # The metric pills become one quiet line of numbers.
        self.stat_line = StatLine()
        top_layout.addWidget(self.stat_line)

        # The legacy buttons stay available for the existing API.
        self.btn_refresh = QPushButton("Re-import")
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.clicked.connect(self._reimport_data)
        self.btn_refresh.setVisible(False)
        top_layout.addWidget(self.btn_refresh)

        # The metric pills stay available for the API, but the interface only
        # shows the quiet numbers of the stat line.
        self.pill_placeholders = StatusPill("TOKENS: 0", color=PRIMARY)
        self.pill_mapped = StatusPill("MAPPED: 0", color=SEMANTIC_SUCCESS)
        self.pill_unmapped = StatusPill("UNMAPPED: 0", color=SEMANTIC_WARNING)
        self.pill_records = StatusPill("RECORDS: 0", color=TEXT_SECONDARY)
        self.pill_errors = StatusPill("ERRORS: 0", color=SEMANTIC_ERROR)

        for pill in (
            self.pill_placeholders,
            self.pill_mapped,
            self.pill_unmapped,
            self.pill_records,
            self.pill_errors,
        ):
            pill.setVisible(False)

        self.lbl_workspace_badge = QLabel("")
        self.lbl_workspace_badge.setProperty("role", "pageSubtitle")
        self.lbl_workspace_badge.setVisible(False)
        top_layout.addWidget(self.lbl_workspace_badge)

        self.lbl_hindi_badge = QLabel("")
        self.lbl_hindi_badge.setProperty("role", "pageSubtitle")
        self.lbl_hindi_badge.setVisible(False)
        top_layout.addWidget(self.lbl_hindi_badge)

        body.addWidget(top_card)

        # ---------------------------------------------------------
        # 2. Main 3-Column Workstation Splitter (flipped: the mapping
        #    inspector leads on the left, the placeholders close the
        #    row on the right)
        # ---------------------------------------------------------
        self.main_splitter = QSplitter(Qt.Horizontal)

        # --- TEMPLATE PLACEHOLDERS COLUMN (closes the row on the right) ---
        left_panel = QFrame()
        left_panel.setObjectName("workspace_panel")
        left_panel.setMinimumWidth(200)
        left_panel.setMaximumWidth(340)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        lbl_tokens_title = QLabel("TEMPLATE PLACEHOLDERS")
        lbl_tokens_title.setProperty("role", "sectionLabel")
        left_layout.addWidget(lbl_tokens_title)

        lbl_tokens_sub = QLabel("Select a token to map it to a column")
        lbl_tokens_sub.setProperty("role", "specKey")
        left_layout.addWidget(lbl_tokens_sub)

        self.list_placeholders = QListWidget()
        self.list_placeholders.setStyleSheet(
            f"QListWidget {{ background: {SURFACE_LOWEST}; border: 1px solid {BORDER_SUBTLE}; color: {TEXT_PRIMARY}; font-size: 11px; }}"
            f"QListWidget::item {{ padding: 0px; border-bottom: 1px solid {BORDER_SUBTLE}; }}"
            f"QListWidget::item:selected {{ background-color: {SURFACE_HIGH}; color: {PRIMARY}; }}"
        )
        self.list_placeholders.itemClicked.connect(self._on_placeholder_clicked)
        left_layout.addWidget(self.list_placeholders)

        self.lbl_token_summary = QLabel("")
        self.lbl_token_summary.setProperty("role", "specKey")
        left_layout.addWidget(self.lbl_token_summary)

        # --- CENTER COLUMN: Spreadsheet Controls & Data Preview Table ---
        center_panel = QFrame()
        center_panel.setObjectName("workspace_panel")
        self.center_layout = QVBoxLayout(center_panel)
        self.center_layout.setContentsMargins(8, 8, 8, 8)
        self.center_layout.setSpacing(8)

        # The connection state of the spreadsheet.
        self.lbl_connection = QLabel("Not connected")
        self.lbl_connection.setProperty("role", "cardTitle")
        self.center_layout.addWidget(self.lbl_connection)

        # Controls sub-bar (Worksheet, Header row, Hindi mode, Search)
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setSpacing(6)

        self.cmb_sheets = QComboBox()
        self.cmb_sheets.setPlaceholderText("Sheet")
        self.cmb_sheets.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_sheets.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.cmb_sheets.setMinimumContentsLength(8)
        self.cmb_sheets.currentIndexChanged.connect(self._on_sheet_changed)
        ctrl_bar.addWidget(self.cmb_sheets)

        self.spin_header = QSpinBox()
        self.spin_header.setRange(0, 100)
        self.spin_header.setValue(0)
        self.spin_header.setPrefix("Header ")
        self.spin_header.setFixedHeight(CONTROL_HEIGHT)
        self.spin_header.valueChanged.connect(self._on_header_changed)
        ctrl_bar.addWidget(self.spin_header)

        self.cmb_hindi_mode = QComboBox()
        self.cmb_hindi_mode.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.cmb_hindi_mode.setMinimumContentsLength(10)
        self.cmb_hindi_mode.addItem("Auto-detect Hindi", "auto")
        self.cmb_hindi_mode.addItem("Kruti Dev → Unicode", "kruti_to_unicode")
        self.cmb_hindi_mode.addItem("Chanakya → Unicode", "chanakya_to_unicode")
        self.cmb_hindi_mode.addItem("Unicode / Mangal", "none")
        self.cmb_hindi_mode.setToolTip(
            "Auto-detect reads the legacy font of the cell.\n"
            "Kruti Dev and Chanakya are converted with the shared legacy "
            "Devanagari mapping.\n"
            "Unicode / Mangal keeps the text as it is."
        )
        self.cmb_hindi_mode.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_hindi_mode.currentIndexChanged.connect(self._on_hindi_mode_changed)
        ctrl_bar.addWidget(self.cmb_hindi_mode)

        ctrl_bar.addStretch()

        # The two mapping tools of the plan.
        self.btn_automap = QPushButton("✦ Auto-map columns")
        self.btn_automap.setToolTip(
            "Automatically map spreadsheet columns to template placeholders by name similarity"
        )
        self.btn_automap.setObjectName("btn_secondary")
        self.btn_automap.setFixedHeight(CONTROL_HEIGHT)
        self.btn_automap.clicked.connect(self._auto_map_columns)
        ctrl_bar.addWidget(self.btn_automap)

        self.btn_validate = QPushButton("Validate all")
        self.btn_validate.setToolTip("Run strict validation checks across all records")
        self.btn_validate.setObjectName("btn_secondary")
        self.btn_validate.setFixedHeight(CONTROL_HEIGHT)
        self.btn_validate.clicked.connect(self._validate_all_records)
        ctrl_bar.addWidget(self.btn_validate)

        # The row of the controls scrolls when the window is too narrow,
        # otherwise the whole page would be wider than the screen.
        self.ctrl_scroll = QScrollArea()
        self.ctrl_scroll.setWidgetResizable(True)
        self.ctrl_scroll.setFrameShape(QFrame.NoFrame)
        self.ctrl_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.ctrl_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.ctrl_scroll.setMinimumHeight(CONTROL_HEIGHT + 8)
        # The row of the controls takes the room it needs - a scroll area
        # would otherwise grow over the whole column and push the table of
        # the records to the bottom.
        self.ctrl_scroll.setFixedHeight(CONTROL_HEIGHT + 8)
        self.ctrl_scroll.setWidget(_wrap(ctrl_bar))
        self.ctrl_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        self.center_layout.addWidget(self.ctrl_scroll)

        # Search & Summary Bar
        search_bar = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter records (name, PIN, designation, dept)...")
        self.txt_search.setProperty("role", "fieldFlat")
        self.txt_search.setFixedHeight(CONTROL_HEIGHT)
        self.txt_search.setMinimumWidth(220)
        self.txt_search.textChanged.connect(self._filter_table)
        search_bar.addWidget(self.txt_search, stretch=1)

        self.lbl_summary = ElidedLabel("0 records loaded")
        self.lbl_summary.setProperty("role", "specKey")
        self.lbl_summary.setMinimumWidth(120)
        # The summary may not push the field out of the column.
        self.lbl_summary.setMaximumWidth(320)
        search_bar.addWidget(self.lbl_summary)
        self.center_layout.addLayout(search_bar)

        # Data Table
        self.record_model = RecordTableModel(self)
        self.table = QTableView()
        self.table.setModel(self.record_model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.selectionModel().selectionChanged.connect(
            lambda selected, deselected: self._on_row_selected()
        )
        self.table.horizontalHeader().sectionClicked.connect(self._on_column_clicked)
        self.table.setMinimumWidth(180)
        self.table.setStyleSheet(
            f"QTableView {{ background-color: {SURFACE_LOWEST}; alternate-background-color: {SURFACE_LOW};"
            f" gridline-color: {BORDER_SUBTLE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SUBTLE}; }}"
            f"QHeaderView::section {{ background-color: {SURFACE_HIGH}; color: {TEXT_SECONDARY}; border: 1px solid {BORDER_SUBTLE};"
            f" padding: 4px; font-weight: 600; font-size: 11px; }}"
        )
        self.center_layout.addWidget(self.table)

        # --- MAPPING & RECORD INSPECTOR COLUMN (leads the row on the left) ---
        right_panel = QFrame()
        right_panel.setObjectName("workspace_panel")
        right_panel.setMinimumWidth(250)
        right_panel.setMaximumWidth(380)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(6)

        self.right_tabs = QTabWidget()
        self.right_tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {BORDER_SUBTLE}; background-color: {SURFACE_LOW}; }}"
            f"QTabBar::tab {{ background: {SURFACE_LOWEST}; color: {TEXT_SECONDARY}; padding: 6px 10px; font-size: 11px; border: 1px solid {BORDER_SUBTLE}; }}"
            f"QTabBar::tab:selected {{ background: {SURFACE_HIGH}; color: {PRIMARY}; border-bottom: 2px solid {PRIMARY}; }}"
        )

        # Tab 1: Field Mapping & Rules Inspector
        tab_mapping = QWidget()
        mapping_outer = QVBoxLayout(tab_mapping)
        mapping_outer.setContentsMargins(0, 0, 0, 0)
        mapping_outer.setSpacing(0)

        mapping_scroll = QScrollArea()
        mapping_scroll.setWidgetResizable(True)
        mapping_scroll.setFrameShape(QFrame.NoFrame)
        mapping_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        mapping_content = QWidget()
        mapping_content.setProperty("role", "flat")
        mapping_layout = QVBoxLayout(mapping_content)
        mapping_layout.setContentsMargins(8, 8, 8, 8)
        mapping_layout.setSpacing(8)

        lbl_map_head = QLabel("TARGET PLACEHOLDER")
        lbl_map_head.setProperty("role", "sectionLabel")
        mapping_layout.addWidget(lbl_map_head)

        self.lbl_active_token = QLabel("{{pin_number}}")
        self.lbl_active_token.setProperty("role", "specValue")
        self.lbl_active_token.setStyleSheet(f"color: {PRIMARY}; font-weight: 600;")
        mapping_layout.addWidget(self.lbl_active_token)

        self.lbl_token_detail = QLabel("")
        self.lbl_token_detail.setProperty("role", "specKey")
        self.lbl_token_detail.setWordWrap(True)
        mapping_layout.addWidget(self.lbl_token_detail)

        lbl_col_head = QLabel("SOURCE COLUMN")
        lbl_col_head.setProperty("role", "sectionLabel")
        mapping_layout.addWidget(lbl_col_head)

        self.cmb_source_column = QComboBox()
        self.cmb_source_column.setPlaceholderText("Spreadsheet column")
        self.cmb_source_column.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_source_column.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.cmb_source_column.setMinimumContentsLength(12)
        self.cmb_source_column.currentIndexChanged.connect(self._on_source_column_changed)
        mapping_layout.addWidget(self.cmb_source_column)

        self.lbl_column_type = QLabel("")
        self.lbl_column_type.setProperty("role", "specKey")
        mapping_layout.addWidget(self.lbl_column_type)

        self.btn_apply_mapping = QPushButton("Apply mapping")
        self.btn_apply_mapping.setObjectName("btn_primary")
        self.btn_apply_mapping.setFixedHeight(CONTROL_HEIGHT)
        self.btn_apply_mapping.clicked.connect(self._apply_current_mapping)
        mapping_layout.addWidget(self.btn_apply_mapping)

        # The rare settings live behind a toggle.
        self.btn_rules = QPushButton("⋯  Field rules")
        self.btn_rules.setObjectName("btn_ghost")
        self.btn_rules.setFixedHeight(CONTROL_HEIGHT)
        self.btn_rules.setToolTip("Show the fallback, overflow and conversion rules")
        self.btn_rules.clicked.connect(self._toggle_rules)
        mapping_layout.addWidget(self.btn_rules)

        self.rules_box = QWidget()
        self.rules_box.setProperty("role", "flat")
        rules_layout = QVBoxLayout(self.rules_box)
        rules_layout.setContentsMargins(0, 4, 0, 0)
        rules_layout.setSpacing(8)

        self.txt_fallback = QLineEdit()
        self.txt_fallback.setPlaceholderText("Fallback value")
        self.txt_fallback.setFixedHeight(CONTROL_HEIGHT)
        self.txt_fallback.setProperty("role", "fieldFlat")
        rules_layout.addWidget(self.txt_fallback)

        self.cmb_overflow = QComboBox()
        self.cmb_overflow.addItem("Auto-shrink font size")
        self.cmb_overflow.addItem("Truncate with ellipsis")
        self.cmb_overflow.addItem("Multi-line wrap")
        self.cmb_overflow.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_overflow.setToolTip(
            "How the text is fitted into its frame when the card is rendered.\n"
            "The canvas always shows the size of the font."
        )
        rules_layout.addWidget(self.cmb_overflow)

        self.chk_required = QCheckBox("Required field")
        self.chk_required.setChecked(True)
        self.chk_required.toggled.connect(self._on_required_toggled)
        rules_layout.addWidget(self.chk_required)

        self.chk_convert_hindi = QCheckBox("Convert KrutiDev / Chanakya")
        self.chk_convert_hindi.setChecked(True)
        rules_layout.addWidget(self.chk_convert_hindi)

        self.rules_box.setVisible(False)
        mapping_layout.addWidget(self.rules_box)

        # --- Photo lookup ---
        lbl_photo_head = QLabel("PHOTO LOOKUP")
        lbl_photo_head.setProperty("role", "sectionLabel")
        mapping_layout.addWidget(lbl_photo_head)

        self.cmb_photo_lookup = QComboBox()
        self.cmb_photo_lookup.addItem("Auto-detect (PIN / ID)", "")
        self.cmb_photo_lookup.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_photo_lookup.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.cmb_photo_lookup.setMinimumContentsLength(12)
        self.cmb_photo_lookup.currentIndexChanged.connect(self._on_photo_lookup_changed)
        mapping_layout.addWidget(self.cmb_photo_lookup)

        self.lbl_photo_stats = QLabel("No photos matched yet.")
        self.lbl_photo_stats.setProperty("role", "specKey")
        self.lbl_photo_stats.setWordWrap(True)
        mapping_layout.addWidget(self.lbl_photo_stats)

        # --- Missing photo policy ---
        lbl_policy_head = QLabel("MISSING PHOTO POLICY")
        lbl_policy_head.setProperty("role", "sectionLabel")
        mapping_layout.addWidget(lbl_policy_head)

        self.cmb_photo_policy = QComboBox()
        self.cmb_photo_policy.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.cmb_photo_policy.setMinimumContentsLength(12)
        self.cmb_photo_policy.addItem(
            "Default avatar placeholder", MissingPhotoPolicy.GENERATE_WITH_PLACEHOLDER
        )
        self.cmb_photo_policy.addItem(
            "Skip the record", MissingPhotoPolicy.SKIP_RECORD
        )
        self.cmb_photo_policy.addItem(
            "Fail the generation", MissingPhotoPolicy.FAIL_RECORD
        )
        self.cmb_photo_policy.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_photo_policy.currentIndexChanged.connect(self._on_photo_policy_changed)
        mapping_layout.addWidget(self.cmb_photo_policy)

        mapping_layout.addStretch()

        mapping_scroll.setWidget(mapping_content)
        mapping_outer.addWidget(mapping_scroll)
        self.right_tabs.addTab(tab_mapping, "Mapping")

        # Tab 2: Selected Record Inspector (preserves self.inspector & self.lbl_inspect_details)
        self.inspector = QFrame()
        self.inspector.setObjectName("card_panel")
        insp_layout = QVBoxLayout(self.inspector)
        insp_layout.setContentsMargins(8, 8, 8, 8)
        insp_layout.setSpacing(6)

        lbl_rec_title = QLabel("RECORD")
        lbl_rec_title.setProperty("role", "sectionLabel")
        insp_layout.addWidget(lbl_rec_title)

        self.lbl_inspect_details = QLabel("<i>Select a row in the table to inspect all attributes.</i>")
        self.lbl_inspect_details.setWordWrap(True)
        self.lbl_inspect_details.setProperty("role", "specValue")
        insp_layout.addWidget(self.lbl_inspect_details)
        insp_layout.addStretch()

        self.right_tabs.addTab(self.inspector, "Record")
        right_layout.addWidget(self.right_tabs)

        # The workstation is flipped: mapping inspector on the left edge
        # (next to the import actions), data table holds the middle, and
        # the template placeholder list closes the row on the right edge.
        self.main_splitter.addWidget(right_panel)
        self.main_splitter.addWidget(center_panel)
        self.main_splitter.addWidget(left_panel)

        # Splitter Initial Proportions: Mapping ~320, Center ~620, Placeholders ~280
        self.main_splitter.setSizes([320, 620, 280])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        body.addWidget(self.main_splitter, stretch=1)

        # ---------------------------------------------------------
        # 3. Bottom Step Navigation Bar (drives the pipeline)
        # ---------------------------------------------------------
        back_label, next_label, badge = workflow.footer_labels(WorkflowStep.DATA_SOURCE)
        self.nav_bar = PageFooter(
            prev_label=back_label,
            next_label=next_label,
            step_badge=badge,
            parent=self,
        )
        self.nav_bar.back_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.DASHBOARD.value))
        self.nav_bar.next_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.PHOTOS.value))
        main_layout.addWidget(self.nav_bar)

        self._refresh_placeholders_list()

    # -----------------------------------------------------------------
    # Placeholders
    # -----------------------------------------------------------------
    def _is_required(self, token: str) -> bool:
        """True when the token has to be mapped."""
        if token in self.token_required:
            return self.token_required[token]
        return token in DEFAULT_REQUIRED_TOKENS

    def _refresh_placeholders_list(self) -> None:
        """Populate left placeholder list."""
        self.list_placeholders.clear()
        mapped_count = 0

        for token in self.template_tokens:
            mapped_column = self.field_mappings.get(token, "")
            if mapped_column:
                mapped_count += 1

            item = QListWidgetItem()
            item.setData(Qt.UserRole, token)
            row = PlaceholderRow(
                token=token,
                mapped_column=mapped_column,
                required=self._is_required(token),
            )
            self.list_placeholders.addItem(item)
            self.list_placeholders.setItemWidget(item, row)
            # The row is drawn by a widget, so the item needs its size.
            item.setSizeHint(row.sizeHint())

        self.pill_placeholders.set_status(f"TOKENS: {len(self.template_tokens)}", color=PRIMARY)
        self.pill_mapped.set_status(f"MAPPED: {mapped_count}", color=SEMANTIC_SUCCESS if mapped_count > 0 else TEXT_MUTED)
        unmapped = len(self.template_tokens) - mapped_count
        self.pill_unmapped.set_status(f"UNMAPPED: {unmapped}", color=SEMANTIC_WARNING if unmapped > 0 else SEMANTIC_SUCCESS)

        self.lbl_token_summary.setText(
            f"{mapped_count} of {len(self.template_tokens)} placeholders mapped"
        )

        self._refresh_stat_line()

    def _refresh_stat_line(self) -> None:
        """Refresh the quiet line of numbers below the source bar."""
        mapped_count = sum(
            1 for token in self.template_tokens if self.field_mappings.get(token)
        )
        unmapped = len(self.template_tokens) - mapped_count
        self.stat_line.set_stats([
            ("Fields", len(self.template_tokens)),
            ("Mapped", mapped_count, SEMANTIC_SUCCESS if mapped_count else None),
            ("Unmapped", unmapped, SEMANTIC_WARNING if unmapped else None),
            ("Records", len(self.records)),
            ("Errors", self._error_count, SEMANTIC_ERROR if self._error_count else None),
        ])

    def _toggle_rules(self) -> None:
        """Show or hide the rarely used field rules."""
        self.rules_box.setVisible(not self.rules_box.isVisible())

    def _on_placeholder_clicked(self, item: QListWidgetItem) -> None:
        token = item.data(Qt.UserRole)
        if not token:
            return

        self.lbl_active_token.setText(f"{{{{{token}}}}}")
        self.right_tabs.setCurrentIndex(0)

        required = self._is_required(token)
        self.chk_required.blockSignals(True)
        self.chk_required.setChecked(required)
        self.chk_required.blockSignals(False)

        self.lbl_token_detail.setText(
            "Required field - the card cannot be rendered without it."
            if required
            else "Optional field - the card falls back to the placeholder."
        )

        # Pre-select mapped column if existing
        mapped_col = self.field_mappings.get(token, "")
        idx = self.cmb_source_column.findData(mapped_col)
        if idx >= 0:
            self.cmb_source_column.setCurrentIndex(idx)
        else:
            self.cmb_source_column.setCurrentIndex(0)
            if mapped_col:
                self.lbl_column_type.setText("")

    def _on_required_toggled(self, checked: bool) -> None:
        """Remember whether the active token is required."""
        token = self.lbl_active_token.text().strip("{}")
        if token:
            self.token_required[token] = checked
            self._refresh_placeholders_list()

    # -----------------------------------------------------------------
    # Import
    # -----------------------------------------------------------------
    def _browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Spreadsheet",
            "",
            "Spreadsheets (*.xlsx *.xls *.csv);;Excel 2007+ (*.xlsx);;Excel 97-2003 (*.xls);;CSV Files (*.csv)",
        )
        if file_path:
            self.load_file(Path(file_path))

    def load_file(self, file_path: Path, copy_to_workspace: bool = True) -> None:
        """Load spreadsheet and populate sheet names, copying to workspace data/ directory if active."""
        file_path = Path(file_path).resolve()

        if copy_to_workspace and self.project_config and self.project_config.workspace_dir:
            try:
                copied_path = ProjectManager.copy_excel_to_workspace(self.project_config, file_path)
                file_path = copied_path
                self.lbl_workspace_badge.setText(f"✓ Copied to Workspace: data/{file_path.name}")
                self.lbl_workspace_badge.setVisible(True)
            except Exception as e:
                logger.warning("Could not copy spreadsheet to workspace data folder: %s", e)

        self.current_file_path = file_path
        self.lbl_path.setText(str(file_path))
        self.btn_refresh.setEnabled(True)
        self.pill_connection.set_status("CONNECTED", color=SEMANTIC_SUCCESS)

        try:
            sheets = ExcelImporter.get_sheet_names(file_path)
            self.cmb_sheets.blockSignals(True)
            self.cmb_sheets.clear()
            self.cmb_sheets.addItems(sheets)
            self.cmb_sheets.blockSignals(False)
            self._import_current()
        except Exception as e:
            logger.error("Failed to inspect sheets in %s: %s", file_path, e)
            self.pill_connection.set_status("ERROR", color=SEMANTIC_ERROR)
            self.notice.set_message(
                f"Could not inspect spreadsheet: {e}", severity="error"
            )

    def _on_sheet_changed(self) -> None:
        self._import_current()

    def _on_header_changed(self) -> None:
        self._import_current()

    def _on_hindi_mode_changed(self) -> None:
        self._import_current()

    def _reimport_data(self) -> None:
        self._import_current()

    def _import_current(self) -> None:
        if not self.current_file_path:
            return

        sheet_name = self.cmb_sheets.currentText() or None
        header_row = self.spin_header.value()
        hindi_mode = self.cmb_hindi_mode.currentData() or "auto"

        try:
            cols, records = ExcelImporter.import_data(
                self.current_file_path,
                sheet_name=sheet_name,
                header_row=header_row,
                hindi_font_mode=hindi_mode,
            )
            # Run data validator
            report = DataValidator.validate_records(records)

            self.columns = cols
            self.records = records
            self.validation_report = report
            self.column_types = self._infer_column_types(cols, records)

            # Update Source Column dropdown in Mapping Inspector
            self.cmb_source_column.clear()
            self.cmb_source_column.addItem("(None / Ignore)", "")
            for col in cols:
                self.cmb_source_column.addItem(
                    f"{col}  {self.column_types.get(col, '[String]')}", col
                )

            # The photo lookup offers every column of the sheet.
            previous_lookup = self.photo_lookup_column
            self.cmb_photo_lookup.blockSignals(True)
            self.cmb_photo_lookup.clear()
            self.cmb_photo_lookup.addItem("Auto-detect (PIN / ID)", "")
            for col in cols:
                self.cmb_photo_lookup.addItem(col, col)
            if previous_lookup:
                index = self.cmb_photo_lookup.findData(previous_lookup)
                if index >= 0:
                    self.cmb_photo_lookup.setCurrentIndex(index)
            self.cmb_photo_lookup.blockSignals(False)

            # Auto-map initial common tokens if not already mapped
            self._auto_map_columns(silent=True)

            # The import succeeded - drop any previous problem report.
            if self.notice.severity in ("error", "warning"):
                self.notice.clear_message()

            # Check if Hindi/Devanagari text is present in columns or data
            has_hindi = (
                any(HindiConverter.is_unicode_devanagari(c) for c in cols)
                or any(
                    any(HindiConverter.is_unicode_devanagari(str(v)) for v in r.data.values())
                    for r in records[:50]
                )
            )
            if has_hindi and hindi_mode != "none":
                self.lbl_hindi_badge.setText("✓ Hindi font detected & converted to Unicode Devanagari")
                self.lbl_hindi_badge.setVisible(True)
            else:
                self.lbl_hindi_badge.setVisible(False)

            self._populate_table(records)
            self.lbl_summary.setText(
                f"{len(records):,} records • {report.valid_records} valid • "
                f"{report.missing_pins} missing PINs • {len(report.duplicate_pins)} duplicate PINs"
            )
            self._update_connection_label()
            self.pill_records.set_status(f"RECORDS: {len(records):,}", color=TEXT_SECONDARY)
            self._error_count = report.missing_pins + len(report.duplicate_pins)
            self.pill_errors.set_status(
                f"ERRORS: {self._error_count}",
                color=SEMANTIC_ERROR if self._error_count > 0 else SEMANTIC_SUCCESS,
            )

            # Publish the data first - the counters are only decoration.
            self.data_loaded.emit(cols, records, report)

            self._refresh_stat_line()
            # The column is painted again, the rows of the table have moved.
            self._repaint_column()

        except Exception as e:
            logger.error("Import failed: %s", e)
            self.pill_connection.set_status("ERROR", color=SEMANTIC_ERROR)
            self.notice.set_message(f"Failed to import records: {e}", severity="error")

    def _update_connection_label(self) -> None:
        """Show the state of the connection the way the plan describes it."""
        sheet = self.cmb_sheets.currentText()
        if not self.records:
            self.lbl_connection.setText("Connected · no records")
            return
        self.lbl_connection.setText(
            f"Connected: {len(self.records):,} Records  |  Sheet: '{sheet or 'default'}'"
        )

    # -----------------------------------------------------------------
    # Column types
    # -----------------------------------------------------------------
    def _infer_column_types(
        self,
        columns: List[str],
        records: List[SourceRecord],
    ) -> Dict[str, str]:
        """Guess the type of every column of the sheet."""
        types: Dict[str, str] = {}
        samples = records[:200]

        for column in columns:
            values = [record.get_value(column) for record in samples]
            values = [value for value in values if value]
            types[column] = self._type_of(values)

        return types

    @staticmethod
    def _type_of(values: List[str]) -> str:
        """Return the type label of a list of values."""
        if not values:
            return "[String]"

        lowered = [value.lower() for value in values]

        if all(
            value.endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"))
            for value in lowered
        ):
            return "[Image Path]"

        if all(HindiConverter.is_unicode_devanagari(value) for value in values):
            return "[Devanagari]"

        if all(re.fullmatch(r"[+-]?\d+", value) for value in values):
            return "[Integer]"

        # A column that mixes whole numbers and decimals is a decimal column.
        if all(re.fullmatch(r"[+-]?\d+([.,]\d+)?", value) for value in values):
            return "[Decimal]"

        if all(
            re.fullmatch(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}", value) for value in values
        ):
            return "[Date]"

        return "[String]"

    # -----------------------------------------------------------------
    # Mapping
    # -----------------------------------------------------------------
    def _auto_map_columns(self, silent: bool = False) -> None:
        """Heuristic auto-mapping between template tokens and spreadsheet column names."""
        if not self.columns:
            if not silent:
                self.notice.set_message(
                    "No spreadsheet columns available to map.", severity="warning"
                )
            return

        mapped_new = 0
        for token in self.template_tokens:
            clean_tok = token.lower().replace("_", "").replace(" ", "").replace("-", "")
            for col in self.columns:
                clean_col = col.lower().replace("_", "").replace(" ", "").replace("-", "")
                if clean_tok in clean_col or clean_col in clean_tok:
                    self.field_mappings[token] = col
                    mapped_new += 1
                    break

        self._refresh_placeholders_list()
        self.mappings_changed.emit(self.field_mappings)
        if not silent:
            self.notice.set_message(
                f"Auto-mapped {len(self.field_mappings)} placeholders to spreadsheet columns.",
                severity="success",
            )

    def _validate_all_records(self) -> None:
        if not self.records:
            self.notice.set_message(
                "No records loaded - import a spreadsheet first.", severity="warning"
            )
            return
        report = DataValidator.validate_records(self.records)
        self.validation_report = report
        self.pill_errors.set_status(
            f"ERRORS: {report.missing_pins + len(report.duplicate_pins)}",
            color=SEMANTIC_ERROR if (report.missing_pins + len(report.duplicate_pins)) > 0 else SEMANTIC_SUCCESS,
        )
        severity = "error" if (report.missing_pins + len(report.duplicate_pins)) else "success"
        self.notice.set_message(
            f"Validation complete - {len(self.records):,} records, "
            f"{report.valid_records:,} valid, {report.missing_pins} missing PIN, "
            f"{len(report.duplicate_pins)} duplicate.",
            severity=severity,
        )

    def _on_source_column_changed(self) -> None:
        """Show the inferred type of the chosen column."""
        column = self.cmb_source_column.currentData()
        if not column:
            self.lbl_column_type.setText("The placeholder stays empty.")
            return
        self.lbl_column_type.setText(
            f"{self.column_types.get(column, '[String]')} · {column}"
        )

    def _apply_current_mapping(self) -> None:
        raw_token = self.lbl_active_token.text().strip("{}")
        col = self.cmb_source_column.currentData() or ""
        self.field_mappings[raw_token] = col
        self._refresh_placeholders_list()
        self.mappings_changed.emit(self.field_mappings)

    # -----------------------------------------------------------------
    # Photo lookup & policy
    # -----------------------------------------------------------------
    def _on_photo_lookup_changed(self) -> None:
        """The column the photographs are looked up by has changed."""
        self.photo_lookup_column = self.cmb_photo_lookup.currentData() or ""
        self.photo_lookup_changed.emit(self.photo_lookup_column)

    def _on_photo_policy_changed(self) -> None:
        """The policy for missing photographs has changed."""
        policy = self.cmb_photo_policy.currentData()
        if policy is not None:
            self.photo_policy_changed.emit(policy)

    def set_photo_lookup_column(self, column: str) -> None:
        """Show the column the photographs are looked up by."""
        self.cmb_photo_lookup.blockSignals(True)
        index = self.cmb_photo_lookup.findData(column or "")
        if index >= 0:
            self.cmb_photo_lookup.setCurrentIndex(index)
        self.cmb_photo_lookup.blockSignals(False)
        self.photo_lookup_column = column or ""

    def set_photo_policy(self, policy) -> None:
        """Show the policy for missing photographs."""
        self.cmb_photo_policy.blockSignals(True)
        index = self.cmb_photo_policy.findData(policy)
        if index >= 0:
            self.cmb_photo_policy.setCurrentIndex(index)
        self.cmb_photo_policy.blockSignals(False)

    def set_photo_stats(self, matched: int, missing: int, ambiguous: int) -> None:
        """Show how many photographs were found for the records."""
        self.lbl_photo_stats.setText(
            f"Matched {matched:,} · Missing {missing:,} · Ambiguous {ambiguous:,}"
        )

    # -----------------------------------------------------------------
    # Table
    # -----------------------------------------------------------------
    def _populate_table(self, records_to_show: List[SourceRecord]) -> None:
        """Fill the virtual table with the imported records."""
        self.record_model.set_records(records_to_show, self.columns)
        self.record_model.set_filter(self.txt_search.text())

    def _filter_table(self, query: str) -> None:
        """Only the matching rows stay visible."""
        self.record_model.set_filter(query)
        self._refresh_stat_line()

    def _refresh_stat_line(self) -> None:
        """Show how many records are visible and how many filters are set."""
        visible = self.record_model.rowCount()
        total = len(self.records)
        filters = len(self.record_model.filtered_columns())

        text = f"{visible:,} of {total:,} records" if visible != total else f"{total:,} records"
        if filters:
            text += f"  ·  {filters} column filter{'s' if filters != 1 else ''}"
        self.lbl_summary.setText(text)

    def _repaint_column(self) -> None:
        """Paint the centre column again.

        The rows of the table move when the records are filled, and a screen
        that is not painted again keeps the pixels of the old place.  That
        showed as a second, half transparent copy of the search field.
        """
        self.center_layout.invalidate()
        self.txt_search.update()
        self.table.viewport().update()
        self.update()

    # -----------------------------------------------------------------
    # The filter of a column
    # -----------------------------------------------------------------
    def _on_column_clicked(self, section: int) -> None:
        """Open the filter of a column of the table."""
        model = self.record_model
        if model is None or section >= model.columnCount():
            return
        self._open_filter_menu(section)

    def _open_filter_menu(self, column: int) -> None:
        """Show the values of a column, so they can be picked."""
        model = self.record_model
        index = model.index(0, column)
        pos = self.table.mapToGlobal(self.table.visualRect(index).topLeft())
        open_column_filter_menu(
            self, model, column, pos, on_changed=self._on_filters_changed
        )

    def _on_filters_changed(self) -> None:
        """The filters of the columns changed."""
        self._refresh_stat_line()

    def _column_title(self, column: int) -> str:
        """The name of a column of the table."""
        model = self.record_model
        if model is None:
            return f"Column {column}"
        return model.headerData(column, Qt.Horizontal) or f"Column {column}"

    def _on_row_selected(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.lbl_inspect_details.setText("<i>Select a row in the table to inspect all attributes.</i>")
            return

        rec = self.record_model.record_at(selected_rows[0].row())
        if rec is None:
            return

        lines = [
            f"<b>Row Index:</b> {rec.row_index + 1}",
            f"<b>PIN Number:</b> {rec.pin or '(None)'}",
            f"<b>Raw PIN:</b> '{rec.raw_pin}'",
            "<hr>",
        ]
        for k, v in rec.data.items():
            lines.append(f"<b>{k}:</b> {v or '<i>empty</i>'}")

        if rec.validation_errors:
            lines.append(f"<hr><font color='{SEMANTIC_ERROR}'><b>Errors:</b><br>" + "<br>".join(rec.validation_errors) + "</font>")
        if rec.validation_warnings:
            lines.append(f"<hr><font color='{SEMANTIC_WARNING}'><b>Warnings:</b><br>" + "<br>".join(rec.validation_warnings) + "</font>")

        self.lbl_inspect_details.setText("<br>".join(lines))
