"""Dialog for browsing, selecting, and deleting saved custom templates to clean up older templates."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

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
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.models import TemplateDefinition
from id_card_generator.templates.template_manager import TemplateManager

logger = logging.getLogger(__name__)


class TemplateCleanupDialog(QDialog):
    """Modal dialog allowing users to view, search, delete, and bulk clean up saved templates."""

    template_selected = Signal(object)  # TemplateDefinition

    def __init__(self, parent=None, active_template_id: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Saved Templates & Clean Up")
        self.setMinimumSize(800, 560)
        self.resize(860, 600)

        self.manager = TemplateManager()
        self.active_template_id = active_template_id
        self.selected_template: Optional[TemplateDefinition] = None
        self._checkbox_map: Dict[str, QCheckBox] = {}

        self._setup_ui()
        self._populate_table()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. Header Hero
        header_frame = QFrame()
        header_frame.setObjectName("card_panel")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(14, 12, 14, 12)

        icon_lbl = QLabel("🗂")
        icon_lbl.setStyleSheet("font-size: 28px;")
        header_layout.addWidget(icon_lbl)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_heading = QLabel("<b>Saved Templates & Library Clean Up</b>")
        lbl_heading.setStyleSheet("font-size: 16px; color: #F1F5F9;")
        title_box.addWidget(lbl_heading)

        self.lbl_stats = QLabel("Loading templates...")
        self.lbl_stats.setStyleSheet("font-size: 12px; color: #94A3B8;")
        title_box.addWidget(self.lbl_stats)
        header_layout.addLayout(title_box, stretch=1)

        main_layout.addWidget(header_frame)

        # 2. Filter & Bulk Action Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 Filter templates by name or description...")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.txt_search, stretch=1)

        self.btn_select_all = QPushButton("Select All Filtered")
        self.btn_select_all.clicked.connect(self._select_all_filtered)
        toolbar.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        toolbar.addWidget(self.btn_deselect_all)

        self.btn_del_selected = QPushButton("🗑 Delete Selected (0)")
        self.btn_del_selected.setObjectName("btn_danger")
        self.btn_del_selected.setEnabled(False)
        self.btn_del_selected.clicked.connect(self._delete_selected_batch)
        toolbar.addWidget(self.btn_del_selected)

        self.btn_clean_all = QPushButton("🧹 Clean Up All Older")
        self.btn_clean_all.setStyleSheet("color: #F59E0B; font-weight: bold;")
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
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #18181B; gridline-color: #27272A; } "
            "QTableWidget::item { padding: 6px; } "
            "QHeaderView::section { background-color: #27272A; color: #E4E4E7; padding: 6px; font-weight: bold; border: none; }"
        )

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 50)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 170)

        main_layout.addWidget(self.table, stretch=1)

        # 4. Footer
        footer = QHBoxLayout()
        lbl_tip = QLabel("💡 Tip: Built-in templates are protected and cannot be deleted. Deleting custom templates permanently removes them from disk.")
        lbl_tip.setStyleSheet("font-size: 11px; color: #64748B;")
        footer.addWidget(lbl_tip, stretch=1)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        footer.addWidget(btn_close)

        main_layout.addLayout(footer)

    def _populate_table(self) -> None:
        """Reload templates from manager and populate table rows."""
        self.manager.reload()
        all_templates = self.manager.list_templates()
        total_count = len(all_templates)
        builtin_count = sum(1 for t in all_templates if self.manager.is_builtin(t.id))
        custom_count = total_count - builtin_count

        self.lbl_stats.setText(
            f"{total_count} total templates ({builtin_count} built-in, {custom_count} saved custom). "
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
                chk.toggled.connect(self._update_delete_button_state)
                chk_layout.addWidget(chk)
                self.table.setCellWidget(row_idx, 0, chk_container)
                self._checkbox_map[tmpl.id] = chk

            # Col 1: Template Name & Description
            name_container = QWidget()
            name_layout = QVBoxLayout(name_container)
            name_layout.setContentsMargins(4, 2, 4, 2)
            name_layout.setSpacing(2)

            title_row = QHBoxLayout()
            title_lbl = QLabel(f"<b>{tmpl.name}</b>")
            title_lbl.setStyleSheet("color: #F8FAFC; font-size: 13px;")
            title_row.addWidget(title_lbl)

            if is_active:
                active_badge = QLabel("● ACTIVE")
                active_badge.setStyleSheet("color: #38BDF8; font-weight: bold; font-size: 10px;")
                title_row.addWidget(active_badge)
            title_row.addStretch()
            name_layout.addLayout(title_row)

            if tmpl.description:
                desc_lbl = QLabel(tmpl.description)
                desc_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
                name_layout.addWidget(desc_lbl)

            self.table.setCellWidget(row_idx, 1, name_container)

            # Col 2: Type Badge
            type_lbl = QLabel("Built-in" if is_built else "Custom Saved")
            if is_built:
                type_lbl.setStyleSheet("color: #94A3B8; font-weight: 500; font-size: 11px; padding: 2px 6px; background: #27272A; border-radius: 4px;")
            else:
                type_lbl.setStyleSheet("color: #C084FC; font-weight: 500; font-size: 11px; padding: 2px 6px; background: rgba(192, 132, 252, 0.15); border-radius: 4px;")
            type_lbl.setAlignment(Qt.AlignCenter)
            self.table.setCellWidget(row_idx, 2, type_lbl)

            # Col 3: Specifications
            elem_count = len(tmpl.elements)
            specs_lbl = QLabel(f"{tmpl.width_px}×{tmpl.height_px} px\n{tmpl.dpi} DPI · {elem_count} elements")
            specs_lbl.setStyleSheet("font-size: 11px; color: #CBD5E1;")
            specs_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.table.setCellWidget(row_idx, 3, specs_lbl)

            # Col 4: Saved File info
            file_path = self.manager.get_template_file_path(tmpl.id)
            if file_path and file_path.exists():
                file_lbl = QLabel(file_path.name)
                file_lbl.setStyleSheet("font-size: 11px; color: #64748B; font-family: monospace;")
                file_lbl.setToolTip(str(file_path))
            else:
                file_lbl = QLabel("Built-in Asset" if is_built else "—")
                file_lbl.setStyleSheet("font-size: 11px; color: #64748B;")
            file_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.table.setCellWidget(row_idx, 4, file_lbl)

            # Col 5: Actions
            actions_container = QWidget()
            actions_layout = QHBoxLayout(actions_container)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(6)

            btn_load = QPushButton("✓ Active" if is_active else "Use / Load")
            btn_load.setStyleSheet("font-size: 11px; padding: 3px 8px;")
            btn_load.clicked.connect(lambda ch=False, t=tmpl: self._on_load_clicked(t))
            actions_layout.addWidget(btn_load)

            if not is_built:
                btn_del = QPushButton("🗑 Delete")
                btn_del.setObjectName("btn_danger")
                btn_del.setStyleSheet("font-size: 11px; padding: 3px 8px; color: #F87171;")
                btn_del.setToolTip("Permanently delete this saved template file from disk")
                btn_del.clicked.connect(lambda ch=False, tid=tmpl.id, tname=tmpl.name: self._delete_single_template(tid, tname))
                actions_layout.addWidget(btn_del)

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
            f"Are you sure you want to permanently delete custom template '{template_name}' from disk?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            try:
                self.manager.delete_user_template(template_id)
                self._populate_table()
                QMessageBox.information(
                    self,
                    "Template Deleted",
                    f"Template '{template_name}' has been successfully deleted from disk.",
                )
            except Exception as e:
                logger.error("Failed to delete template %s: %s", template_id, e)
                QMessageBox.critical(self, "Delete Error", f"Could not delete template:\n{e}")

    def _delete_selected_batch(self) -> None:
        """Confirm and delete all checked custom templates."""
        selected_ids = self._get_selected_ids()
        count = len(selected_ids)
        if count == 0:
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Batch Deletion",
            f"Are you sure you want to permanently delete {count} selected template(s) from disk?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            try:
                deleted_count = self.manager.delete_user_templates_batch(selected_ids)
                self._populate_table()
                QMessageBox.information(
                    self,
                    "Templates Deleted",
                    f"Successfully deleted {deleted_count} template(s) from disk.",
                )
            except Exception as e:
                logger.error("Failed batch deleting templates: %s", e)
                QMessageBox.critical(self, "Delete Error", f"Error during deletion:\n{e}")

    def _cleanup_all_custom(self) -> None:
        """Clean up and delete all custom saved templates with safety confirmation."""
        custom_ids = [
            t.id for t in self.manager.list_templates()
            if not self.manager.is_builtin(t.id)
        ]
        count = len(custom_ids)
        if count == 0:
            QMessageBox.information(self, "Clean Up", "No custom saved templates found to clean up.")
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
                QMessageBox.information(
                    self,
                    "Clean Up Complete",
                    f"Clean up complete. Deleted {deleted_count} older custom template(s) from disk.",
                )
            except Exception as e:
                logger.error("Failed cleaning up templates: %s", e)
                QMessageBox.critical(self, "Clean Up Error", f"Error during clean up:\n{e}")
