"""Dialog for browsing, selecting, and deleting saved custom templates to clean up older templates."""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.models import TemplateDefinition
from id_card_generator.templates.template_manager import TemplateManager
from id_card_generator.ui.components.elided_label import ElidedLabel
from id_card_generator.ui.studio_tokens import (
    FONT_FAMILY_MONO,
    FONT_FAMILY_UI,
    PRIMARY,
    PRIMARY_LIGHT,
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

logger = logging.getLogger(__name__)

# Every control in the dialog uses the same height as the rest of the app.
CONTROL_HEIGHT = 28

# Height of a table row - the name column holds two lines of text.
ROW_HEIGHT = 52

# Column widths (the template name column stretches).
COL_SELECT = 56
COL_TYPE = 118
COL_SPECS = 142
COL_FILE = 190
COL_ACTIONS = 176


class TemplateCleanupDialog(QDialog):
    """Modal dialog allowing users to view, search, delete, and bulk clean up saved templates."""

    template_selected = Signal(object)  # TemplateDefinition

    def __init__(self, parent=None, active_template_id: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Saved Templates & Clean Up")
        self.setMinimumSize(900, 560)
        self.resize(1060, 660)

        self.manager = TemplateManager()
        self.active_template_id = active_template_id
        self.selected_template: Optional[TemplateDefinition] = None
        self._checkbox_map: Dict[str, QCheckBox] = {}

        self._setup_ui()
        self._populate_table()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 12)
        main_layout.setSpacing(12)

        # 1. Header Hero
        header_frame = QFrame()
        header_frame.setObjectName("card_panel")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(14)

        icon_lbl = QLabel("🗂")
        icon_lbl.setStyleSheet("font-size: 26px;")
        icon_lbl.setFixedWidth(38)
        icon_lbl.setAlignment(Qt.AlignTop)
        header_layout.addWidget(icon_lbl)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(4)

        lbl_heading = QLabel("Saved Templates & Library Clean Up")
        lbl_heading.setTextFormat(Qt.PlainText)
        lbl_heading.setProperty("role", "pageTitle")
        title_box.addWidget(lbl_heading)

        self.lbl_stats = QLabel("Loading templates...")
        self.lbl_stats.setWordWrap(True)
        self.lbl_stats.setProperty("role", "pageSubtitle")
        title_box.addWidget(self.lbl_stats)

        header_layout.addLayout(title_box, stretch=1)

        main_layout.addWidget(header_frame)

        # 2. Filter & Bulk Action Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter templates by name or description...")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setFixedHeight(CONTROL_HEIGHT)
        self.txt_search.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.txt_search, stretch=1)

        self.btn_select_all = QPushButton("Select All Filtered")
        self.btn_select_all.setFixedHeight(CONTROL_HEIGHT)
        self.btn_select_all.clicked.connect(self._select_all_filtered)
        toolbar.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_deselect_all.setFixedHeight(CONTROL_HEIGHT)
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        toolbar.addWidget(self.btn_deselect_all)

        self.btn_del_selected = QPushButton("🗑 Delete Selected (0)")
        self.btn_del_selected.setObjectName("btn_danger")
        self.btn_del_selected.setFixedHeight(CONTROL_HEIGHT)
        self.btn_del_selected.setEnabled(False)
        self.btn_del_selected.clicked.connect(self._delete_selected_batch)
        toolbar.addWidget(self.btn_del_selected)

        self.btn_clean_all = QPushButton("🧹 Clean Up All Older")
        self.btn_clean_all.setFixedHeight(CONTROL_HEIGHT)
        self.btn_clean_all.setStyleSheet(
            f"color: {SEMANTIC_WARNING}; font-weight: 600; font-size: 12px;"
        )
        self.btn_clean_all.setToolTip("Permanently delete all custom saved templates from disk")
        self.btn_clean_all.clicked.connect(self._cleanup_all_custom)
        toolbar.addWidget(self.btn_clean_all)

        main_layout.addLayout(toolbar)

        # 3. Table of Templates
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Select",
            "Template Name",
            "Type",
            "Specifications",
            "Saved File",
            "Actions",
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        # The rows hold two lines of text - without this the cell widgets
        # overlap each other.
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.table.setShowGrid(False)
        self.table.setObjectName("cleanup_table")

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setFixedHeight(32)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(0, COL_SELECT)
        self.table.setColumnWidth(2, COL_TYPE)
        self.table.setColumnWidth(3, COL_SPECS)
        self.table.setColumnWidth(4, COL_FILE)
        self.table.setColumnWidth(5, COL_ACTIONS)

        main_layout.addWidget(self.table, stretch=1)

        # 4. Footer
        footer = QHBoxLayout()
        footer.setSpacing(12)
        lbl_tip = QLabel(
            "💡 Built-in templates are protected and cannot be deleted. "
            "Deleting a custom template permanently removes it from disk."
        )
        lbl_tip.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        footer.addWidget(lbl_tip, stretch=1)

        btn_close = QPushButton("Close")
        btn_close.setFixedHeight(CONTROL_HEIGHT)
        btn_close.setObjectName("btn_primary")
        btn_close.clicked.connect(self.reject)
        footer.addWidget(btn_close)

        main_layout.addLayout(footer)

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------
    def _populate_table(self) -> None:
        """Reload templates from manager and populate table rows."""
        self.manager.reload()
        all_templates = self.manager.list_templates()
        total_count = len(all_templates)
        builtin_count = sum(1 for t in all_templates if self.manager.is_builtin(t.id))
        custom_count = total_count - builtin_count

        self.lbl_stats.setText(
            f"{total_count} total templates · {builtin_count} built-in · {custom_count} saved custom. "
            f"Select templates to delete or clean up older versions."
        )

        self._checkbox_map.clear()
        self.table.setRowCount(0)

        # Sort: Built-ins first, then custom templates
        sorted_templates = sorted(
            all_templates,
            key=lambda t: (0 if self.manager.is_builtin(t.id) else 1, t.name.lower())
        )

        search_query = self.txt_search.text().strip().lower()

        for row_idx, tmpl in enumerate(sorted_templates):
            is_built = self.manager.is_builtin(tmpl.id)
            is_active = (tmpl.id == self.active_template_id)

            self.table.insertRow(row_idx)

            # Col 0: Checkbox
            if is_built:
                lock_lbl = QLabel("🔒")
                lock_lbl.setAlignment(Qt.AlignCenter)
                lock_lbl.setToolTip("Protected built-in template")
                self.table.setCellWidget(row_idx, 0, lock_lbl)
            else:
                chk_container = QWidget()
                chk_layout = QHBoxLayout(chk_container)
                chk_layout.setContentsMargins(0, 0, 0, 0)
                chk_layout.setAlignment(Qt.AlignCenter)
                chk = QCheckBox()
                chk.setFixedHeight(CONTROL_HEIGHT)
                chk.toggled.connect(self._update_delete_button_state)
                chk_layout.addWidget(chk)
                chk_layout.activate()
                self.table.setCellWidget(row_idx, 0, chk_container)
                self._checkbox_map[tmpl.id] = chk

            # Col 1: Template Name & Description
            name_container = QWidget()
            name_layout = QVBoxLayout(name_container)
            name_layout.setContentsMargins(4, 4, 4, 4)
            name_layout.setSpacing(1)

            title_row = QHBoxLayout()
            title_row.setContentsMargins(0, 0, 0, 0)
            title_row.setSpacing(6)
            title_lbl = QLabel(tmpl.name)
            title_lbl.setProperty("role", "tableTitle")
            title_lbl.setToolTip(tmpl.name)
            title_row.addWidget(title_lbl)

            if is_active:
                active_badge = QLabel("● ACTIVE")
                active_badge.setStyleSheet(
                    f"color: {PRIMARY_LIGHT}; font-weight: 700; font-size: 10px;"
                )
                title_row.addWidget(active_badge)
            title_row.addStretch()
            name_layout.addLayout(title_row)
            name_layout.activate()

            if tmpl.description:
                desc_lbl = ElidedLabel(tmpl.description)
                desc_lbl.setProperty("role", "tableSubtitle")
                desc_lbl.setToolTip(tmpl.description)
                name_layout.addWidget(desc_lbl)

            self.table.setCellWidget(row_idx, 1, name_container)

            # Col 2: Type Badge
            type_lbl = QLabel("Built-in" if is_built else "Custom Saved")
            type_lbl.setProperty("role", "badgeMuted" if is_built else "badgeAccent")
            type_lbl.setAlignment(Qt.AlignCenter)
            self.table.setCellWidget(row_idx, 2, type_lbl)

            # Col 3: Specifications
            elem_count = len(tmpl.elements)
            specs_lbl = QLabel(
                f"{tmpl.width_px} × {tmpl.height_px} px\n{tmpl.dpi} DPI · {elem_count} elements"
            )
            specs_lbl.setProperty("role", "tableCell")
            specs_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.table.setCellWidget(row_idx, 3, specs_lbl)

            # Col 4: Saved File info
            file_path = self.manager.get_template_file_path(tmpl.id)
            if file_path and file_path.exists():
                file_lbl = ElidedLabel(file_path.name)
                file_lbl.setProperty("role", "tableMono")
                file_lbl.setToolTip(str(file_path))
            else:
                file_lbl = ElidedLabel("Built-in Asset" if is_built else "—")
                file_lbl.setProperty("role", "tableSubtitle")
            file_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.table.setCellWidget(row_idx, 4, file_lbl)

            # Col 5: Actions - the buttons have to fit into the column,
            # otherwise they are clipped by the viewport.
            actions_container = QWidget()
            actions_layout = QHBoxLayout(actions_container)
            actions_layout.setContentsMargins(4, 0, 4, 0)
            actions_layout.setSpacing(4)
            actions_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            btn_load = QPushButton("✓ Active" if is_active else "Use")
            btn_load.setFixedHeight(CONTROL_HEIGHT)
            btn_load.setFixedWidth(70)
            btn_load.setStyleSheet("font-size: 11px;")
            btn_load.setToolTip("Load this template into the designer")
            btn_load.clicked.connect(lambda ch=False, t=tmpl: self._on_load_clicked(t))
            actions_layout.addWidget(btn_load)

            if not is_built:
                btn_del = QPushButton("🗑 Delete")
                btn_del.setObjectName("btn_danger")
                btn_del.setFixedHeight(CONTROL_HEIGHT)
                btn_del.setFixedWidth(88)
                btn_del.setStyleSheet("font-size: 12px;")
                btn_del.setToolTip(
                    f"Permanently delete '{tmpl.name}' from disk"
                )
                btn_del.clicked.connect(
                    lambda ch=False, tid=tmpl.id, tname=tmpl.name: self._delete_single_template(tid, tname)
                )
                actions_layout.addWidget(btn_del)

            # The layout of a cell widget is only calculated when the event
            # loop runs - without this the buttons are drawn at their default
            # position and look misaligned.
            actions_layout.activate()
            self.table.setCellWidget(row_idx, 5, actions_container)

            # Check search filter visibility
            if search_query:
                visible = (
                    search_query in tmpl.name.lower()
                    or search_query in tmpl.description.lower()
                    or search_query in tmpl.id.lower()
                )
                self.table.setRowHidden(row_idx, not visible)

        self._update_delete_button_state()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_search_changed(self, text: str) -> None:
        """Filter table rows live as user types."""
        query = text.strip().lower()
        all_templates = self.manager.list_templates()
        sorted_templates = sorted(
            all_templates,
            key=lambda t: (0 if self.manager.is_builtin(t.id) else 1, t.name.lower())
        )

        for row_idx, tmpl in enumerate(sorted_templates):
            if not query:
                self.table.setRowHidden(row_idx, False)
            else:
                visible = (
                    query in tmpl.name.lower()
                    or query in tmpl.description.lower()
                    or query in tmpl.id.lower()
                )
                self.table.setRowHidden(row_idx, not visible)

    def _on_load_clicked(self, template: TemplateDefinition) -> None:
        """Load selected template into editor and close dialog."""
        self.selected_template = template
        self.template_selected.emit(template)
        self.accept()

    def _get_selected_ids(self) -> List[str]:
        """Return list of template IDs currently checked by user."""
        selected = []
        for tid, chk in self._checkbox_map.items():
            if chk.isChecked():
                selected.append(tid)
        return selected

    def _update_delete_button_state(self) -> None:
        """Update Delete Selected button label and enabled status."""
        count = len(self._get_selected_ids())
        self.btn_del_selected.setText(f"🗑 Delete Selected ({count})")
        self.btn_del_selected.setEnabled(count > 0)

    def _select_all_filtered(self) -> None:
        """Check all visible/filtered custom template checkboxes."""
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                cell = self.table.cellWidget(row, 0)
                if cell and isinstance(cell, QWidget):
                    chk = cell.findChild(QCheckBox)
                    if chk:
                        chk.setChecked(True)

    def _deselect_all(self) -> None:
        """Uncheck all custom template checkboxes."""
        for chk in self._checkbox_map.values():
            chk.setChecked(False)

    def _delete_single_template(self, template_id: str, template_name: str) -> None:
        """Confirm and delete a single saved custom template."""
        confirm = QMessageBox.question(
            self,
            "Confirm Template Deletion",
            f"Are you sure you want to permanently delete custom template "
            f"'{template_name}' from disk?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            try:
                self.manager.delete_user_template(template_id)
                self._populate_table()
                self._set_status(
                    f"Template '{template_name}' was deleted from disk.", SEMANTIC_SUCCESS
                )
            except Exception as e:
                logger.error("Failed to delete template %s: %s", template_id, e)
                self._set_status(f"Could not delete the template: {e}", "error")

    def _delete_selected_batch(self) -> None:
        """Confirm and delete all checked custom templates."""
        selected_ids = self._get_selected_ids()
        count = len(selected_ids)
        if count == 0:
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Batch Deletion",
            f"Are you sure you want to permanently delete {count} selected template(s) "
            f"from disk?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            try:
                deleted_count = self.manager.delete_user_templates_batch(selected_ids)
                self._populate_table()
                self._set_status(
                    f"Deleted {deleted_count} template(s) from disk.", SEMANTIC_SUCCESS
                )
            except Exception as e:
                logger.error("Failed batch deleting templates: %s", e)
                self._set_status(f"Error during deletion: {e}", "error")

    def _cleanup_all_custom(self) -> None:
        """Clean up and delete all custom saved templates with safety confirmation."""
        custom_ids = [
            t.id for t in self.manager.list_templates()
            if not self.manager.is_builtin(t.id)
        ]
        count = len(custom_ids)
        if count == 0:
            self._set_status("No custom saved templates found to clean up.", "warning")
            return

        confirm = QMessageBox.warning(
            self,
            "Clean Up All Older Templates",
            f"You are about to delete all {count} custom saved template(s) from disk.\n"
            "Built-in templates will be preserved.\n\n"
            "Are you sure you want to perform this clean up?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            try:
                deleted_count = self.manager.delete_user_templates_batch(custom_ids)
                self._populate_table()
                self._set_status(
                    f"Clean up complete - deleted {deleted_count} custom template(s).",
                    SEMANTIC_SUCCESS,
                )
            except Exception as e:
                logger.error("Failed cleaning up templates: %s", e)
                self._set_status(f"Error during clean up: {e}", "error")

    def _set_status(self, message: str, severity: str = "info") -> None:
        """Show a short status message inside the dialog."""
        colors = {
            "info": TEXT_SECONDARY,
            "success": SEMANTIC_SUCCESS,
            "warning": SEMANTIC_WARNING,
            "error": SEMANTIC_WARNING,
        }
        self.lbl_stats.setStyleSheet(
            f"color: {colors.get(severity, TEXT_SECONDARY)}; font-size: 11px;"
        )
        self.lbl_stats.setText(message)
