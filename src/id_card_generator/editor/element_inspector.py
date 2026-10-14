"""Properties inspector panel for editing selected canvas element attributes."""

import logging
from typing import List, Optional
from PySide6.QtCore import QPointF, QRectF, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import ImageFitMode
from id_card_generator.core.models import CanvasElement
from id_card_generator.editor.canvas_items import CanvasItem

logger = logging.getLogger(__name__)


class ElementInspector(QWidget):
    """Right-side dock/panel allowing precise property editing of the selected element."""

    property_changed = Signal(object)  # CanvasItem

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_item: Optional[CanvasItem] = None
        self._updating = False
        self._available_columns: List[str] = []

        self._setup_ui()

    def set_available_columns(self, columns: List[str]) -> None:
        """Update available spreadsheet column bindings."""
        self._available_columns = columns
        self._refresh_binding_combo()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Header
        self.lbl_title = QLabel("<b>Element Properties</b>")
        main_layout.addWidget(self.lbl_title)

        # Scroll Area for properties
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.form_layout = QVBoxLayout(container)
        self.form_layout.setContentsMargins(4, 4, 4, 4)
        self.form_layout.setSpacing(10)

        # 1. Identity & Geometry Group
        geom_group = QGroupBox("Transform & Position")
        geom_layout = QFormLayout(geom_group)

        self.txt_name = QLineEdit()
        self.txt_name.textChanged.connect(self._on_name_changed)
        geom_layout.addRow("Name:", self.txt_name)

        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-5000, 5000)
        self.spin_x.valueChanged.connect(self._on_pos_changed)
        geom_layout.addRow("X (px):", self.spin_x)

        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-5000, 5000)
        self.spin_y.valueChanged.connect(self._on_pos_changed)
        geom_layout.addRow("Y (px):", self.spin_y)

        self.spin_w = QDoubleSpinBox()
        self.spin_w.setRange(5, 5000)
        self.spin_w.valueChanged.connect(self._on_size_changed)
        geom_layout.addRow("Width:", self.spin_w)

        self.spin_h = QDoubleSpinBox()
        self.spin_h.setRange(5, 5000)
        self.spin_h.valueChanged.connect(self._on_size_changed)
        geom_layout.addRow("Height:", self.spin_h)

        self.chk_locked = QCheckBox("Lock element on canvas")
        self.chk_locked.toggled.connect(self._on_lock_toggled)
        geom_layout.addRow("", self.chk_locked)

        self.form_layout.addWidget(geom_group)

        # 2. Data Binding Group
        binding_group = QGroupBox("Data Binding")
        binding_layout = QFormLayout(binding_group)

        self.cmb_binding = QComboBox()
        self.cmb_binding.currentIndexChanged.connect(self._on_binding_changed)
        binding_layout.addRow("Bind Column:", self.cmb_binding)

        self.txt_static = QLineEdit()
        self.txt_static.textChanged.connect(self._on_static_changed)
        binding_layout.addRow("Static Text:", self.txt_static)

        self.form_layout.addWidget(binding_group)

        # 3. Typography Group
        self.type_group = QGroupBox("Typography")
        type_layout = QFormLayout(self.type_group)

        self.cmb_font = QFontComboBox()
        self.cmb_font.currentFontChanged.connect(self._on_font_changed)
        type_layout.addRow("Font:", self.cmb_font)

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(6, 144)
        self.spin_font_size.valueChanged.connect(self._on_font_size_changed)
        type_layout.addRow("Size:", self.spin_font_size)

        style_row = QHBoxLayout()
        self.chk_bold = QCheckBox("Bold")
        self.chk_bold.toggled.connect(self._on_bold_toggled)
        self.chk_italic = QCheckBox("Italic")
        self.chk_italic.toggled.connect(self._on_italic_toggled)
        style_row.addWidget(self.chk_bold)
        style_row.addWidget(self.chk_italic)
        type_layout.addRow("Style:", style_row)

        self.btn_font_color = QPushButton("Pick Color")
        self.btn_font_color.clicked.connect(self._pick_font_color)
        type_layout.addRow("Text Color:", self.btn_font_color)

        self.cmb_align = QComboBox()
        self.cmb_align.addItems(["left", "center", "right"])
        self.cmb_align.currentTextChanged.connect(self._on_align_changed)
        type_layout.addRow("Align:", self.cmb_align)

        self.form_layout.addWidget(self.type_group)

        # 4. Appearance & Borders Group
        self.app_group = QGroupBox("Appearance & Borders")
        app_layout = QFormLayout(self.app_group)

        self.btn_bg_color = QPushButton("Pick Fill Color")
        self.btn_bg_color.clicked.connect(self._pick_bg_color)
        app_layout.addRow("Background:", self.btn_bg_color)

        self.btn_border_color = QPushButton("Pick Border Color")
        self.btn_border_color.clicked.connect(self._pick_border_color)
        app_layout.addRow("Border Color:", self.btn_border_color)

        self.spin_border_width = QSpinBox()
        self.spin_border_width.setRange(0, 50)
        self.spin_border_width.valueChanged.connect(self._on_border_width_changed)
        app_layout.addRow("Border Width:", self.spin_border_width)

        self.spin_border_radius = QSpinBox()
        self.spin_border_radius.setRange(0, 500)
        self.spin_border_radius.valueChanged.connect(self._on_border_radius_changed)
        app_layout.addRow("Corner Radius:", self.spin_border_radius)

        self.form_layout.addWidget(self.app_group)

        # 5. Image & Masking Group
        self.img_group = QGroupBox("Photo / Image Options")
        img_layout = QFormLayout(self.img_group)

        self.cmb_mask = QComboBox()
        self.cmb_mask.addItems(["rect", "circle", "rounded"])
        self.cmb_mask.currentTextChanged.connect(self._on_mask_changed)
        img_layout.addRow("Mask Shape:", self.cmb_mask)

        self.cmb_fit = QComboBox()
        self.cmb_fit.addItems(["cover", "contain", "stretch", "crop"])
        self.cmb_fit.currentTextChanged.connect(self._on_fit_changed)
        img_layout.addRow("Fit Mode:", self.cmb_fit)

        self.form_layout.addWidget(self.img_group)

        self.form_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        self.setEnabled(False)

    def set_selected_item(self, item: Optional[CanvasItem]) -> None:
        """Bind selected item to inspector form controls."""
        self._current_item = item
        if not item:
            self.lbl_title.setText("<i>No element selected</i>")
            self.setEnabled(False)
            return

        self.setEnabled(True)
        self._updating = True
        elem = item.element
        self.lbl_title.setText(f"<b>{elem.name}</b> ({elem.type})")

        # Position & Size
        self.txt_name.setText(elem.name)
        self.spin_x.setValue(item.pos().x())
        self.spin_y.setValue(item.pos().y())
        self.spin_w.setValue(elem.width)
        self.spin_h.setValue(elem.height)
        self.chk_locked.setChecked(elem.locked)

        # Binding
        self._refresh_binding_combo()
        if elem.binding:
            idx = self.cmb_binding.findText(elem.binding)
            if idx >= 0:
                self.cmb_binding.setCurrentIndex(idx)
        else:
            self.cmb_binding.setCurrentIndex(0)

        self.txt_static.setText(elem.static_content or "")

        # Typography
        self.cmb_font.setCurrentFont(elem.style.font_family)
        self.spin_font_size.setValue(int(elem.style.font_size))
        self.chk_bold.setChecked(elem.style.font_bold)
        self.chk_italic.setChecked(elem.style.font_italic)
        self.cmb_align.setCurrentText(elem.style.text_align)
        self.btn_font_color.setStyleSheet(f"background-color: {elem.style.font_color}; color: #FFFFFF;")

        # Appearance
        self.btn_bg_color.setStyleSheet(
            f"background-color: {elem.style.background_color};" if elem.style.background_color != 'transparent' else ""
        )
        self.btn_border_color.setStyleSheet(
            f"background-color: {elem.style.border_color};" if elem.style.border_color != 'transparent' else ""
        )
        self.spin_border_width.setValue(elem.style.border_width)
        self.spin_border_radius.setValue(elem.style.border_radius)

        # Image
        self.cmb_mask.setCurrentText(elem.style.mask_shape)
        self.cmb_fit.setCurrentText(str(elem.style.fit_mode.value))

        # Show/hide groups based on type
        is_text = elem.type in ("static_text", "dynamic_text", "pin_field")
        is_photo = elem.type in ("photo", "image")
        self.type_group.setVisible(is_text)
        self.img_group.setVisible(is_photo)

        self._updating = False

    def _refresh_binding_combo(self) -> None:
        self.cmb_binding.blockSignals(True)
        self.cmb_binding.clear()
        self.cmb_binding.addItem("(None)", "")
        self.cmb_binding.addItem("Profile Photo [photo]", "photo")
        self.cmb_binding.addItem("PIN Number [pin]", "PIN Number")
        for col in self._available_columns:
            self.cmb_binding.addItem(col, col)
        self.cmb_binding.blockSignals(False)

    def _on_name_changed(self, text: str):
        if not self._updating and self._current_item:
            self._current_item.element.name = text

    def _on_pos_changed(self):
        if not self._updating and self._current_item:
            self._current_item.setPos(self.spin_x.value(), self.spin_y.value())
            self._current_item.update_model_position()

    def _on_size_changed(self):
        if not self._updating and self._current_item:
            self._current_item.set_rect(QRectF(0, 0, self.spin_w.value(), self.spin_h.value()))

    def _on_lock_toggled(self, checked: bool):
        if not self._updating and self._current_item:
            self._current_item.element.locked = checked

    def _on_binding_changed(self):
        if not self._updating and self._current_item:
            val = self.cmb_binding.currentData()
            self._current_item.element.binding = val if val else None
            self._current_item.update()
            self.property_changed.emit(self._current_item)

    def _on_static_changed(self, text: str):
        if not self._updating and self._current_item:
            self._current_item.element.static_content = text
            self._current_item.update()
            self.property_changed.emit(self._current_item)

    def _on_font_changed(self, font):
        if not self._updating and self._current_item:
            self._current_item.element.style.font_family = font.family()
            self._current_item.update()
            self.property_changed.emit(self._current_item)

    def _on_font_size_changed(self, val: int):
        if not self._updating and self._current_item:
            self._current_item.element.style.font_size = val
            self._current_item.update()
            self.property_changed.emit(self._current_item)

    def _on_bold_toggled(self, checked: bool):
        if not self._updating and self._current_item:
            self._current_item.element.style.font_bold = checked
            self._current_item.update()
            self.property_changed.emit(self._current_item)

    def _on_italic_toggled(self, checked: bool):
        if not self._updating and self._current_item:
            self._current_item.element.style.font_italic = checked
            self._current_item.update()
            self.property_changed.emit(self._current_item)

    def _on_align_changed(self, text: str):
        if not self._updating and self._current_item:
            self._current_item.element.style.text_align = text
            self._current_item.update()
            self.property_changed.emit(self._current_item)

    def _pick_font_color(self):
        if self._current_item:
            c = QColorDialog.getColor(QColor(self._current_item.element.style.font_color), self)
            if c.isValid():
                hex_c = c.name().upper()
                self._current_item.element.style.font_color = hex_c
                self.btn_font_color.setStyleSheet(f"background-color: {hex_c}; color: #FFFFFF;")
                self._current_item.update()
                self.property_changed.emit(self._current_item)

    def _pick_bg_color(self):
        if self._current_item:
            c = QColorDialog.getColor(QColor("#FFFFFF"), self)
            if c.isValid():
                hex_c = c.name().upper()
                self._current_item.element.style.background_color = hex_c
                self.btn_bg_color.setStyleSheet(f"background-color: {hex_c};")
                self._current_item.update()
                self.property_changed.emit(self._current_item)

    def _pick_border_color(self):
        if self._current_item:
            c = QColorDialog.getColor(QColor("#000000"), self)
            if c.isValid():
                hex_c = c.name().upper()
                self._current_item.element.style.border_color = hex_c
                self.btn_border_color.setStyleSheet(f"background-color: {hex_c};")
                self._current_item.update()
                self.property_changed.emit(self._current_item)

    def _on_border_width_changed(self, val: int):
        if not self._updating and self._current_item:
            self._current_item.element.style.border_width = val
            self._current_item.update()
            self.property_changed.emit(self._current_item)

    def _on_border_radius_changed(self, val: int):
        if not self._updating and self._current_item:
            self._current_item.element.style.border_radius = val
            self._current_item.update()
            self.property_changed.emit(self._current_item)

    def _on_mask_changed(self, text: str):
        if not self._updating and self._current_item:
            self._current_item.element.style.mask_shape = text
            self._current_item.update()
            self.property_changed.emit(self._current_item)

    def _on_fit_changed(self, text: str):
        if not self._updating and self._current_item:
            self._current_item.element.style.fit_mode = ImageFitMode(text)
            self._current_item.update()
            self.property_changed.emit(self._current_item)
