"""Data source import and interactive record preview page.

Revamped into a 3-column workstation suite per Stitch screen bd2f3aebf3bb:
- Top Ribbon: connection pill, action toolbar, live metric pills.
- Left Column: Template Placeholders & schema token registry.
- Center Column: Spreadsheet controls, search filter, and live preview data table.
- Right Column: Field Mapping & Rule Inspector + Selected Record Inspector.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
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
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import WorkflowStep
from id_card_generator.core.exceptions import DataSourceError
from id_card_generator.core.models import ProjectConfiguration, SourceRecord, TemplateDefinition
from id_card_generator.core.project_manager import ProjectManager
from id_card_generator.data.data_validator import DataValidator, ValidationReport
from id_card_generator.data.excel_importer import ExcelImporter
from id_card_generator.data.hindi_converter import HindiConverter
from id_card_generator.ui import workflow
from id_card_generator.ui.studio_tokens import SIZES
from id_card_generator.ui.components.layout_blocks import Divider, OverflowMenu, StatLine
from id_card_generator.ui.components.page_scaffold import InlineNotice, PageFooter, PageHeader
from id_card_generator.ui.components.status_pill import StatusPill
from id_card_generator.ui.studio_tokens import (
    BORDER_DEFAULT,
    BORDER_SUBTLE,
    FONT_FAMILY_MONO,
    FONT_FAMILY_UI,
    PRIMARY,
    SEMANTIC_ERROR,
    SEMANTIC_SUCCESS,
    SEMANTIC_WARNING,
    SURFACE,
    SURFACE_HIGH,
    SURFACE_HIGHER,
    SURFACE_LOW,
    SURFACE_LOWEST,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)

# Every control in a row uses the same height as the rest of the app.
CONTROL_HEIGHT = SIZES.CONTROL_HEIGHT


class DataSourcePage(QWidget):
    """Import spreadsheet, configure sheet/headers, validate rows, and preview data."""

    data_loaded = Signal(object, object, object)  # (columns, records, validation_report)
    navigate_requested = Signal(str)  # WorkflowStep value
    mappings_changed = Signal(dict)  # token -> column mapping dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_config: Optional[ProjectConfiguration] = None
        self.current_file_path: Optional[Path] = None
        self.columns: List[str] = []
        self.records: List[SourceRecord] = []
        self.validation_report: Optional[ValidationReport] = None
        self.field_mappings: Dict[str, str] = {}
        self.template_tokens: List[str] = ["pin_number", "employee_name", "department", "designation", "photo"]
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
                import re
                found = re.findall(r"\{\{([^}]+)\}\}", elem.text)
                for f in found:
                    tokens.add(f.strip())
        if tokens:
            self.template_tokens = sorted(list(tokens))
            self._refresh_placeholders_list()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---------------------------------------------------------
        # 0. Page Header (step badge, title, contextual actions)
        # ---------------------------------------------------------
        badge, title, subtitle = workflow.page_header_text(WorkflowStep.DATA_SOURCE)
        self.page_header = PageHeader(title, subtitle, badge)
        main_layout.addWidget(self.page_header)

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

        self.pill_connection = StatusPill("NO DATA", color=TEXT_MUTED)
        file_row.addWidget(self.pill_connection)

        self.lbl_path = QLabel("No spreadsheet connected")
        self.lbl_path.setProperty("role", "monoMuted")
        file_row.addWidget(self.lbl_path, stretch=1)

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

        self.btn_automap = QPushButton("Auto-Map")
        self.btn_automap.setToolTip("Automatically map spreadsheet columns to template placeholders by name similarity")
        self.btn_automap.clicked.connect(self._auto_map_columns)
        self.btn_automap.setVisible(False)
        top_layout.addWidget(self.btn_automap)

        self.btn_validate = QPushButton("Validate All")
        self.btn_validate.setToolTip("Run strict validation checks across all records")
        self.btn_validate.clicked.connect(self._validate_all_records)
        self.btn_validate.setVisible(False)
        top_layout.addWidget(self.btn_validate)

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
        # 2. Main 3-Column Workstation Splitter
        # ---------------------------------------------------------
        self.main_splitter = QSplitter(Qt.Horizontal)

        # --- LEFT COLUMN: Template Placeholders List ---
        left_panel = QFrame()
        left_panel.setObjectName("workspace_panel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        lbl_tokens_title = QLabel("<b>TEMPLATE PLACEHOLDERS</b>")
        lbl_tokens_title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px; letter-spacing: 0.5px;")
        left_layout.addWidget(lbl_tokens_title)

        lbl_tokens_sub = QLabel("Select token to inspect or map")
        lbl_tokens_sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        left_layout.addWidget(lbl_tokens_sub)

        self.list_placeholders = QListWidget()
        self.list_placeholders.setStyleSheet(
            f"QListWidget {{ background: {SURFACE_LOWEST}; border: 1px solid {BORDER_SUBTLE}; color: {TEXT_PRIMARY}; font-size: 11px; }}"
            f"QListWidget::item {{ padding: 6px; border-bottom: 1px solid {BORDER_SUBTLE}; }}"
            f"QListWidget::item:selected {{ background-color: {SURFACE_HIGH}; color: {PRIMARY}; border-left: 2px solid {PRIMARY}; }}"
        )
        self.list_placeholders.itemClicked.connect(self._on_placeholder_clicked)
        left_layout.addWidget(self.list_placeholders)

        self.main_splitter.addWidget(left_panel)

        # --- CENTER COLUMN: Spreadsheet Controls & Data Preview Table ---
        center_panel = QFrame()
        center_panel.setObjectName("workspace_panel")
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(8, 8, 8, 8)
        center_layout.setSpacing(8)

        # Controls sub-bar (Worksheet, Header row, Hindi mode, Search)
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setSpacing(6)

        self.cmb_sheets = QComboBox()
        self.cmb_sheets.setPlaceholderText("Sheet")
        self.cmb_sheets.setFixedHeight(CONTROL_HEIGHT)
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
        self.cmb_hindi_mode.addItem("Auto-detect Hindi", "auto")
        self.cmb_hindi_mode.addItem("Kruti Dev → Unicode", "kruti_to_unicode")
        self.cmb_hindi_mode.addItem("Unicode / Mangal", "none")
        self.cmb_hindi_mode.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_hindi_mode.currentIndexChanged.connect(self._on_hindi_mode_changed)
        ctrl_bar.addWidget(self.cmb_hindi_mode)

        center_layout.addLayout(ctrl_bar)

        # Search & Summary Bar
        search_bar = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter records (name, PIN, designation, dept)...")
        self.txt_search.textChanged.connect(self._filter_table)
        search_bar.addWidget(self.txt_search, stretch=1)

        self.lbl_summary = QLabel("0 records loaded")
        self.lbl_summary.setStyleSheet(f"font-weight: 600; color: {TEXT_SECONDARY}; font-size: 11px;")
        search_bar.addWidget(self.lbl_summary)
        center_layout.addLayout(search_bar)

        # Data Table
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self.table.setStyleSheet(
            f"QTableWidget {{ background-color: {SURFACE_LOWEST}; alternate-background-color: {SURFACE_LOW};"
            f" gridline-color: {BORDER_SUBTLE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SUBTLE}; }}"
            f"QHeaderView::section {{ background-color: {SURFACE_HIGH}; color: {TEXT_SECONDARY}; border: 1px solid {BORDER_SUBTLE};"
            f" padding: 4px; font-weight: 600; font-size: 11px; }}"
        )
        center_layout.addWidget(self.table)

        self.main_splitter.addWidget(center_panel)

        # --- RIGHT COLUMN: Field Mapping & Selected Record Inspector ---
        right_panel = QFrame()
        right_panel.setObjectName("workspace_panel")
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
        mapping_layout = QVBoxLayout(tab_mapping)
        mapping_layout.setContentsMargins(8, 8, 8, 8)
        mapping_layout.setSpacing(8)

        lbl_map_head = QLabel("MAPPING")
        lbl_map_head.setProperty("role", "sectionLabel")
        mapping_layout.addWidget(lbl_map_head)

        self.lbl_active_token = QLabel("{{pin_number}}")
        self.lbl_active_token.setProperty("role", "specValue")
        self.lbl_active_token.setStyleSheet(f"color: {PRIMARY}; font-weight: 600;")
        mapping_layout.addWidget(self.lbl_active_token)

        self.cmb_source_column = QComboBox()
        self.cmb_source_column.setPlaceholderText("Spreadsheet column")
        self.cmb_source_column.setFixedHeight(CONTROL_HEIGHT)
        self.cmb_source_column.currentIndexChanged.connect(self._on_source_column_changed)
        mapping_layout.addWidget(self.cmb_source_column)

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
        rules_layout.addWidget(self.cmb_overflow)

        self.chk_required = QCheckBox("Required field")
        self.chk_required.setChecked(True)
        rules_layout.addWidget(self.chk_required)

        self.chk_convert_hindi = QCheckBox("Convert KrutiDev / DevLys")
        self.chk_convert_hindi.setChecked(True)
        rules_layout.addWidget(self.chk_convert_hindi)

        self.rules_box.setVisible(False)
        mapping_layout.addWidget(self.rules_box)

        mapping_layout.addStretch()
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
        self.lbl_inspect_details.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; line-height: 1.4;")
        insp_layout.addWidget(self.lbl_inspect_details)
        insp_layout.addStretch()

        self.right_tabs.addTab(self.inspector, "Record")
        right_layout.addWidget(self.right_tabs)

        self.main_splitter.addWidget(right_panel)

        # Set Splitter Initial Proportions: Left ~240, Center ~600, Right ~280
        self.main_splitter.setSizes([240, 620, 280])
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

    def _refresh_placeholders_list(self) -> None:
        """Populate left placeholder list."""
        self.list_placeholders.clear()
        mapped_count = 0
        for token in self.template_tokens:
            is_mapped = token in self.field_mappings and bool(self.field_mappings[token])
            if is_mapped:
                mapped_count += 1
                status = f"✓ {self.field_mappings[token]}"
            else:
                status = "⚠ unmapped"

            item = QListWidgetItem(f"{{{{{token}}}}}\n   {status}")
            item.setData(Qt.UserRole, token)
            self.list_placeholders.addItem(item)

        self.pill_placeholders.set_status(f"TOKENS: {len(self.template_tokens)}", color=PRIMARY)
        self.pill_mapped.set_status(f"MAPPED: {mapped_count}", color=SEMANTIC_SUCCESS if mapped_count > 0 else TEXT_MUTED)
        unmapped = len(self.template_tokens) - mapped_count
        self.pill_unmapped.set_status(f"UNMAPPED: {unmapped}", color=SEMANTIC_WARNING if unmapped > 0 else SEMANTIC_SUCCESS)

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
        if token:
            self.lbl_active_token.setText(f"{{{{{token}}}}}")
            self.right_tabs.setCurrentIndex(0)
            # Pre-select mapped column if existing
            mapped_col = self.field_mappings.get(token, "")
            idx = self.cmb_source_column.findText(mapped_col)
            if idx >= 0:
                self.cmb_source_column.setCurrentIndex(idx)

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

            # Update Source Column dropdown in Mapping Inspector
            self.cmb_source_column.clear()
            self.cmb_source_column.addItem("(None / Ignore)", "")
            for col in cols:
                self.cmb_source_column.addItem(col, col)

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
            self.pill_records.set_status(f"RECORDS: {len(records):,}", color=TEXT_SECONDARY)
            self._error_count = report.missing_pins + len(report.duplicate_pins)
            self.pill_errors.set_status(
                f"ERRORS: {self._error_count}",
                color=SEMANTIC_ERROR if self._error_count > 0 else SEMANTIC_SUCCESS,
            )
            self._refresh_stat_line()

            self.data_loaded.emit(cols, records, report)

        except Exception as e:
            logger.error("Import failed: %s", e)
            self.pill_connection.set_status("ERROR", color=SEMANTIC_ERROR)
            self.pill_connection.set_status("ERROR", color=SEMANTIC_ERROR)
            self.notice.set_message(f"Failed to import records: {e}", severity="error")

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
        pass

    def _apply_current_mapping(self) -> None:
        raw_token = self.lbl_active_token.text().strip("{}")
        col = self.cmb_source_column.currentText()
        if col.startswith("(None"):
            col = ""
        self.field_mappings[raw_token] = col
        self._refresh_placeholders_list()
        self.mappings_changed.emit(self.field_mappings)

    def _populate_table(self, records_to_show: List[SourceRecord]) -> None:
        self.table.clear()
        if not records_to_show or not self.columns:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

        tbl_font = self.table.font()
        tbl_font.setFamilies([tbl_font.family(), "Segoe UI", "Nirmala UI", "Mangal", "Kohinoor Devanagari", "Devanagari Sangam MN", "Noto Sans Devanagari", "Arial"])
        self.table.setFont(tbl_font)

        headers = ["Row", "PIN Status", "PIN Number"] + [c for c in self.columns if c.lower() != "pin number"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(records_to_show))

        for row_idx, rec in enumerate(records_to_show):
            # Row index
            item_row = QTableWidgetItem(str(rec.row_index))
            item_row.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 0, item_row)

            # PIN Status
            if not rec.pin:
                status_item = QTableWidgetItem("MISSING PIN")
                status_item.setBackground(QColor(239, 68, 68, 60))
                status_item.setForeground(QColor(SEMANTIC_ERROR))
            elif any("Duplicate" in w for w in rec.validation_warnings):
                status_item = QTableWidgetItem("DUPLICATE")
                status_item.setBackground(QColor(245, 158, 11, 60))
                status_item.setForeground(QColor(SEMANTIC_WARNING))
            else:
                status_item = QTableWidgetItem("VALID")
                status_item.setForeground(QColor(SEMANTIC_SUCCESS))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 1, status_item)

            # PIN Number
            item_pin = QTableWidgetItem(rec.pin or rec.raw_pin)
            if not rec.pin:
                item_pin.setBackground(QColor(239, 68, 68, 40))
            self.table.setItem(row_idx, 2, item_pin)

            # Other columns
            col_offset = 3
            for c_idx, col_name in enumerate(c for c in self.columns if c.lower() != "pin number"):
                val = rec.get_value(col_name)
                item = QTableWidgetItem(val)
                if not val:
                    # Empty cell highlight
                    item.setBackground(QColor(40, 44, 52, 100))
                self.table.setItem(row_idx, col_offset + c_idx, item)

    def _filter_table(self, query: str) -> None:
        query = query.lower().strip()
        if not query:
            for r in range(self.table.rowCount()):
                self.table.setRowHidden(r, False)
            return

        for r in range(self.table.rowCount()):
            row_visible = False
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item and query in item.text().lower():
                    row_visible = True
                    break
            self.table.setRowHidden(r, not row_visible)

    def _on_row_selected(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.lbl_inspect_details.setText("<i>Select a row in the table to inspect all attributes.</i>")
            return

        row_idx = selected_rows[0].row()
        if 0 <= row_idx < len(self.records):
            rec = self.records[row_idx]
            lines = [
                f"<b>Row Index:</b> {rec.row_index}",
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
