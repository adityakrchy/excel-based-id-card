"""Data source import and interactive record preview page."""

import logging
from pathlib import Path
from typing import List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import WorkflowStep
from id_card_generator.core.exceptions import DataSourceError
from id_card_generator.core.models import ProjectConfiguration, SourceRecord
from id_card_generator.core.project_manager import ProjectManager
from id_card_generator.data.data_validator import DataValidator, ValidationReport
from id_card_generator.data.excel_importer import ExcelImporter
from id_card_generator.ui.step_nav_bar import StepNavBar

logger = logging.getLogger(__name__)


class DataSourcePage(QWidget):
    """Import spreadsheet, configure sheet/headers, validate rows, and preview data."""

    data_loaded = Signal(object, object, object)  # (columns, records, validation_report)
    navigate_requested = Signal(str)  # WorkflowStep value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_config: Optional[ProjectConfiguration] = None
        self.current_file_path: Optional[Path] = None
        self.columns: List[str] = []
        self.records: List[SourceRecord] = []
        self.validation_report: Optional[ValidationReport] = None

        self._setup_ui()

    def set_project_config(self, config: Optional[ProjectConfiguration]) -> None:
        """Associate active project workspace configuration."""
        self.project_config = config
        if config and config.workspace_dir and config.excel_file_path:
            p = Path(config.excel_file_path)
            if p.exists():
                self.lbl_workspace_badge.setText(f"✓ Stored in Workspace: data/{p.name}")
                self.lbl_workspace_badge.setVisible(True)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 1. Top File Selection Card
        top_card = QFrame()
        top_card.setObjectName("card_panel")
        top_layout = QVBoxLayout(top_card)

        # File browse row
        file_row = QHBoxLayout()
        self.lbl_path = QLabel("<i>No file selected</i>")
        self.lbl_path.setStyleSheet("color: #94A3B8; font-weight: 500;")

        self.btn_browse = QPushButton("Browse Spreadsheet...")
        self.btn_browse.setObjectName("btn_primary")
        self.btn_browse.clicked.connect(self._browse_file)

        self.btn_refresh = QPushButton("Re-import")
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.clicked.connect(self._reimport_data)

        file_row.addWidget(self.btn_browse)
        file_row.addWidget(self.lbl_path, stretch=1)
        file_row.addWidget(self.btn_refresh)
        top_layout.addLayout(file_row)

        # Workspace badge row
        self.lbl_workspace_badge = QLabel("")
        self.lbl_workspace_badge.setStyleSheet("color: #10B981; font-weight: 600; font-size: 11px;")
        self.lbl_workspace_badge.setVisible(False)
        top_layout.addWidget(self.lbl_workspace_badge)

        # Controls row: Sheet selector & Header row
        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel("Worksheet:"))
        self.cmb_sheets = QComboBox()
        self.cmb_sheets.currentIndexChanged.connect(self._on_sheet_changed)
        ctrl_row.addWidget(self.cmb_sheets, stretch=1)

        ctrl_row.addWidget(QLabel("Header Row (0-indexed):"))
        self.spin_header = QSpinBox()
        self.spin_header.setRange(0, 100)
        self.spin_header.setValue(0)
        self.spin_header.valueChanged.connect(self._on_header_changed)
        ctrl_row.addWidget(self.spin_header)

        top_layout.addLayout(ctrl_row)
        layout.addWidget(top_card)

        # 2. Search & Filter Bar
        search_row = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search records by name, PIN, designation, office...")
        self.txt_search.textChanged.connect(self._filter_table)
        search_row.addWidget(self.txt_search)

        self.lbl_summary = QLabel("0 records loaded")
        self.lbl_summary.setStyleSheet("font-weight: 600; color: #64748B;")
        search_row.addWidget(self.lbl_summary)
        layout.addLayout(search_row)

        # 3. Main Data Preview Splitter (Table on left, Record Inspector on right)
        splitter = QSplitter(Qt.Horizontal)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self.table)

        # Inspector Panel
        self.inspector = QFrame()
        self.inspector.setObjectName("card_panel")
        self.inspector.setMinimumWidth(280)
        insp_layout = QVBoxLayout(self.inspector)
        insp_layout.addWidget(QLabel("<b>Selected Record Inspector</b>"))
        self.lbl_inspect_details = QLabel("<i>Select a row in the table to inspect all attributes.</i>")
        self.lbl_inspect_details.setWordWrap(True)
        insp_layout.addWidget(self.lbl_inspect_details)
        insp_layout.addStretch()
        splitter.addWidget(self.inspector)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        # 4. Bottom Step Navigation Bar
        self.nav_bar = StepNavBar(
            prev_label="Dashboard & Settings",
            next_label="Photo Library",
            step_badge="Step 1 of 7: Data Source",
            parent=self,
        )
        self.nav_bar.back_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.DASHBOARD.value))
        self.nav_bar.next_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.PHOTOS.value))
        layout.addWidget(self.nav_bar)

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

        try:
            sheets = ExcelImporter.get_sheet_names(file_path)
            self.cmb_sheets.blockSignals(True)
            self.cmb_sheets.clear()
            self.cmb_sheets.addItems(sheets)
            self.cmb_sheets.blockSignals(False)
            self._import_current()
        except Exception as e:
            logger.error("Failed to inspect sheets in %s: %s", file_path, e)
            QMessageBox.critical(self, "Import Error", f"Could not inspect spreadsheet: {e}")

    def _on_sheet_changed(self) -> None:
        self._import_current()

    def _on_header_changed(self) -> None:
        self._import_current()

    def _reimport_data(self) -> None:
        self._import_current()

    def _import_current(self) -> None:
        if not self.current_file_path:
            return

        sheet_name = self.cmb_sheets.currentText() or None
        header_row = self.spin_header.value()

        try:
            cols, records = ExcelImporter.import_data(
                self.current_file_path,
                sheet_name=sheet_name,
                header_row=header_row,
            )
            # Run data validator
            report = DataValidator.validate_records(records)

            self.columns = cols
            self.records = records
            self.validation_report = report

            self._populate_table(records)
            self.lbl_summary.setText(
                f"{len(records):,} records • {report.valid_records} valid • "
                f"{report.missing_pins} missing PINs • {len(report.duplicate_pins)} duplicate PINs"
            )

            self.data_loaded.emit(cols, records, report)

        except Exception as e:
            logger.error("Import failed: %s", e)
            QMessageBox.critical(self, "Data Import Error", f"Failed to import records: {e}")

    def _populate_table(self, records_to_show: List[SourceRecord]) -> None:
        self.table.clear()
        if not records_to_show or not self.columns:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

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
                status_item.setForeground(QColor("#DC2626"))
            elif any("Duplicate" in w for w in rec.validation_warnings):
                status_item = QTableWidgetItem("DUPLICATE")
                status_item.setBackground(QColor(245, 158, 11, 60))
                status_item.setForeground(QColor("#D97706"))
            else:
                status_item = QTableWidgetItem("VALID")
                status_item.setForeground(QColor("#059669"))
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
                    item.setBackground(QColor(241, 245, 249, 100))
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
                lines.append("<hr><font color='#DC2626'><b>Errors:</b><br>" + "<br>".join(rec.validation_errors) + "</font>")
            if rec.validation_warnings:
                lines.append("<hr><font color='#D97706'><b>Warnings:</b><br>" + "<br>".join(rec.validation_warnings) + "</font>")

            self.lbl_inspect_details.setText("<br>".join(lines))
