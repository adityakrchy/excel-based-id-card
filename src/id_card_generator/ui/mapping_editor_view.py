"""Streamlined Data-Binding Workspace for mapping finalized template elements to spreadsheet columns."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import MatchStatus, WorkflowStep
from id_card_generator.core.models import (
    CanvasElement,
    PhotoMatchResult,
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.rendering.pillow_renderer import PillowRenderer
from id_card_generator.ui.step_nav_bar import StepNavBar

logger = logging.getLogger(__name__)


class MappingCardPreview(QFrame):
    """Authoritative ID card preview with element highlight overlay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card_panel")
        self._raw_pixmap: Optional[QPixmap] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        top = QHBoxLayout()
        lbl_head = QLabel("<b>Card Preview & Selected Element</b>")
        lbl_head.setStyleSheet("font-size: 13px; color: #E2E8F0;")
        top.addWidget(lbl_head)

        self.lbl_specs = QLabel("")
        self.lbl_specs.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: 600;")
        top.addWidget(self.lbl_specs)
        top.addStretch()
        layout.addLayout(top)

        # Preview viewport container
        self.container = QFrame()
        self.container.setStyleSheet("background-color: #0F172A; border-radius: 6px; border: 1px solid #1E293B;")
        c_layout = QVBoxLayout(self.container)
        c_layout.setAlignment(Qt.AlignCenter)
        c_layout.setContentsMargins(10, 10, 10, 10)

        self.lbl_img = QLabel("No card preview available")
        self.lbl_img.setAlignment(Qt.AlignCenter)
        self.lbl_img.setStyleSheet("color: #64748B; font-size: 12px;")
        c_layout.addWidget(self.lbl_img)

        layout.addWidget(self.container, stretch=1)

    def set_card_preview(
        self,
        pil_img: Optional[Image.Image],
        selected_elem: Optional[CanvasElement] = None,
        specs_text: str = "",
    ) -> None:
        if not pil_img:
            self._raw_pixmap = None
            self.lbl_img.setPixmap(QPixmap())
            self.lbl_img.setText("No card preview available")
            self.lbl_specs.setText("")
            return

        img_copy = pil_img.copy()
        if img_copy.mode != "RGBA":
            img_copy = img_copy.convert("RGBA")

        # If an element is selected, overlay a highlighted bounding box
        if selected_elem:
            draw = ImageDraw.Draw(img_copy, "RGBA")
            x0 = int(selected_elem.x)
            y0 = int(selected_elem.y)
            x1 = int(selected_elem.x + selected_elem.width)
            y1 = int(selected_elem.y + selected_elem.height)

            # Tint overlay
            draw.rectangle([(x0, y0), (x1, y1)], fill=(56, 189, 248, 45), outline=(56, 189, 248, 240), width=3)
            # Label tag
            tag_text = f" {selected_elem.name} "
            tag_y0 = max(0, y0 - 18)
            draw.rectangle([(x0, tag_y0), (min(img_copy.width, x0 + len(tag_text) * 8 + 10), y0)], fill=(14, 116, 144, 230))
            draw.text((x0 + 4, tag_y0 + 2), tag_text, fill=(255, 255, 255, 255))

        data = img_copy.tobytes("raw", "RGBA")
        qimg = QImage(data, img_copy.width, img_copy.height, QImage.Format_RGBA8888)
        self._raw_pixmap = QPixmap.fromImage(qimg.copy())
        self.lbl_specs.setText(specs_text)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self) -> None:
        if not self._raw_pixmap or self._raw_pixmap.isNull():
            return
        avail_w = max(100, self.container.width() - 24)
        avail_h = max(100, self.container.height() - 24)
        scaled = self._raw_pixmap.scaled(
            avail_w,
            avail_h,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.lbl_img.setPixmap(scaled)
        self.lbl_img.setText("")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_pixmap()


class MappingEditorView(QWidget):
    """Simplified, streamlined data-binding workspace without canvas drawing tools."""

    edit_template_requested = Signal()
    mappings_updated = Signal(dict)  # column_mappings Dict[str, str]
    navigate_requested = Signal(str)  # WorkflowStep value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.template: Optional[TemplateDefinition] = None
        self.records: List[SourceRecord] = []
        self.match_results: Dict[str, PhotoMatchResult] = {}
        self.columns: List[str] = []
        self.column_mappings: Dict[str, str] = {}  # elem.id -> column_name
        self.required_elements: Set[str] = set()
        self.fallback_texts: Dict[str, str] = {}
        self.empty_behaviors: Dict[str, str] = {}

        self.sample_index: int = 0
        self.selected_element: Optional[CanvasElement] = None
        self._updating_bindings = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 1. Header Bar
        header = QFrame()
        header.setObjectName("card_panel")
        header.setFixedHeight(50)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 6, 12, 6)
        h_layout.setSpacing(12)

        self.btn_edit_template = QPushButton("◀ Edit Template")
        self.btn_edit_template.setToolTip("Return to visual template designer to modify layout or styling")
        self.btn_edit_template.clicked.connect(self._on_edit_template_clicked)
        h_layout.addWidget(self.btn_edit_template)

        self.lbl_title = QLabel("<b>Data Mapping:</b> Configure Field Bindings")
        self.lbl_title.setStyleSheet("font-size: 14px; color: #F8FAFC;")
        h_layout.addWidget(self.lbl_title)

        self.lbl_status_badge = QLabel("✓ Template Finalized")
        self.lbl_status_badge.setStyleSheet(
            "background: rgba(34, 197, 94, 0.15); color: #22C55E; "
            "border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: bold;"
        )
        h_layout.addWidget(self.lbl_status_badge)

        h_layout.addStretch()

        self.btn_goto_generate = QPushButton("Batch Generate Cards ➔")
        self.btn_goto_generate.setObjectName("btn_primary")
        self.btn_goto_generate.clicked.connect(lambda: self.navigate_requested.emit(WorkflowStep.GENERATE.value))
        h_layout.addWidget(self.btn_goto_generate)

        layout.addWidget(header)

        # 2. Main Three-Column Splitter
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(6)
        self.splitter.setChildrenCollapsible(False)

        # Left Column: Elements List
        left_panel = self._create_elements_panel()
        self.splitter.addWidget(left_panel)

        # Center Column: Preview & Record Navigator
        center_panel = self._create_preview_panel()
        self.splitter.addWidget(center_panel)

        # Right Column: Binding Properties & Validation Summary
        right_panel = self._create_binding_panel()
        self.splitter.addWidget(right_panel)

        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 4)
        self.splitter.setStretchFactor(2, 3)
        self.splitter.setSizes([320, 520, 360])

        layout.addWidget(self.splitter, stretch=1)

        # 3. Bottom Step Navigation Bar
        self.nav_bar = StepNavBar(
            prev_label="Edit Template",
            next_label="Batch Generate",
            step_badge="Step 4 of 7: Data Mapping",
            parent=self,
        )
        self.nav_bar.back_requested.connect(self._on_edit_template_clicked)
        self.nav_bar.next_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.GENERATE.value))
        layout.addWidget(self.nav_bar)

    def _create_elements_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("card_panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        lbl_head = QLabel("<b>Template Elements</b>")
        lbl_head.setStyleSheet("font-size: 13px; color: #E2E8F0;")
        layout.addWidget(lbl_head)

        # Search box
        self.txt_search_elements = QLineEdit()
        self.txt_search_elements.setPlaceholderText("Filter elements...")
        self.txt_search_elements.textChanged.connect(self._filter_elements)
        layout.addWidget(self.txt_search_elements)

        # Elements List
        self.list_elements = QListWidget()
        self.list_elements.setStyleSheet("QListWidget::item { padding: 8px 6px; border-bottom: 1px solid #27272A; }")
        self.list_elements.currentItemChanged.connect(self._on_element_selected)
        layout.addWidget(self.list_elements, stretch=1)

        # Element count footer
        self.lbl_elem_counts = QLabel("0 elements")
        self.lbl_elem_counts.setStyleSheet("color: #94A3B8; font-size: 11px;")
        layout.addWidget(self.lbl_elem_counts)

        return panel

    def _create_preview_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("card_panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Sample Record Navigator
        nav_box = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.setFixedWidth(64)
        self.btn_prev.clicked.connect(self._prev_sample)
        nav_box.addWidget(self.btn_prev)

        self.lbl_record_info = QLabel("Record 0 / 0")
        self.lbl_record_info.setAlignment(Qt.AlignCenter)
        self.lbl_record_info.setStyleSheet("font-weight: 600; color: #38BDF8; font-size: 12px;")
        nav_box.addWidget(self.lbl_record_info, stretch=1)

        self.btn_next = QPushButton("Next ▶")
        self.btn_next.setFixedWidth(64)
        self.btn_next.clicked.connect(self._next_sample)
        nav_box.addWidget(self.btn_next)

        layout.addLayout(nav_box)

        # Search record
        self.txt_search_record = QLineEdit()
        self.txt_search_record.setPlaceholderText("Search record by PIN or name...")
        self.txt_search_record.returnPressed.connect(self._on_search_record)
        layout.addWidget(self.txt_search_record)

        # Photo resolution status badge
        photo_box = QHBoxLayout()
        self.lbl_photo_thumb = QLabel()
        self.lbl_photo_thumb.setFixedSize(36, 42)
        self.lbl_photo_thumb.setStyleSheet("background-color: #1E293B; border-radius: 4px; border: 1px solid #334155;")
        self.lbl_photo_thumb.setAlignment(Qt.AlignCenter)
        photo_box.addWidget(self.lbl_photo_thumb)

        self.lbl_photo_info = QLabel("No record loaded")
        self.lbl_photo_info.setStyleSheet("font-size: 11px; color: #94A3B8;")
        self.lbl_photo_info.setWordWrap(True)
        photo_box.addWidget(self.lbl_photo_info, stretch=1)
        layout.addLayout(photo_box)

        # Live Pillow Card Preview
        self.card_preview = MappingCardPreview()
        layout.addWidget(self.card_preview, stretch=1)

        return panel

    def _create_binding_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("card_panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 1. Selected Element Header
        self.grp_binding = QGroupBox("Element Data Binding")
        grp_layout = QVBoxLayout(self.grp_binding)
        grp_layout.setSpacing(8)

        self.lbl_sel_name = QLabel("Select an element on the left")
        self.lbl_sel_name.setStyleSheet("font-size: 13px; font-weight: bold; color: #38BDF8;")
        grp_layout.addWidget(self.lbl_sel_name)

        self.lbl_sel_type = QLabel("Type: —")
        self.lbl_sel_type.setStyleSheet("font-size: 11px; color: #94A3B8;")
        grp_layout.addWidget(self.lbl_sel_type)

        # Form for dynamic text binding
        self.form_text = QWidget()
        form_layout = QFormLayout(self.form_text)
        form_layout.setContentsMargins(0, 4, 0, 4)
        form_layout.setSpacing(6)

        self.combo_columns = QComboBox()
        self.combo_columns.currentIndexChanged.connect(self._on_column_changed)
        form_layout.addRow("Excel Column:", self.combo_columns)

        self.lbl_sample_val = QLabel("—")
        self.lbl_sample_val.setStyleSheet("color: #38BDF8; font-weight: 500; font-family: monospace;")
        self.lbl_sample_val.setWordWrap(True)
        form_layout.addRow("Current Value:", self.lbl_sample_val)

        self.chk_required = QCheckBox("Required Field (Cannot be empty)")
        self.chk_required.toggled.connect(self._on_required_toggled)
        form_layout.addRow("", self.chk_required)

        self.txt_fallback = QLineEdit()
        self.txt_fallback.setPlaceholderText("Fallback text if cell is empty")
        self.txt_fallback.textChanged.connect(self._on_fallback_changed)
        form_layout.addRow("Fallback Text:", self.txt_fallback)

        self.combo_empty_behavior = QComboBox()
        self.combo_empty_behavior.addItems(["Use Fallback Text", "Leave Blank / Empty", "Report Error"])
        self.combo_empty_behavior.currentTextChanged.connect(self._on_empty_behavior_changed)
        form_layout.addRow("If Missing:", self.combo_empty_behavior)

        self.lbl_text_fit = QLabel("Status: OK")
        self.lbl_text_fit.setStyleSheet("font-size: 11px; color: #22C55E;")
        form_layout.addRow("Text Fit:", self.lbl_text_fit)

        btn_row = QHBoxLayout()
        self.btn_clear_binding = QPushButton("Clear Binding")
        self.btn_clear_binding.clicked.connect(self._clear_current_binding)
        btn_row.addWidget(self.btn_clear_binding)
        btn_row.addStretch()
        form_layout.addRow("", btn_row)

        grp_layout.addWidget(self.form_text)

        # Form for photo binding
        self.form_photo = QWidget()
        photo_layout = QFormLayout(self.form_photo)
        photo_layout.setContentsMargins(0, 4, 0, 4)
        photo_layout.setSpacing(6)

        self.combo_photo_source = QComboBox()
        self.combo_photo_source.addItems([
            "Record Photograph Association (Auto-Match)",
            "Manual Override / Individual Assignment",
        ])
        photo_layout.addRow("Photo Source:", self.combo_photo_source)

        self.lbl_photo_bind_status = QLabel("Auto-bound to record photograph")
        self.lbl_photo_bind_status.setStyleSheet("color: #22C55E; font-size: 11px;")
        photo_layout.addRow("Status:", self.lbl_photo_bind_status)

        grp_layout.addWidget(self.form_photo)

        # Info widget for static elements
        self.form_static = QWidget()
        static_layout = QVBoxLayout(self.form_static)
        self.lbl_static_info = QLabel("Static element — renders fixed design and requires no spreadsheet binding.")
        self.lbl_static_info.setStyleSheet("color: #94A3B8; font-size: 11px; font-style: italic;")
        self.lbl_static_info.setWordWrap(True)
        static_layout.addWidget(self.lbl_static_info)
        grp_layout.addWidget(self.form_static)

        layout.addWidget(self.grp_binding)

        # 2. Validation Summary Panel
        val_group = QGroupBox("Mapping Validation Summary")
        val_layout = QVBoxLayout(val_group)
        val_layout.setSpacing(6)

        self.lbl_val_dynamic = QLabel("Dynamic Elements: 0")
        self.lbl_val_bound = QLabel("Bound to Columns: 0")
        self.lbl_val_unbound = QLabel("Unbound Elements: 0")
        self.lbl_val_missing_req = QLabel("Missing Required: 0")
        self.lbl_val_photos = QLabel("Unresolved Photos: 0")

        val_layout.addWidget(self.lbl_val_dynamic)
        val_layout.addWidget(self.lbl_val_bound)
        val_layout.addWidget(self.lbl_val_unbound)
        val_layout.addWidget(self.lbl_val_missing_req)
        val_layout.addWidget(self.lbl_val_photos)

        self.btn_validate = QPushButton("⟳ Re-Validate Mappings")
        self.btn_validate.clicked.connect(self._revalidate_all)
        val_layout.addWidget(self.btn_validate)

        layout.addWidget(val_group)
        layout.addStretch()

        return panel

    def set_mapping_context(
        self,
        template: TemplateDefinition,
        records: List[SourceRecord],
        match_results: Dict[str, PhotoMatchResult],
        columns: List[str],
        column_mappings: Optional[Dict[str, str]] = None,
    ) -> None:
        """Load finalized template, source dataset, photo matches, and existing column mappings."""
        self.template = template
        self.records = records
        self.match_results = match_results
        self.columns = columns
        self.sample_index = 0

        # Preserve valid bindings from existing mappings
        incoming = column_mappings or {}
        existing_elem_ids = {el.id for el in template.elements}
        reconciled: Dict[str, str] = {}

        # 1. Preserve incoming mappings for elements that still exist
        for eid, col in incoming.items():
            if eid in existing_elem_ids and (not self.columns or col in self.columns):
                reconciled[eid] = col

        # 2. Also check if element itself has binding property set
        for el in template.elements:
            if el.binding and el.id not in reconciled:
                if not self.columns or el.binding in self.columns:
                    reconciled[el.id] = el.binding

        self.column_mappings = reconciled
        self.lbl_title.setText(f"<b>Data Mapping:</b> {template.name}")

        self._refresh_columns_combo()
        self._populate_elements_list()
        self._refresh_sample_card()
        self._revalidate_all()

    def _refresh_columns_combo(self) -> None:
        self._updating_bindings = True
        self.combo_columns.clear()
        self.combo_columns.addItem("(None - Not Bound)", "")
        for col in self.columns:
            self.combo_columns.addItem(col, col)
        self._updating_bindings = False

    def _populate_elements_list(self) -> None:
        if not self.template:
            return

        self.list_elements.clear()
        search = self.txt_search_elements.text().strip().lower()

        dynamic_count = 0
        photo_count = 0
        static_count = 0

        for elem in self.template.elements:
            is_dynamic = elem.type in ("dynamic_text", "pin_field")
            is_photo = elem.type == "photo"

            if is_dynamic:
                dynamic_count += 1
            elif is_photo:
                photo_count += 1
            else:
                static_count += 1

            if search and search not in elem.name.lower() and search not in elem.type.lower():
                continue

            item = QListWidgetItem()
            item.setData(Qt.UserRole, elem.id)

            if is_dynamic:
                bound_col = self.column_mappings.get(elem.id) or elem.binding
                if bound_col:
                    icon_txt = "🔗"
                    status_txt = f"Mapped ➔ {bound_col}"
                else:
                    icon_txt = "⚠"
                    status_txt = "UNBOUND"
                item.setText(f"{icon_txt} {elem.name} ({status_txt})")
            elif is_photo:
                item.setText(f"📷 {elem.name} (Photo Placeholder)")
            elif elem.type == "static_text":
                preview = f'"{elem.static_content}"' if elem.static_content else "Empty"
                item.setText(f"T {elem.name} (Static: {preview})")
            elif elem.type == "image":
                item.setText(f"🖼 {elem.name} (Static Logo/Image)")
            else:
                item.setText(f"▭ {elem.name} (Shape / Decoration)")

            self.list_elements.addItem(item)

        self.lbl_elem_counts.setText(
            f"{len(self.template.elements)} elements ({dynamic_count} Dynamic, {photo_count} Photo, {static_count} Static)"
        )

        if self.list_elements.count() > 0:
            self.list_elements.setCurrentRow(0)

    def _filter_elements(self, text: str) -> None:
        self._populate_elements_list()

    def _on_element_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem] = None) -> None:
        if not current or not self.template:
            self.selected_element = None
            self.lbl_sel_name.setText("Select an element on the left")
            self.lbl_sel_type.setText("Type: —")
            self.form_text.setVisible(False)
            self.form_photo.setVisible(False)
            self.form_static.setVisible(False)
            self._refresh_sample_card()
            return

        elem_id = current.data(Qt.UserRole)
        elem = next((el for el in self.template.elements if el.id == elem_id), None)
        if not elem:
            return

        self.selected_element = elem
        self.lbl_sel_name.setText(elem.name)

        is_dynamic = elem.type in ("dynamic_text", "pin_field")
        is_photo = elem.type == "photo"

        if is_dynamic:
            self.lbl_sel_type.setText(f"Type: Dynamic Text ({int(elem.width)}×{int(elem.height)} px @ {int(elem.x)},{int(elem.y)})")
            self.form_text.setVisible(True)
            self.form_photo.setVisible(False)
            self.form_static.setVisible(False)

            self._updating_bindings = True
            # Update column dropdown
            bound_col = self.column_mappings.get(elem.id) or elem.binding or ""
            idx = self.combo_columns.findData(bound_col)
            if idx >= 0:
                self.combo_columns.setCurrentIndex(idx)
            else:
                self.combo_columns.setCurrentIndex(0)

            # Update required
            self.chk_required.setChecked(elem.id in self.required_elements)
            self.txt_fallback.setText(self.fallback_texts.get(elem.id, ""))
            self.combo_empty_behavior.setCurrentText(self.empty_behaviors.get(elem.id, "Use Fallback Text"))
            self._updating_bindings = False

            self._update_sample_value_display(elem, bound_col)

        elif is_photo:
            self.lbl_sel_type.setText(f"Type: Photo Placeholder ({int(elem.width)}×{int(elem.height)} px)")
            self.form_text.setVisible(False)
            self.form_photo.setVisible(True)
            self.form_static.setVisible(False)
        else:
            self.lbl_sel_type.setText(f"Type: Static Element ({elem.type})")
            self.form_text.setVisible(False)
            self.form_photo.setVisible(False)
            self.form_static.setVisible(True)

        self._refresh_sample_card()

    def _update_sample_value_display(self, elem: CanvasElement, bound_col: str) -> None:
        if not bound_col:
            self.lbl_sample_val.setText("(No column mapped)")
            self.lbl_text_fit.setText("Status: Unmapped")
            self.lbl_text_fit.setStyleSheet("color: #F59E0B; font-size: 11px;")
            return

        sample_val = ""
        if self.records and 0 <= self.sample_index < len(self.records):
            rec = self.records[self.sample_index]
            sample_val = rec.data.get(bound_col, "") if bound_col != "PIN Number" else rec.pin

        display_text = sample_val if sample_val else self.fallback_texts.get(elem.id, "")
        self.lbl_sample_val.setText(str(display_text) if display_text else "(Empty cell)")

        # Simple text length overflow check
        approx_char_width = max(6, int(elem.style.font_size * 0.55))
        max_chars_per_line = max(1, int(elem.width / approx_char_width))
        if len(str(display_text)) > max_chars_per_line * 3 and not elem.style.wrap:
            self.lbl_text_fit.setText("⚠ Long text may overflow box")
            self.lbl_text_fit.setStyleSheet("color: #EF4444; font-size: 11px; font-weight: bold;")
        else:
            self.lbl_text_fit.setText("✓ Fits comfortably")
            self.lbl_text_fit.setStyleSheet("color: #22C55E; font-size: 11px;")

    def _on_column_changed(self, idx: int) -> None:
        if self._updating_bindings or not self.selected_element:
            return
        col_data = self.combo_columns.currentData()
        elem_id = self.selected_element.id

        if col_data:
            self.column_mappings[elem_id] = col_data
            self.selected_element.binding = col_data
        else:
            self.column_mappings.pop(elem_id, None)
            self.selected_element.binding = None

        self._update_sample_value_display(self.selected_element, col_data)
        self._refresh_current_list_item()
        self._refresh_sample_card()
        self._revalidate_all()
        self.mappings_updated.emit(self.column_mappings)

    def _on_required_toggled(self, checked: bool) -> None:
        if not self.selected_element:
            return
        if checked:
            self.required_elements.add(self.selected_element.id)
        else:
            self.required_elements.discard(self.selected_element.id)
        self._revalidate_all()

    def _on_fallback_changed(self, text: str) -> None:
        if not self.selected_element:
            return
        self.fallback_texts[self.selected_element.id] = text
        bound_col = self.column_mappings.get(self.selected_element.id, "")
        self._update_sample_value_display(self.selected_element, bound_col)
        self._refresh_sample_card()

    def _on_empty_behavior_changed(self, text: str) -> None:
        if not self.selected_element:
            return
        self.empty_behaviors[self.selected_element.id] = text

    def _clear_current_binding(self) -> None:
        if not self.selected_element:
            return
        self.combo_columns.setCurrentIndex(0)

    def _refresh_current_list_item(self) -> None:
        item = self.list_elements.currentItem()
        if not item or not self.selected_element:
            return
        elem = self.selected_element
        bound_col = self.column_mappings.get(elem.id) or elem.binding
        if bound_col:
            item.setText(f"🔗 {elem.name} (Mapped ➔ {bound_col})")
        else:
            item.setText(f"⚠ {elem.name} (UNBOUND)")

    def _refresh_sample_card(self) -> None:
        if not self.template:
            self.card_preview.set_card_preview(None)
            return

        curr_rec: Optional[SourceRecord] = None
        photo_path: Optional[str] = None

        if self.records and 0 <= self.sample_index < len(self.records):
            curr_rec = self.records[self.sample_index]
            match = self.match_results.get(curr_rec.record_id)
            if match:
                photo_path = match.photo_path

            self.lbl_record_info.setText(f"Record {self.sample_index + 1} of {len(self.records)} (PIN: {curr_rec.pin})")

            # Photo status readout
            if photo_path and Path(photo_path).exists():
                self.lbl_photo_info.setText(f"✓ Photo matched: {Path(photo_path).name}")
                self.lbl_photo_info.setStyleSheet("color: #22C55E; font-size: 11px;")
                pix = QPixmap(photo_path)
                if not pix.isNull():
                    self.lbl_photo_thumb.setPixmap(pix.scaled(36, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    self.lbl_photo_thumb.setText("📷")
            else:
                self.lbl_photo_info.setText("⚠ Photo missing — policy placeholder will be used")
                self.lbl_photo_info.setStyleSheet("color: #F59E0B; font-size: 11px;")
                self.lbl_photo_thumb.setText("?")
        else:
            self.lbl_record_info.setText("No records available")
            self.lbl_photo_info.setText("No data loaded")
            self.lbl_photo_thumb.setText("—")

        # Authoritative render with PillowRenderer
        try:
            pil_img, _ = PillowRenderer.render_card(
                template=self.template,
                record=curr_rec,
                photo_path=photo_path,
                column_mappings=self.column_mappings,
                settings=RenderSettings(dpi=150),
            )
            w_px, h_px = self.template.width_px, self.template.height_px
            specs = f"{w_px}×{h_px} px @ {self.template.dpi} DPI"
            self.card_preview.set_card_preview(pil_img, self.selected_element, specs)
        except Exception as e:
            logger.error("Failed to render mapping card preview: %s", e)
            self.card_preview.set_card_preview(None)

    def _prev_sample(self) -> None:
        if not self.records:
            return
        self.sample_index = (self.sample_index - 1) % len(self.records)
        self._refresh_sample_card()
        if self.selected_element and self.selected_element.type in ("dynamic_text", "pin_field"):
            bound_col = self.column_mappings.get(self.selected_element.id, "")
            self._update_sample_value_display(self.selected_element, bound_col)

    def _next_sample(self) -> None:
        if not self.records:
            return
        self.sample_index = (self.sample_index + 1) % len(self.records)
        self._refresh_sample_card()
        if self.selected_element and self.selected_element.type in ("dynamic_text", "pin_field"):
            bound_col = self.column_mappings.get(self.selected_element.id, "")
            self._update_sample_value_display(self.selected_element, bound_col)

    def _on_search_record(self) -> None:
        q = self.txt_search_record.text().strip().lower()
        if not q or not self.records:
            return
        for i, rec in enumerate(self.records):
            if q in rec.pin.lower() or any(q in str(v).lower() for v in rec.data.values()):
                self.sample_index = i
                self._refresh_sample_card()
                break

    def _revalidate_all(self) -> None:
        if not self.template:
            return

        dynamic_elements = [el for el in self.template.elements if el.type in ("dynamic_text", "pin_field")]
        bound_count = sum(1 for el in dynamic_elements if self.column_mappings.get(el.id) or el.binding)
        unbound_count = len(dynamic_elements) - bound_count

        missing_req_count = 0
        if self.records and self.required_elements:
            for rec in self.records:
                for req_id in self.required_elements:
                    col = self.column_mappings.get(req_id)
                    val = rec.data.get(col) if (col and col != "PIN Number") else (rec.pin if col == "PIN Number" else None)
                    if not col or not val:
                        missing_req_count += 1
                        break

        missing_photos = sum(1 for m in self.match_results.values() if not m.photo_path)

        self.lbl_val_dynamic.setText(f"Dynamic Elements: {len(dynamic_elements)}")
        self.lbl_val_bound.setText(f"Bound to Columns: {bound_count}")
        self.lbl_val_bound.setStyleSheet("color: #22C55E; font-weight: 500;")

        self.lbl_val_unbound.setText(f"Unbound Elements: {unbound_count}")
        if unbound_count > 0:
            self.lbl_val_unbound.setStyleSheet("color: #F59E0B; font-weight: 600;")
        else:
            self.lbl_val_unbound.setStyleSheet("color: #94A3B8;")

        self.lbl_val_missing_req.setText(f"Missing Required Values: {missing_req_count}")
        if missing_req_count > 0:
            self.lbl_val_missing_req.setStyleSheet("color: #EF4444; font-weight: 600;")
        else:
            self.lbl_val_missing_req.setStyleSheet("color: #94A3B8;")

        self.lbl_val_photos.setText(f"Missing Photos in Dataset: {missing_photos}")
        if missing_photos > 0:
            self.lbl_val_photos.setStyleSheet("color: #F59E0B;")
        else:
            self.lbl_val_photos.setStyleSheet("color: #94A3B8;")

    def _on_edit_template_clicked(self) -> None:
        """User explicitly requested returning to visual template designer."""
        self.edit_template_requested.emit()
