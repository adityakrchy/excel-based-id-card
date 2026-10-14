"""Photoshop-inspired Visual Canvas Editor workspace with vertical tool strip, contextual options bar, layer hierarchy, and integrated field mapping."""

import logging
from typing import Dict, List, Optional
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import ImageFitMode
from id_card_generator.core.models import (
    CanvasElement,
    PhotoMatchResult,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.editor.alignment_tools import AlignmentTools
from id_card_generator.editor.canvas_items import CanvasItem
from id_card_generator.editor.canvas_scene import CanvasScene
from id_card_generator.editor.canvas_view import CanvasView
from id_card_generator.editor.element_inspector import ElementInspector
from id_card_generator.editor.field_mapping_panel import FieldMappingPanel
from id_card_generator.editor.layers_panel import LayersPanel

logger = logging.getLogger(__name__)


class EditorPage(QWidget):
    """Professional, Photoshop-inspired canvas editor workspace."""

    template_updated = Signal(object)  # TemplateDefinition

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = CanvasScene(self)
        self.view = CanvasView(self.scene, self)
        self.inspector = ElementInspector(self)
        self.layers_panel = LayersPanel(self.scene, self)
        self.mapping_panel = FieldMappingPanel(self)

        self.records: List[SourceRecord] = []
        self.match_results: Dict[str, PhotoMatchResult] = {}
        self.columns: List[str] = []
        self.sample_index: int = 0
        self._updating_context_bar: bool = False

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # 1. Top Contextual Options Bar
        self.options_bar = QFrame()
        self.options_bar.setObjectName("card_panel")
        self.options_bar.setFixedHeight(48)
        self.opt_layout = QHBoxLayout(self.options_bar)
        self.opt_layout.setContentsMargins(8, 4, 8, 4)
        self.opt_layout.setSpacing(8)

        # Stacked widget for contextual options
        self.stack_context = QStackedWidget()

        # Page 0: Document Default Context
        self.page_doc_context = self._create_doc_context_page()
        self.stack_context.addWidget(self.page_doc_context)

        # Page 1: Text Element Context
        self.page_text_context = self._create_text_context_page()
        self.stack_context.addWidget(self.page_text_context)

        # Page 2: Shape Element Context
        self.page_shape_context = self._create_shape_context_page()
        self.stack_context.addWidget(self.page_shape_context)

        # Page 3: Photo / Image Element Context
        self.page_photo_context = self._create_photo_context_page()
        self.stack_context.addWidget(self.page_photo_context)

        self.opt_layout.addWidget(self.stack_context, stretch=1)

        # Common action buttons on far right of options bar
        self.btn_undo = QPushButton("↶ Undo")
        self.btn_undo.setToolTip("Undo last action (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.scene.undo)
        self.opt_layout.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("↷ Redo")
        self.btn_redo.setToolTip("Redo last action (Ctrl+Y)")
        self.btn_redo.clicked.connect(self.scene.redo)
        self.opt_layout.addWidget(self.btn_redo)

        self.btn_dup = QPushButton("⧉ Duplicate")
        self.btn_dup.clicked.connect(self.scene.duplicate_selected)
        self.opt_layout.addWidget(self.btn_dup)

        self.btn_del = QPushButton("🗑 Delete")
        self.btn_del.setObjectName("btn_danger")
        self.btn_del.clicked.connect(self.scene.delete_selected)
        self.opt_layout.addWidget(self.btn_del)

        main_layout.addWidget(self.options_bar)

        # 2. Editor Central Area: Left Vertical Toolbar + Center Canvas + Right Panels
        editor_body = QHBoxLayout()
        editor_body.setSpacing(6)

        # Left Vertical Icon Toolbar (Photoshop inspired)
        self.tool_strip = self._create_vertical_tool_strip()
        editor_body.addWidget(self.tool_strip)

        # Resizable Splitter (Canvas ~70% and Right Panels ~30%)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.view)

        # Right Tabbed Dock
        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(self.inspector, "Properties")
        self.right_tabs.addTab(self.layers_panel, "Layers")
        self.right_tabs.addTab(self.mapping_panel, "Data Mapping")
        self.splitter.addWidget(self.right_tabs)

        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 3)
        editor_body.addWidget(self.splitter, stretch=1)

        main_layout.addLayout(editor_body, stretch=1)

        # 3. Bottom Status Bar Readout
        self.status_bar_frame = QFrame()
        self.status_bar_frame.setObjectName("card_panel")
        self.status_bar_frame.setFixedHeight(28)
        sb_layout = QHBoxLayout(self.status_bar_frame)
        sb_layout.setContentsMargins(10, 2, 10, 2)

        self.lbl_sb_zoom = QLabel("Zoom: 100%")
        sb_layout.addWidget(self.lbl_sb_zoom)
        sb_layout.addSpacing(16)

        self.lbl_sb_dim = QLabel("Size: 85.6 × 54.0 mm (1011 × 638 px)")
        sb_layout.addWidget(self.lbl_sb_dim)
        sb_layout.addSpacing(16)

        self.lbl_sb_dpi = QLabel("DPI: 300")
        sb_layout.addWidget(self.lbl_sb_dpi)
        sb_layout.addSpacing(16)

        self.lbl_sb_selection = QLabel("No selection")
        self.lbl_sb_selection.setStyleSheet("color: #60CDFF;")
        sb_layout.addWidget(self.lbl_sb_selection)

        sb_layout.addStretch()

        self.lbl_sb_status = QLabel("Ready")
        sb_layout.addWidget(self.lbl_sb_status)

        main_layout.addWidget(self.status_bar_frame)

    def _create_vertical_tool_strip(self) -> QFrame:
        """Create Photoshop-inspired vertical icon toolbar."""
        frame = QFrame()
        frame.setObjectName("card_panel")
        frame.setFixedWidth(52)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(6)

        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)

        tools = [
            ("select", "↖", "Select / Move Tool (V)"),
            ("static_text", "T", "Text Tool (T)"),
            ("dynamic_text", "{T}", "Dynamic Field Tool (D)"),
            ("photo", "📷", "Photo Tool (P)"),
            ("rect", "▭", "Rectangle Tool (U)"),
            ("round_rect", "▢", "Rounded Rectangle Tool (R)"),
            ("line", "―", "Line Tool (L)"),
        ]

        for tool_id, icon_char, tooltip in tools:
            btn = QToolButton()
            btn.setText(icon_char)
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setFixedSize(40, 36)
            btn.setStyleSheet("font-size: 15px; font-weight: bold;")
            if tool_id == "select":
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, tid=tool_id: self._on_tool_selected(tid))
            self.tool_group.addButton(btn)
            layout.addWidget(btn)

        layout.addSpacing(10)
        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #3F3F46;")
        layout.addWidget(sep)
        layout.addSpacing(10)

        # Zoom & Fit actions
        btn_fit = QToolButton()
        btn_fit.setText("⛶")
        btn_fit.setToolTip("Fit Card to View")
        btn_fit.setFixedSize(40, 36)
        btn_fit.clicked.connect(self.view.fit_to_view)
        layout.addWidget(btn_fit)

        btn_100 = QToolButton()
        btn_100.setText("1:1")
        btn_100.setToolTip("Zoom 100%")
        btn_100.setFixedSize(40, 36)
        btn_100.clicked.connect(self.view.reset_zoom)
        layout.addWidget(btn_100)

        layout.addStretch()
        return frame

    def _create_doc_context_page(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("<b>Document:</b>"))
        self.lbl_ctx_doc_dims = QLabel("CR80 Standard")
        layout.addWidget(self.lbl_ctx_doc_dims)

        layout.addSpacing(12)
        btn_zoom_in = QPushButton("+ Zoom")
        btn_zoom_in.clicked.connect(self.view.zoom_in)
        layout.addWidget(btn_zoom_in)

        btn_zoom_out = QPushButton("- Zoom")
        btn_zoom_out.clicked.connect(self.view.zoom_out)
        layout.addWidget(btn_zoom_out)

        layout.addStretch()
        return widget

    def _create_text_context_page(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(QLabel("<b>Text:</b>"))

        self.ctx_font_family = QFontComboBox()
        self.ctx_font_family.setFixedWidth(140)
        self.ctx_font_family.currentFontChanged.connect(self._on_ctx_font_changed)
        layout.addWidget(self.ctx_font_family)

        self.ctx_font_size = QSpinBox()
        self.ctx_font_size.setRange(6, 200)
        self.ctx_font_size.valueChanged.connect(self._on_ctx_font_size_changed)
        layout.addWidget(self.ctx_font_size)

        self.ctx_chk_bold = QCheckBox("B")
        self.ctx_chk_bold.setStyleSheet("font-weight: bold;")
        self.ctx_chk_bold.toggled.connect(self._on_ctx_bold_toggled)
        layout.addWidget(self.ctx_chk_bold)

        self.ctx_chk_italic = QCheckBox("I")
        self.ctx_chk_italic.setStyleSheet("font-style: italic;")
        self.ctx_chk_italic.toggled.connect(self._on_ctx_italic_toggled)
        layout.addWidget(self.ctx_chk_italic)

        self.ctx_btn_color = QPushButton("Color")
        self.ctx_btn_color.setFixedWidth(60)
        self.ctx_btn_color.clicked.connect(self._on_ctx_color_clicked)
        layout.addWidget(self.ctx_btn_color)

        self.ctx_cmb_align = QComboBox()
        self.ctx_cmb_align.addItems(["left", "center", "right"])
        self.ctx_cmb_align.currentTextChanged.connect(self._on_ctx_align_changed)
        layout.addWidget(self.ctx_cmb_align)

        layout.addStretch()
        return widget

    def _create_shape_context_page(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("<b>Shape:</b>"))

        self.ctx_btn_fill = QPushButton("Fill")
        self.ctx_btn_fill.clicked.connect(self._on_ctx_fill_clicked)
        layout.addWidget(self.ctx_btn_fill)

        self.ctx_btn_stroke = QPushButton("Stroke")
        self.ctx_btn_stroke.clicked.connect(self._on_ctx_stroke_clicked)
        layout.addWidget(self.ctx_btn_stroke)

        layout.addWidget(QLabel("Width:"))
        self.ctx_spin_stroke_w = QSpinBox()
        self.ctx_spin_stroke_w.setRange(0, 50)
        self.ctx_spin_stroke_w.valueChanged.connect(self._on_ctx_stroke_w_changed)
        layout.addWidget(self.ctx_spin_stroke_w)

        layout.addWidget(QLabel("Radius:"))
        self.ctx_spin_radius = QSpinBox()
        self.ctx_spin_radius.setRange(0, 500)
        self.ctx_spin_radius.valueChanged.connect(self._on_ctx_radius_changed)
        layout.addWidget(self.ctx_spin_radius)

        layout.addStretch()
        return widget

    def _create_photo_context_page(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("<b>Photo / Image:</b>"))

        layout.addWidget(QLabel("Fit:"))
        self.ctx_cmb_fit = QComboBox()
        self.ctx_cmb_fit.addItems(["cover", "contain", "stretch", "crop"])
        self.ctx_cmb_fit.currentTextChanged.connect(self._on_ctx_fit_changed)
        layout.addWidget(self.ctx_cmb_fit)

        layout.addWidget(QLabel("Mask:"))
        self.ctx_cmb_mask = QComboBox()
        self.ctx_cmb_mask.addItems(["rect", "circle", "rounded"])
        self.ctx_cmb_mask.currentTextChanged.connect(self._on_ctx_mask_changed)
        layout.addWidget(self.ctx_cmb_mask)

        layout.addStretch()
        return widget

    def _connect_signals(self) -> None:
        self.scene.element_selected.connect(self._on_element_selected)
        self.scene.template_modified.connect(self._on_template_modified)
        self.inspector.property_changed.connect(self._on_inspector_property_changed)
        self.layers_panel.item_selected.connect(self.inspector.set_selected_item)
        self.layers_panel.order_changed.connect(self._on_template_modified)

        # Field mapping panel signals
        self.mapping_panel.bind_column_requested.connect(self._bind_selected_element)
        self.mapping_panel.create_dynamic_requested.connect(self._create_dynamic_element_for_column)
        self.mapping_panel.sample_changed.connect(self._on_sample_index_changed)

    def load_template(self, template: TemplateDefinition) -> None:
        """Load template into canvas editor and update metadata readouts."""
        self.scene.load_template(template)
        self.layers_panel.refresh_layers()
        self.view.fit_to_view()
        self._update_status_dimensions()
        self._update_sample_preview()

    def set_dataset(
        self,
        records: List[SourceRecord],
        match_results: Dict[str, PhotoMatchResult],
        columns: List[str],
    ) -> None:
        """Set spreadsheet dataset for live binding and preview."""
        self.records = records
        self.match_results = match_results
        self.columns = columns
        self.inspector.set_available_columns(columns)
        self.mapping_panel.set_dataset(columns, records, match_results)
        self.sample_index = 0
        self._update_sample_preview()

    def _on_tool_selected(self, tool_id: str) -> None:
        if tool_id == "select":
            return
        elif tool_id == "static_text":
            self._add_static_text()
        elif tool_id == "dynamic_text":
            self._add_dynamic_text()
        elif tool_id == "photo":
            self._add_photo_element()
        elif tool_id == "rect":
            self._add_rect_element()
        elif tool_id == "round_rect":
            self._add_round_rect_element()
        elif tool_id == "line":
            self._add_line_element()

        # Reset selection tool
        for btn in self.tool_group.buttons():
            if btn.text() == "↖":
                btn.setChecked(True)
                break

    def _on_element_selected(self, item: Optional[CanvasItem]) -> None:
        self.inspector.set_selected_item(item)
        self.mapping_panel.set_selected_item(item)
        self._update_context_options(item)

        if item:
            elem = item.element
            self.lbl_sb_selection.setText(f"Selected: {elem.name} ({int(item.x())}, {int(item.y())}) {int(elem.width)}×{int(elem.height)}px")
        else:
            self.lbl_sb_selection.setText("No selection")

    def _update_context_options(self, item: Optional[CanvasItem]) -> None:
        if not item:
            self.stack_context.setCurrentIndex(0)
            return

        self._updating_context_bar = True
        elem = item.element
        if elem.type in ("static_text", "dynamic_text", "pin_field"):
            self.stack_context.setCurrentIndex(1)
            self.ctx_font_family.setCurrentFont(elem.style.font_family)
            self.ctx_font_size.setValue(int(elem.style.font_size))
            self.ctx_chk_bold.setChecked(elem.style.font_bold)
            self.ctx_chk_italic.setChecked(elem.style.font_italic)
            self.ctx_cmb_align.setCurrentText(elem.style.text_align)
            self.ctx_btn_color.setStyleSheet(f"background-color: {elem.style.font_color}; color: #FFFFFF;")
        elif elem.type in ("rect", "round_rect", "line"):
            self.stack_context.setCurrentIndex(2)
            self.ctx_spin_stroke_w.setValue(elem.style.border_width)
            self.ctx_spin_radius.setValue(elem.style.border_radius)
        elif elem.type in ("photo", "image"):
            self.stack_context.setCurrentIndex(3)
            self.ctx_cmb_fit.setCurrentText(str(elem.style.fit_mode.value))
            self.ctx_cmb_mask.setCurrentText(elem.style.mask_shape)
        else:
            self.stack_context.setCurrentIndex(0)

        self._updating_context_bar = False

    def _on_inspector_property_changed(self, item: CanvasItem) -> None:
        self.scene.update()
        self._update_context_options(item)
        self.layers_panel.refresh_layers()

    def _on_template_modified(self) -> None:
        self.layers_panel.refresh_layers()
        if self.scene.template:
            self.template_updated.emit(self.scene.template)

    def _update_status_dimensions(self) -> None:
        if not self.scene.template:
            return
        tmpl = self.scene.template
        w_px, h_px = tmpl.width_px, tmpl.height_px
        w_mm = tmpl.width_physical or round(w_px / tmpl.dpi * 25.4, 1)
        h_mm = tmpl.height_physical or round(h_px / tmpl.dpi * 25.4, 1)
        self.lbl_sb_dim.setText(f"Size: {w_mm} × {h_mm} mm ({w_px} × {h_px} px)")
        self.lbl_sb_dpi.setText(f"DPI: {tmpl.dpi}")
        self.lbl_ctx_doc_dims.setText(f"{tmpl.name} • {w_px} × {h_px} px @ {tmpl.dpi} DPI")

    def _update_sample_preview(self) -> None:
        if not self.records:
            self.scene.set_sample_data(None, None)
            return

        self.sample_index = max(0, min(len(self.records) - 1, self.sample_index))
        rec = self.records[self.sample_index]
        match = self.match_results.get(rec.record_id)
        photo_path = match.photo_path if match else None

        self.scene.set_sample_data(rec, photo_path)

    def _on_sample_index_changed(self, index: int) -> None:
        self.sample_index = index
        self._update_sample_preview()

    def _bind_selected_element(self, column_name: str) -> None:
        selected = [it for it in self.scene.selectedItems() if isinstance(it, CanvasItem)]
        if not selected:
            return
        item = selected[0]
        item.element.binding = column_name
        if item.element.type == "static_text":
            item.element.type = "dynamic_text"
        self.inspector.set_selected_item(item)
        self.layers_panel.refresh_layers()
        self._update_sample_preview()
        self._on_template_modified()

    def _create_dynamic_element_for_column(self, column_name: str) -> None:
        el = CanvasElement(
            name=column_name,
            type="dynamic_text",
            x=60.0,
            y=120.0,
            width=280.0,
            height=40.0,
            binding=column_name,
        )
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()
        self._update_sample_preview()

    # Contextual Options Handlers
    def _on_ctx_font_changed(self, font: QFont) -> None:
        if self._updating_context_bar:
            return
        for it in self.scene.selectedItems():
            if isinstance(it, CanvasItem):
                it.element.style.font_family = font.family()
                it.update()
        self.scene.update()

    def _on_ctx_font_size_changed(self, sz: int) -> None:
        if self._updating_context_bar:
            return
        for it in self.scene.selectedItems():
            if isinstance(it, CanvasItem):
                it.element.style.font_size = sz
                it.update()
        self.scene.update()

    def _on_ctx_bold_toggled(self, checked: bool) -> None:
        if self._updating_context_bar:
            return
        for it in self.scene.selectedItems():
            if isinstance(it, CanvasItem):
                it.element.style.font_bold = checked
                it.update()
        self.scene.update()

    def _on_ctx_italic_toggled(self, checked: bool) -> None:
        if self._updating_context_bar:
            return
        for it in self.scene.selectedItems():
            if isinstance(it, CanvasItem):
                it.element.style.font_italic = checked
                it.update()
        self.scene.update()

    def _on_ctx_color_clicked(self) -> None:
        col = QColorDialog.getColor(QColor("#1A1A1A"), self, "Select Text Color")
        if col.isValid():
            hex_col = col.name().upper()
            for it in self.scene.selectedItems():
                if isinstance(it, CanvasItem):
                    it.element.style.font_color = hex_col
                    it.update()
            self.ctx_btn_color.setStyleSheet(f"background-color: {hex_col}; color: #FFFFFF;")
            self.scene.update()

    def _on_ctx_align_changed(self, align: str) -> None:
        if self._updating_context_bar:
            return
        for it in self.scene.selectedItems():
            if isinstance(it, CanvasItem):
                it.element.style.text_align = align
                it.update()
        self.scene.update()

    def _on_ctx_fill_clicked(self) -> None:
        col = QColorDialog.getColor(QColor("#E2E8F0"), self, "Select Shape Fill Color")
        if col.isValid():
            hex_col = col.name().upper()
            for it in self.scene.selectedItems():
                if isinstance(it, CanvasItem):
                    it.element.style.background_color = hex_col
                    it.update()
            self.scene.update()

    def _on_ctx_stroke_clicked(self) -> None:
        col = QColorDialog.getColor(QColor("#0078D4"), self, "Select Shape Stroke Color")
        if col.isValid():
            hex_col = col.name().upper()
            for it in self.scene.selectedItems():
                if isinstance(it, CanvasItem):
                    it.element.style.border_color = hex_col
                    it.update()
            self.scene.update()

    def _on_ctx_stroke_w_changed(self, val: int) -> None:
        if self._updating_context_bar:
            return
        for it in self.scene.selectedItems():
            if isinstance(it, CanvasItem):
                it.element.style.border_width = val
                it.update()
        self.scene.update()

    def _on_ctx_radius_changed(self, val: int) -> None:
        if self._updating_context_bar:
            return
        for it in self.scene.selectedItems():
            if isinstance(it, CanvasItem):
                it.element.style.border_radius = val
                it.update()
        self.scene.update()

    def _on_ctx_fit_changed(self, fit_str: str) -> None:
        if self._updating_context_bar:
            return
        for it in self.scene.selectedItems():
            if isinstance(it, CanvasItem):
                it.element.style.fit_mode = ImageFitMode(fit_str)
                it.update()
        self.scene.update()

    def _on_ctx_mask_changed(self, mask_str: str) -> None:
        if self._updating_context_bar:
            return
        for it in self.scene.selectedItems():
            if isinstance(it, CanvasItem):
                it.element.style.mask_shape = mask_str
                it.update()
        self.scene.update()

    # Element Creation Methods
    def _add_static_text(self) -> None:
        el = CanvasElement(
            name="Static Label",
            type="static_text",
            x=60.0,
            y=60.0,
            width=240.0,
            height=36.0,
            static_content="Sample Text",
        )
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()

    def _add_dynamic_text(self) -> None:
        col = self.columns[0] if self.columns else "Name"
        el = CanvasElement(
            name=f"Dynamic {col}",
            type="dynamic_text",
            x=60.0,
            y=110.0,
            width=280.0,
            height=40.0,
            binding=col,
        )
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()
        self._update_sample_preview()

    def _add_photo_element(self) -> None:
        el = CanvasElement(
            name="Profile Photo",
            type="photo",
            x=80.0,
            y=160.0,
            width=180.0,
            height=200.0,
            binding="photo",
        )
        el.style.border_width = 2
        el.style.border_color = "#0078D4"
        el.style.border_radius = 8
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()
        self._update_sample_preview()

    def _add_rect_element(self) -> None:
        el = CanvasElement(
            name="Rectangle",
            type="rect",
            x=50.0,
            y=200.0,
            width=300.0,
            height=80.0,
        )
        el.style.background_color = "#27272A"
        el.style.border_width = 1
        el.style.border_color = "#3F3F46"
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()

    def _add_round_rect_element(self) -> None:
        el = CanvasElement(
            name="Rounded Card",
            type="round_rect",
            x=50.0,
            y=200.0,
            width=320.0,
            height=90.0,
        )
        el.style.background_color = "#202023"
        el.style.border_width = 1
        el.style.border_color = "#3F3F46"
        el.style.border_radius = 12
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()

    def _add_line_element(self) -> None:
        el = CanvasElement(
            name="Divider",
            type="line",
            x=50.0,
            y=240.0,
            width=350.0,
            height=2.0,
        )
        el.style.border_color = "#3F3F46"
        el.style.border_width = 2
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()
