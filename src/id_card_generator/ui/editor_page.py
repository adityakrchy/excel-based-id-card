"""Visual Canvas Editor page combining interactive scene, toolbar, inspector, and sample navigation."""

import logging
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import ImageFitMode
from id_card_generator.core.models import CanvasElement, PhotoMatchResult, SourceRecord, TemplateDefinition
from id_card_generator.editor.alignment_tools import AlignmentTools
from id_card_generator.editor.canvas_items import CanvasItem
from id_card_generator.editor.canvas_scene import CanvasScene
from id_card_generator.editor.canvas_view import CanvasView
from id_card_generator.editor.element_inspector import ElementInspector
from id_card_generator.editor.mapping_manager import MappingManager

logger = logging.getLogger(__name__)


class EditorPage(QWidget):
    """Full-featured visual WYSIWYG template editor with element library and record test bar."""

    template_updated = Signal(object)  # TemplateDefinition

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = CanvasScene(self)
        self.view = CanvasView(self.scene, self)
        self.inspector = ElementInspector(self)
        self.mapping_manager = MappingManager()

        self.records: List[SourceRecord] = []
        self.match_results: Dict[str, PhotoMatchResult] = {}
        self.sample_index = 0

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 1. Top Element & View Controls Toolbar
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("card_panel")
        tb_layout = QHBoxLayout(toolbar_frame)
        tb_layout.setContentsMargins(6, 6, 6, 6)
        tb_layout.setSpacing(6)

        # Add Elements buttons
        tb_layout.addWidget(QLabel("<b>Add:</b>"))
        self.btn_add_text = QPushButton("+ Text")
        self.btn_add_text.clicked.connect(self._add_static_text)
        tb_layout.addWidget(self.btn_add_text)

        self.btn_add_dyn = QPushButton("+ Dynamic Field")
        self.btn_add_dyn.clicked.connect(self._add_dynamic_text)
        tb_layout.addWidget(self.btn_add_dyn)

        self.btn_add_photo = QPushButton("+ Photo")
        self.btn_add_photo.clicked.connect(self._add_photo_element)
        tb_layout.addWidget(self.btn_add_photo)

        self.btn_add_pin = QPushButton("+ PIN Field")
        self.btn_add_pin.clicked.connect(self._add_pin_field)
        tb_layout.addWidget(self.btn_add_pin)

        self.btn_add_rect = QPushButton("+ Rectangle")
        self.btn_add_rect.clicked.connect(self._add_rect_element)
        tb_layout.addWidget(self.btn_add_rect)

        self.btn_add_line = QPushButton("+ Line")
        self.btn_add_line.clicked.connect(self._add_line_element)
        tb_layout.addWidget(self.btn_add_line)

        tb_layout.addSpacing(12)
        tb_layout.addWidget(QLabel("<b>Align:</b>"))
        self.btn_align_left = QPushButton("⇤ Left")
        self.btn_align_left.clicked.connect(self._align_left)
        tb_layout.addWidget(self.btn_align_left)

        self.btn_center_h = QPushButton("↔ Center")
        self.btn_center_h.clicked.connect(self._center_h)
        tb_layout.addWidget(self.btn_center_h)

        tb_layout.addSpacing(12)
        tb_layout.addWidget(QLabel("<b>Zoom:</b>"))
        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.clicked.connect(self.view.zoom_in)
        tb_layout.addWidget(self.btn_zoom_in)

        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_out.clicked.connect(self.view.zoom_out)
        tb_layout.addWidget(self.btn_zoom_out)

        self.btn_zoom_fit = QPushButton("Fit Card")
        self.btn_zoom_fit.clicked.connect(self.view.fit_to_view)
        tb_layout.addWidget(self.btn_zoom_fit)

        self.btn_zoom_100 = QPushButton("100%")
        self.btn_zoom_100.clicked.connect(self.view.reset_zoom)
        tb_layout.addWidget(self.btn_zoom_100)

        tb_layout.addStretch()

        # Delete & Duplicate
        self.btn_duplicate = QPushButton("Duplicate")
        self.btn_duplicate.clicked.connect(self.scene.duplicate_selected)
        tb_layout.addWidget(self.btn_duplicate)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("btn_danger")
        self.btn_delete.clicked.connect(self.scene.delete_selected)
        tb_layout.addWidget(self.btn_delete)

        layout.addWidget(toolbar_frame)

        # 2. Main Central Splitter (Canvas on left, Inspector on right)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.view)
        splitter.addWidget(self.inspector)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

        # 3. Bottom Test Preview Navigation Bar
        test_frame = QFrame()
        test_frame.setObjectName("card_panel")
        test_layout = QHBoxLayout(test_frame)
        test_layout.setContentsMargins(8, 6, 8, 6)

        test_layout.addWidget(QLabel("<b>Live Test Sample:</b>"))
        self.btn_sample_prev = QPushButton("◀ Prev Record")
        self.btn_sample_prev.clicked.connect(self._prev_sample)
        test_layout.addWidget(self.btn_sample_prev)

        self.lbl_sample_info = QLabel("No records loaded")
        self.lbl_sample_info.setStyleSheet("font-weight: 600; color: #38BDF8; padding: 0 10px;")
        test_layout.addWidget(self.lbl_sample_info)

        self.btn_sample_next = QPushButton("Next Record ▶")
        self.btn_sample_next.clicked.connect(self._next_sample)
        test_layout.addWidget(self.btn_sample_next)

        test_layout.addSpacing(16)
        self.txt_sample_search = QLineEdit()
        self.txt_sample_search.setPlaceholderText("Search record by PIN or Name...")
        self.txt_sample_search.returnPressed.connect(self._search_sample)
        test_layout.addWidget(self.txt_sample_search, stretch=1)

        layout.addWidget(test_frame)

    def _connect_signals(self) -> None:
        self.scene.element_selected.connect(self.inspector.set_selected_item)
        self.scene.template_modified.connect(self._on_template_modified)
        self.inspector.property_changed.connect(lambda it: self.scene.update())

    def load_template(self, template: TemplateDefinition) -> None:
        """Load template into canvas editor."""
        self.scene.load_template(template)
        self.view.fit_to_view()
        self._update_sample_preview()

    def set_dataset(
        self,
        records: List[SourceRecord],
        match_results: Dict[str, PhotoMatchResult],
        columns: List[str],
    ) -> None:
        """Set available spreadsheet dataset for live binding and preview."""
        self.records = records
        self.match_results = match_results
        self.inspector.set_available_columns(columns)
        self.sample_index = 0
        self._update_sample_preview()

    def _update_sample_preview(self) -> None:
        if not self.records:
            self.lbl_sample_info.setText("No records available")
            self.scene.set_sample_data(None, None)
            return

        self.sample_index = max(0, min(len(self.records) - 1, self.sample_index))
        rec = self.records[self.sample_index]
        match = self.match_results.get(rec.record_id)
        photo_path = match.photo_path if match else None

        name = rec.get_value("Name", "Unknown")
        self.lbl_sample_info.setText(
            f"Record {self.sample_index + 1} of {len(self.records)}: [{rec.pin}] {name}"
        )
        self.scene.set_sample_data(rec, photo_path)

    def _next_sample(self) -> None:
        if self.records and self.sample_index < len(self.records) - 1:
            self.sample_index += 1
            self._update_sample_preview()

    def _prev_sample(self) -> None:
        if self.records and self.sample_index > 0:
            self.sample_index -= 1
            self._update_sample_preview()

    def _search_sample(self) -> None:
        query = self.txt_sample_search.text().lower().strip()
        if not query or not self.records:
            return

        for idx, rec in enumerate(self.records):
            if query in rec.pin.lower() or query in rec.get_value("Name", "").lower():
                self.sample_index = idx
                self._update_sample_preview()
                break

    def _on_template_modified(self) -> None:
        if self.scene.template:
            self.template_updated.emit(self.scene.template)

    # Element Library Actions
    def _add_static_text(self) -> None:
        el = CanvasElement(
            name="Static Text",
            type="static_text",
            x=50.0,
            y=50.0,
            width=250.0,
            height=40.0,
            static_content="Sample Label",
        )
        self.scene.add_element(el)

    def _add_dynamic_text(self) -> None:
        el = CanvasElement(
            name="Dynamic Field",
            type="dynamic_text",
            x=50.0,
            y=100.0,
            width=300.0,
            height=40.0,
            binding="Name",
        )
        self.scene.add_element(el)

    def _add_photo_element(self) -> None:
        el = CanvasElement(
            name="Profile Photo",
            type="photo",
            x=100.0,
            y=150.0,
            width=180.0,
            height=180.0,
            binding="photo",
        )
        el.style.border_width = 2
        el.style.border_color = "#3B82F6"
        self.scene.add_element(el)

    def _add_pin_field(self) -> None:
        el = CanvasElement(
            name="PIN Field",
            type="pin_field",
            x=100.0,
            y=350.0,
            width=250.0,
            height=50.0,
            binding="PIN Number",
        )
        el.style.font_bold = True
        el.style.text_align = "center"
        self.scene.add_element(el)

    def _add_rect_element(self) -> None:
        el = CanvasElement(
            name="Rectangle",
            type="rect",
            x=50.0,
            y=200.0,
            width=400.0,
            height=80.0,
        )
        el.style.background_color = "#E2E8F0"
        el.style.border_width = 1
        el.style.border_color = "#CBD5E1"
        self.scene.add_element(el)

    def _add_line_element(self) -> None:
        el = CanvasElement(
            name="Divider Line",
            type="line",
            x=50.0,
            y=250.0,
            width=400.0,
            height=2.0,
        )
        el.style.background_color = "#94A3B8"
        self.scene.add_element(el)

    def _align_left(self) -> None:
        items = [it for it in self.scene.selectedItems() if isinstance(it, CanvasItem)]
        AlignmentTools.align_left(items)

    def _center_h(self) -> None:
        items = [it for it in self.scene.selectedItems() if isinstance(it, CanvasItem)]
        card_w = self.scene.template.width_px if self.scene.template else 638.0
        AlignmentTools.center_horizontally_on_card(items, card_w)
