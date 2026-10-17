"""Template selection, visual canvas preview, property editing, importing, duplication, and management page."""

import logging
from pathlib import Path
from typing import List, Optional
from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import WorkflowStep
from id_card_generator.core.geometry import convert_unit
from id_card_generator.core.models import (
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.rendering.pillow_renderer import PillowRenderer
from id_card_generator.templates.template_manager import TemplateManager
from id_card_generator.ui.dialogs.blank_canvas_dialog import (
    BlankCanvasDialog,
    CanvasPropertiesDialog,
)
from id_card_generator.ui.dialogs.template_cleanup_dialog import TemplateCleanupDialog
from id_card_generator.ui.step_nav_bar import StepNavBar

logger = logging.getLogger(__name__)


class CanvasPreviewCard(QFrame):
    """Visual preview card container that renders and responsively scales ID card canvas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card_panel")
        self._original_pixmap: Optional[QPixmap] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Header bar
        header = QHBoxLayout()
        self.lbl_header = QLabel("<b>Live Canvas Preview</b>")
        self.lbl_header.setStyleSheet("font-size: 14px;")
        header.addWidget(self.lbl_header)

        self.lbl_badge = QLabel("")
        self.lbl_badge.setStyleSheet(
            "background: rgba(56, 189, 248, 0.15); color: #38BDF8; "
            "border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: bold;"
        )
        header.addWidget(self.lbl_badge)
        header.addStretch()

        self.btn_refresh = QPushButton("⟳ Refresh")
        self.btn_refresh.setToolTip("Re-render canvas preview")
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        # Center card container
        self.image_container = QFrame()
        self.image_container.setStyleSheet(
            "background-color: #0F172A; border-radius: 8px; border: 1px solid #1E293B;"
        )
        container_layout = QVBoxLayout(self.image_container)
        container_layout.setContentsMargins(16, 16, 16, 16)
        container_layout.setAlignment(Qt.AlignCenter)

        self.lbl_image = QLabel("No template selected")
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setStyleSheet("color: #64748B; font-size: 13px;")
        container_layout.addWidget(self.lbl_image)

        layout.addWidget(self.image_container, stretch=1)

    def set_preview(self, pixmap: Optional[QPixmap], specs_text: str = "") -> None:
        self._original_pixmap = pixmap
        if specs_text:
            self.lbl_badge.setText(specs_text)
            self.lbl_badge.setVisible(True)
        else:
            self.lbl_badge.setVisible(False)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self) -> None:
        if not self._original_pixmap or self._original_pixmap.isNull():
            self.lbl_image.setPixmap(QPixmap())
            self.lbl_image.setText("No template preview available")
            return

        avail_w = max(100, self.image_container.width() - 36)
        avail_h = max(100, self.image_container.height() - 36)

        scaled = self._original_pixmap.scaled(
            avail_w,
            avail_h,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.lbl_image.setPixmap(scaled)
        self.lbl_image.setText("")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scaled_pixmap()


class TemplatePage(QWidget):
    """Template manager interface for choosing, previewing, property-editing, importing, duplicating, and exporting templates."""

    template_selected = Signal(object)  # TemplateDefinition
    open_editor_requested = Signal()
    navigate_requested = Signal(str)  # WorkflowStep value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = TemplateManager()
        self.active_template: Optional[TemplateDefinition] = None
        self.sample_record: Optional[SourceRecord] = None

        self._current_bg_color = "#FFFFFF"
        self._current_bg_image_path: Optional[str] = None
        self._updating_ui = False

        self._setup_ui()
        self._load_templates()

    def set_sample_record(self, record: Optional[SourceRecord] = None) -> None:
        """Set sample data record for rendering realistic card preview."""
        self.sample_record = record
        if self.active_template:
            self._update_preview(self.active_template)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header & Action Bar
        top_bar = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.addWidget(QLabel("<h2>ID Card Templates</h2>"))
        lbl_sub = QLabel(
            "Select, preview, and edit canvas template specifications before opening the mapping editor."
        )
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

        self.btn_cleanup = QPushButton("🧹 Clean Up Saved Templates...")
        self.btn_cleanup.setToolTip("Open template cleanup manager to search, delete, and clean up older saved templates")
        self.btn_cleanup.clicked.connect(self._open_cleanup_dialog)
        top_bar.addWidget(self.btn_cleanup)

        layout.addLayout(top_bar)

        # Main Splitter: Left List (templates) vs Right Workspace (preview + properties)
        main_splitter = QSplitter(Qt.Horizontal)

        # Left List Panel
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        lbl_list_title = QLabel("<b>Available Templates</b>")
        lbl_list_title.setStyleSheet("font-size: 13px; color: #94A3B8;")
        left_layout.addWidget(lbl_list_title)

        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("🔍 Filter templates...")
        self.txt_filter.setClearButtonEnabled(True)
        self.txt_filter.textChanged.connect(self._filter_template_list)
        left_layout.addWidget(self.txt_filter)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        left_layout.addWidget(self.list_widget, stretch=1)

        lbl_hint = QLabel("💡 <i>Double-click any template to edit canvas properties</i>")
        lbl_hint.setStyleSheet("font-size: 11px; color: #64748B; padding: 2px;")
        left_layout.addWidget(lbl_hint)

        main_splitter.addWidget(left_panel)

        # Right Splitter: Center Preview Card (stretch 3) and Right Canvas Properties (stretch 2)
        right_splitter = QSplitter(Qt.Horizontal)

        # Center Preview Card
        self.preview_card = CanvasPreviewCard()
        self.preview_card.btn_refresh.clicked.connect(self._refresh_current_preview)
        right_splitter.addWidget(self.preview_card)

        # Right Detail & Canvas Properties Card
        self.detail_card = QFrame()
        self.detail_card.setObjectName("card_panel")
        detail_layout = QVBoxLayout(self.detail_card)
        detail_layout.setContentsMargins(14, 12, 14, 12)
        detail_layout.setSpacing(10)

        # Header with title and badge
        header_row = QHBoxLayout()
        self.lbl_tmpl_title = QLabel("<b>Select a template</b>")
        self.lbl_tmpl_title.setStyleSheet("font-size: 16px;")
        header_row.addWidget(self.lbl_tmpl_title)

        self.lbl_tmpl_badge = QLabel("")
        self.lbl_tmpl_badge.setStyleSheet("font-size: 11px; font-weight: bold; color: #38BDF8;")
        header_row.addWidget(self.lbl_tmpl_badge)
        header_row.addStretch()
        detail_layout.addLayout(header_row)

        # Scrollable Properties form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        prop_container = QWidget()
        prop_layout = QVBoxLayout(prop_container)
        prop_layout.setContentsMargins(2, 2, 2, 2)
        prop_layout.setSpacing(10)

        # 1. Identity Group
        grp_overview = QGroupBox("Canvas Identity")
        overview_layout = QFormLayout(grp_overview)

        self.txt_tmpl_name = QLineEdit()
        self.txt_tmpl_name.setPlaceholderText("Template Name")
        self.txt_tmpl_name.textChanged.connect(self._on_inline_name_changed)
        overview_layout.addRow("Name:", self.txt_tmpl_name)

        self.txt_tmpl_desc = QLineEdit()
        self.txt_tmpl_desc.setPlaceholderText("Optional description")
        overview_layout.addRow("Description:", self.txt_tmpl_desc)
        prop_layout.addWidget(grp_overview)

        # 2. Dimensions & Quality Specifications Group
        grp_specs = QGroupBox("Dimensions & Specifications")
        specs_layout = QVBoxLayout(grp_specs)
        self.lbl_tmpl_specs = QLabel("")
        self.lbl_tmpl_specs.setStyleSheet("font-family: monospace; color: #38BDF8; font-size: 11px; line-height: 1.4;")
        specs_layout.addWidget(self.lbl_tmpl_specs)
        prop_layout.addWidget(grp_specs)

        # 3. Surface & Background Properties Group
        grp_surface = QGroupBox("Card Surface & Background")
        surface_layout = QFormLayout(grp_surface)

        color_row = QHBoxLayout()
        self.btn_prop_bg_color = QPushButton()
        self.btn_prop_bg_color.setFixedSize(36, 22)
        self.btn_prop_bg_color.clicked.connect(self._pick_prop_color)
        color_row.addWidget(self.btn_prop_bg_color)

        self.lbl_prop_bg_hex = QLabel("#FFFFFF")
        color_row.addWidget(self.lbl_prop_bg_hex)

        btn_change_col = QPushButton("Change Color...")
        btn_change_col.clicked.connect(self._pick_prop_color)
        color_row.addWidget(btn_change_col)
        color_row.addStretch()
        surface_layout.addRow("Background:", color_row)

        img_row = QHBoxLayout()
        self.lbl_prop_bg_img = QLabel("(None)")
        self.lbl_prop_bg_img.setStyleSheet("color: #94A3B8; font-size: 11px;")
        img_row.addWidget(self.lbl_prop_bg_img)

        btn_browse_bg = QPushButton("Browse...")
        btn_browse_bg.clicked.connect(self._browse_prop_image)
        img_row.addWidget(btn_browse_bg)

        btn_clear_bg = QPushButton("Clear")
        btn_clear_bg.clicked.connect(self._clear_prop_image)
        img_row.addWidget(btn_clear_bg)
        surface_layout.addRow("Background Image:", img_row)
        prop_layout.addWidget(grp_surface)

        prop_layout.addStretch()
        scroll.setWidget(prop_container)
        detail_layout.addWidget(scroll, stretch=1)

        # Action Buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(6)

        self.btn_save_prop = QPushButton("💾 Save Canvas Properties")
        self.btn_save_prop.setToolTip("Save edited canvas properties to this template")
        self.btn_save_prop.clicked.connect(self._save_inline_properties)
        btn_layout.addWidget(self.btn_save_prop)

        self.btn_edit_specs = QPushButton("⚙ Edit Canvas Properties (Dimensions / DPI)...")
        self.btn_edit_specs.setToolTip("Open dialog to edit dimensions, DPI, orientation, and presets")
        self.btn_edit_specs.clicked.connect(lambda: self._edit_canvas_properties())
        btn_layout.addWidget(self.btn_edit_specs)

        self.btn_use = QPushButton("Use This Template for Project")
        self.btn_use.setObjectName("btn_primary")
        self.btn_use.clicked.connect(self._use_template)
        btn_layout.addWidget(self.btn_use)

        self.btn_edit = QPushButton("Open in Visual Canvas Editor")
        self.btn_edit.clicked.connect(lambda: self.open_editor_requested.emit())
        btn_layout.addWidget(self.btn_edit)

        sub_btn_row = QHBoxLayout()
        self.btn_dup = QPushButton("Duplicate")
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
        right_splitter.addWidget(self.detail_card)

        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)
        main_splitter.addWidget(right_splitter)

        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 4)
        layout.addWidget(main_splitter, stretch=1)

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

        self._updating_ui = True
        self.active_template = tmpl
        is_built = self.manager.is_builtin(tmpl.id)

        self.lbl_tmpl_title.setText(f"<b>{tmpl.name}</b>")
        self.lbl_tmpl_badge.setText("[Built-in Template]" if is_built else "[User Custom Template]")
        self.txt_tmpl_name.setText(tmpl.name)
        self.txt_tmpl_desc.setText(tmpl.description or "")

        # Compute physical dimensions readout
        unit = tmpl.unit or "mm"
        if tmpl.width_physical and tmpl.height_physical:
            w_phys = tmpl.width_physical
            h_phys = tmpl.height_physical
        else:
            w_mm = tmpl.width_px / tmpl.dpi * 25.4
            h_mm = tmpl.height_px / tmpl.dpi * 25.4
            w_phys = convert_unit(w_mm, "mm", unit)
            h_phys = convert_unit(h_mm, "mm", unit)

        orient = tmpl.orientation.title() if tmpl.orientation else ("Landscape" if tmpl.is_landscape else "Portrait")
        element_summary = f"{len(tmpl.elements)} elements"

        self.lbl_tmpl_specs.setText(
            f"Physical Size: {w_phys:.2f} × {h_phys:.2f} {unit}\n"
            f"Canvas Pixels: {tmpl.width_px} × {tmpl.height_px} px\n"
            f"Print Quality: {tmpl.dpi} DPI\n"
            f"Orientation:   {orient}\n"
            f"Elements:      {element_summary}"
        )

        # Background color & image
        self._current_bg_color = tmpl.background_color or "#FFFFFF"
        self._update_prop_color_btn()

        self._current_bg_image_path = tmpl.background_image_path
        if tmpl.background_image_path:
            self.lbl_prop_bg_img.setText(Path(tmpl.background_image_path).name)
        else:
            self.lbl_prop_bg_img.setText("(None)")

        self.btn_delete.setEnabled(not is_built)
        self._updating_ui = False

        # Live Canvas Preview
        self._update_preview(tmpl)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Double clicking a template item directly opens the canvas property editor dialog."""
        tmpl_id = item.data(Qt.UserRole)
        tmpl = self.manager.get_template(tmpl_id)
        if tmpl:
            self._edit_canvas_properties(tmpl)

    def _on_inline_name_changed(self, text: str) -> None:
        if not self._updating_ui:
            self.lbl_tmpl_title.setText(f"<b>{text.strip() or 'Untitled Template'}</b>")

    def _pick_prop_color(self) -> None:
        col = QColorDialog.getColor(QColor(self._current_bg_color), self, "Select Card Background Color")
        if col.isValid():
            self._current_bg_color = col.name().upper()
            self._update_prop_color_btn()
            # Live-preview the change immediately
            if self.active_template:
                temp_preview = self.active_template.model_copy(deep=True)
                temp_preview.background_color = self._current_bg_color
                temp_preview.background_image_path = self._current_bg_image_path
                self._update_preview(temp_preview)

    def _update_prop_color_btn(self) -> None:
        self.btn_prop_bg_color.setStyleSheet(
            f"background-color: {self._current_bg_color}; border: 1px solid #64748B; border-radius: 4px;"
        )
        self.lbl_prop_bg_hex.setText(self._current_bg_color)

    def _browse_prop_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Background Image",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            self._current_bg_image_path = path
            self.lbl_prop_bg_img.setText(Path(path).name)
            if self.active_template:
                temp_preview = self.active_template.model_copy(deep=True)
                temp_preview.background_color = self._current_bg_color
                temp_preview.background_image_path = self._current_bg_image_path
                self._update_preview(temp_preview)

    def _clear_prop_image(self) -> None:
        self._current_bg_image_path = None
        self.lbl_prop_bg_img.setText("(None)")
        if self.active_template:
            temp_preview = self.active_template.model_copy(deep=True)
            temp_preview.background_color = self._current_bg_color
            temp_preview.background_image_path = None
            self._update_preview(temp_preview)

    def _save_inline_properties(self) -> None:
        """Save inline canvas property edits (name, description, background) to template."""
        if not self.active_template:
            return

        updated = self.active_template.model_copy(deep=True)
        updated.name = self.txt_tmpl_name.text().strip() or updated.name
        updated.description = self.txt_tmpl_desc.text().strip()
        updated.background_color = self._current_bg_color
        updated.background_image_path = self._current_bg_image_path

        if self.manager.is_builtin(updated.id) and not updated.name.endswith("(Custom)"):
            updated.name = f"{updated.name} (Custom)"

        self.manager.save_user_template(updated)
        self._load_templates()

        for idx in range(self.list_widget.count()):
            it = self.list_widget.item(idx)
            if it.data(Qt.UserRole) == updated.id:
                self.list_widget.setCurrentItem(it)
                break

        self.template_selected.emit(updated)
        QMessageBox.information(
            self,
            "Canvas Properties Saved",
            f"Canvas properties for '{updated.name}' have been saved.",
        )

    def _edit_canvas_properties(self, tmpl: Optional[TemplateDefinition] = None) -> None:
        """Open full modal dialog to edit canvas physical dimensions, DPI, orientation, and background."""
        target = tmpl or self.active_template
        if not target:
            return

        dialog = CanvasPropertiesDialog(self, existing_template=target)
        if dialog.exec():
            updated = dialog.template_definition
            if updated:
                if self.manager.is_builtin(updated.id) and not updated.name.endswith("(Custom)"):
                    updated.name = f"{updated.name} (Custom)"

                self.manager.save_user_template(updated)
                self._load_templates()

                # Re-select the updated template
                for idx in range(self.list_widget.count()):
                    it = self.list_widget.item(idx)
                    if it.data(Qt.UserRole) == updated.id:
                        self.list_widget.setCurrentItem(it)
                        break

                self.template_selected.emit(updated)
                QMessageBox.information(
                    self,
                    "Canvas Properties Updated",
                    f"Canvas properties for '{updated.name}' updated successfully.",
                )

    def _update_preview(self, tmpl: TemplateDefinition) -> None:
        """Render high quality ID card canvas preview using PillowRenderer."""
        try:
            pil_img, _ = PillowRenderer.render_card(
                template=tmpl,
                record=self.sample_record,
            )
            if pil_img.mode != "RGBA":
                pil_img = pil_img.convert("RGBA")
            data = pil_img.tobytes("raw", "RGBA")
            qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format_RGBA8888)
            pix = QPixmap.fromImage(qimg.copy())

            unit = tmpl.unit or "mm"
            if tmpl.width_physical and tmpl.height_physical:
                w_str = f"{tmpl.width_physical:.1f} × {tmpl.height_physical:.1f} {unit}"
            else:
                w_mm = tmpl.width_px / tmpl.dpi * 25.4
                h_mm = tmpl.height_px / tmpl.dpi * 25.4
                w_str = f"{w_mm:.1f} × {h_mm:.1f} mm"

            orient_icon = "↔" if tmpl.is_landscape else "↕"
            specs_badge = f"{w_str} ({tmpl.width_px}×{tmpl.height_px} px) @ {tmpl.dpi} DPI {orient_icon}"

            self.preview_card.set_preview(pix, specs_badge)
        except Exception as e:
            logger.error("Failed to render preview for template %s: %s", tmpl.name, e)
            self.preview_card.set_preview(None, "Preview unavailable")

    def _refresh_current_preview(self) -> None:
        if self.active_template:
            self._update_preview(self.active_template)

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
        for idx in range(self.list_widget.count()):
            it = self.list_widget.item(idx)
            if it.data(Qt.UserRole) == new_tmpl.id:
                self.list_widget.setCurrentItem(it)
                break
        QMessageBox.information(self, "Template Duplicated", f"Created '{new_name}'.")

    def _import_template(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Template JSON", "", "JSON Files (*.json)")
        if file_path:
            try:
                imported = self.manager.import_template(Path(file_path))
                self._load_templates()
                for idx in range(self.list_widget.count()):
                    it = self.list_widget.item(idx)
                    if it.data(Qt.UserRole) == imported.id:
                        self.list_widget.setCurrentItem(it)
                        break
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
        dialog = BlankCanvasDialog(self)
        if dialog.exec():
            tmpl = dialog.template_definition
            if tmpl:
                self.manager.save_user_template(tmpl)
                self._load_templates()
                for idx in range(self.list_widget.count()):
                    item = self.list_widget.item(idx)
                    if item.data(Qt.UserRole) == tmpl.id:
                        self.list_widget.setCurrentItem(item)
                        break
                self.template_selected.emit(tmpl)
                self.open_editor_requested.emit()

    def _open_cleanup_dialog(self) -> None:
        """Open modal cleanup dialog to search, delete, and clean up older templates."""
        active_id = self.active_template.id if self.active_template else ""
        dialog = TemplateCleanupDialog(self, active_template_id=active_id)
        dialog.template_selected.connect(self._on_template_selected_from_dialog)
        dialog.exec()
        self.manager.reload()
        self._load_templates()

    def _on_template_selected_from_dialog(self, template: TemplateDefinition) -> None:
        """Handle template selected from cleanup dialog."""
        self.manager.reload()
        self._load_templates()
        for idx in range(self.list_widget.count()):
            it = self.list_widget.item(idx)
            if it.data(Qt.UserRole) == template.id:
                self.list_widget.setCurrentItem(it)
                break

    def _filter_template_list(self, text: str) -> None:
        """Filter the templates list widget based on search text."""
        query = text.strip().lower()
        for idx in range(self.list_widget.count()):
            it = self.list_widget.item(idx)
            tmpl_id = it.data(Qt.UserRole)
            tmpl = self.manager.get_template(tmpl_id)
            if not tmpl or not query:
                it.setHidden(False)
            else:
                match = (
                    query in tmpl.name.lower()
                    or query in (tmpl.description or "").lower()
                    or query in tmpl.id.lower()
                )
                it.setHidden(not match)
