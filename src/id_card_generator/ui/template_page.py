"""Template selection, importing, duplication, and management page."""

import logging
from pathlib import Path
from typing import List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import WorkflowStep
from id_card_generator.core.models import TemplateDefinition
from id_card_generator.templates.template_manager import TemplateManager
from id_card_generator.ui.step_nav_bar import StepNavBar

logger = logging.getLogger(__name__)


class TemplatePage(QWidget):
    """Template manager interface for choosing, importing, duplicating, and exporting templates."""

    template_selected = Signal(object)  # TemplateDefinition
    open_editor_requested = Signal()
    navigate_requested = Signal(str)  # WorkflowStep value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = TemplateManager()
        self.active_template: Optional[TemplateDefinition] = None

        self._setup_ui()
        self._load_templates()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header & Action Bar
        top_bar = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.addWidget(QLabel("<h2>ID Card Templates</h2>"))
        lbl_sub = QLabel("Select a template to use for your project, customize it in the visual editor, or import your own.")
        lbl_sub.setStyleSheet("color: #64748B;")
        title_box.addWidget(lbl_sub)
        top_bar.addLayout(title_box)

        top_bar.addStretch()

        self.btn_blank = QPushButton("+ Create Blank Canvas...")
        self.btn_blank.setObjectName("btn_primary")
        self.btn_blank.clicked.connect(self._create_blank_canvas)
        top_bar.addWidget(self.btn_blank)

        self.btn_import = QPushButton("Import Template JSON...")
        self.btn_import.clicked.connect(self._import_template)
        top_bar.addWidget(self.btn_import)

        layout.addLayout(top_bar)

        # Main Splitter: Templates List on left, Template Detail & Actions on right
        splitter = QSplitter(Qt.Horizontal)

        # Left List
        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        splitter.addWidget(self.list_widget)

        # Right Detail Card
        self.detail_card = QFrame()
        self.detail_card.setObjectName("card_panel")
        detail_layout = QVBoxLayout(self.detail_card)
        detail_layout.setSpacing(12)

        self.lbl_tmpl_title = QLabel("<b>Select a template</b>")
        self.lbl_tmpl_title.setStyleSheet("font-size: 18px;")
        detail_layout.addWidget(self.lbl_tmpl_title)

        self.lbl_tmpl_desc = QLabel("")
        self.lbl_tmpl_desc.setWordWrap(True)
        self.lbl_tmpl_desc.setStyleSheet("color: #94A3B8;")
        detail_layout.addWidget(self.lbl_tmpl_desc)

        self.lbl_tmpl_specs = QLabel("")
        self.lbl_tmpl_specs.setStyleSheet("font-family: monospace; color: #38BDF8;")
        detail_layout.addWidget(self.lbl_tmpl_specs)

        detail_layout.addStretch()

        # Action buttons
        btn_layout = QVBoxLayout()
        self.btn_use = QPushButton("Use This Template for Project")
        self.btn_use.setObjectName("btn_primary")
        self.btn_use.clicked.connect(self._use_template)
        btn_layout.addWidget(self.btn_use)

        self.btn_edit = QPushButton("Open in Visual Canvas Editor")
        self.btn_edit.clicked.connect(lambda: self.open_editor_requested.emit())
        btn_layout.addWidget(self.btn_edit)

        sub_btn_row = QHBoxLayout()
        self.btn_dup = QPushButton("Duplicate Template")
        self.btn_dup.clicked.connect(self._duplicate_template)

        self.btn_export = QPushButton("Export JSON")
        self.btn_export.clicked.connect(self._export_template)

        self.btn_delete = QPushButton("Delete Custom")
        self.btn_delete.setObjectName("btn_danger")
        self.btn_delete.clicked.connect(self._delete_template)

        sub_btn_row.addWidget(self.btn_dup)
        sub_btn_row.addWidget(self.btn_export)
        sub_btn_row.addWidget(self.btn_delete)
        btn_layout.addLayout(sub_btn_row)

        detail_layout.addLayout(btn_layout)
        splitter.addWidget(self.detail_card)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        # Bottom Step Navigation Bar
        self.nav_bar = StepNavBar(
            prev_label="Photo Library",
            next_label="Canvas Editor & Field Mapping",
            step_badge="Step 3 of 7: Template",
            parent=self,
        )
        self.nav_bar.back_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.PHOTOS.value))
        self.nav_bar.next_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.CANVAS_EDITOR.value))
        layout.addWidget(self.nav_bar)

    def _load_templates(self) -> None:
        self.manager.reload()
        self.list_widget.clear()
        templates = self.manager.list_templates()

        for tmpl in templates:
            is_built = self.manager.is_builtin(tmpl.id)
            tag = "[Built-in]" if is_built else "[Custom]"
            item = QListWidgetItem(f"{tag} {tmpl.name}")
            item.setData(Qt.UserRole, tmpl.id)
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_item_changed(self, current: Optional[QListWidgetItem], previous=None) -> None:
        if not current:
            return
        tmpl_id = current.data(Qt.UserRole)
        tmpl = self.manager.get_template(tmpl_id)
        if not tmpl:
            return

        self.active_template = tmpl
        self.lbl_tmpl_title.setText(f"<b>{tmpl.name}</b>")
        self.lbl_tmpl_desc.setText(tmpl.description or "No description provided.")
        self.lbl_tmpl_specs.setText(
            f"Dimensions: {tmpl.width_px} x {tmpl.height_px} px @ {tmpl.dpi} DPI\n"
            f"Canvas Elements: {len(tmpl.elements)}\n"
            f"Type: {'Built-in Template' if self.manager.is_builtin(tmpl.id) else 'User Custom Template'}"
        )

        self.btn_delete.setEnabled(not self.manager.is_builtin(tmpl.id))

    def _use_template(self) -> None:
        if self.active_template:
            self.template_selected.emit(self.active_template)
            QMessageBox.information(
                self,
                "Template Activated",
                f"'{self.active_template.name}' is now the active template for your project.",
            )

    def _duplicate_template(self) -> None:
        if not self.active_template:
            return
        new_name = f"{self.active_template.name} (Copy)"
        new_tmpl = self.manager.duplicate_template(self.active_template.id, new_name)
        self._load_templates()
        QMessageBox.information(self, "Template Duplicated", f"Created '{new_name}'.")

    def _import_template(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Template JSON", "", "JSON Files (*.json)")
        if file_path:
            try:
                imported = self.manager.import_template(Path(file_path))
                self._load_templates()
                QMessageBox.information(self, "Template Imported", f"Imported '{imported.name}' successfully.")
            except Exception as e:
                logger.error("Failed to import template %s: %s", file_path, e)
                QMessageBox.critical(self, "Import Error", f"Failed to import template: {e}")

    def _export_template(self) -> None:
        if not self.active_template:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Export Template JSON",
            f"{self.active_template.name.replace(' ', '_').lower()}.json",
            "JSON Files (*.json)",
        )
        if dest:
            try:
                self.manager.export_template(self.active_template.id, Path(dest))
                QMessageBox.information(self, "Export Successful", f"Saved template to {dest}.")
            except Exception as e:
                logger.error("Failed to export template: %s", e)
                QMessageBox.critical(self, "Export Error", f"Failed to export template: {e}")

    def _delete_template(self) -> None:
        if not self.active_template:
            return
        if self.manager.is_builtin(self.active_template.id):
            QMessageBox.warning(self, "Protected", "Built-in templates cannot be deleted.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete custom template '{self.active_template.name}'?",
        )
        if confirm == QMessageBox.Yes:
            self.manager.delete_user_template(self.active_template.id)
            self._load_templates()

    def _create_blank_canvas(self) -> None:
        from id_card_generator.ui.dialogs.blank_canvas_dialog import BlankCanvasDialog
        dialog = BlankCanvasDialog(self)
        if dialog.exec():
            tmpl = dialog.template_definition
            if tmpl:
                self.manager.save_user_template(tmpl)
                self._load_templates()
                # Select the new template
                for idx in range(self.list_widget.count()):
                    item = self.list_widget.item(idx)
                    if item.data(Qt.UserRole) == tmpl.id:
                        self.list_widget.setCurrentItem(item)
                        break
                self.template_selected.emit(tmpl)
                self.open_editor_requested.emit()
