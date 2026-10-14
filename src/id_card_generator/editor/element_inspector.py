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

        # Layer Arrangement Group (Bring to top, send to bottom, step forward/backward)
        arrange_group = QGroupBox("Layer Order & Stacking")
        arrange_layout = QHBoxLayout(arrange_group)
        arrange_layout.setContentsMargins(4, 6, 4, 6)
        arrange_layout.setSpacing(4)

        self.btn_prop_to_front = QPushButton("To Front ⏫")
        self.btn_prop_to_front.setToolTip("Bring element on top of every other element")
        self.btn_prop_to_front.clicked.connect(self._bring_to_front)
        arrange_layout.addWidget(self.btn_prop_to_front)

        self.btn_prop_forward = QPushButton("Forward ▲")
        self.btn_prop_forward.setToolTip("Bring element one step forward")
        self.btn_prop_forward.clicked.connect(self._bring_forward)
        arrange_layout.addWidget(self.btn_prop_forward)

        self.btn_prop_backward = QPushButton("Backward ▼")
        self.btn_prop_backward.setToolTip("Send element one step backward")
        self.btn_prop_backward.clicked.connect(self._send_backward)
        arrange_layout.addWidget(self.btn_prop_backward)

        self.btn_prop_to_back = QPushButton("To Back ⏬")
        self.btn_prop_to_back.setToolTip("Send element back to bottom of all elements")
        self.btn_prop_to_back.clicked.connect(self._send_to_back)
        arrange_layout.addWidget(self.btn_prop_to_back)

        self.form_layout.addWidget(arrange_group)

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

    def _apply_change(self, update_fn, description: str = "Change Property") -> None:
        if self._updating or not self._current_item:
            return
        item = self._current_item
        old_state = item.element.model_dump(mode="json")
        update_fn()
        new_state = item.element.model_dump(mode="json")
        if old_state != new_state:
            scene = item.scene()
            if scene and hasattr(scene, "undo_stack"):
                from id_card_generator.editor.undo_manager import ChangeElementStateCommand
                scene.undo_stack.push(ChangeElementStateCommand(scene, item.element.id, old_state, new_state, description))
            item.update()
            if scene:
                scene.update()
                scene.template_modified.emit()
            self.property_changed.emit(item)

    def _bring_to_front(self) -> None:
        """Bring selected element on top of every other canvas element."""
        if self._current_item and self._current_item.scene():
            scene = self._current_item.scene()
            if hasattr(scene, "bring_to_front"):
                scene.bring_to_front(self._current_item)
                self.property_changed.emit(self._current_item)

    def _bring_forward(self) -> None:
        """Bring selected element one step forward (on top of adjacent element)."""
        if self._current_item and self._current_item.scene():
            scene = self._current_item.scene()
            if hasattr(scene, "bring_forward"):
                scene.bring_forward(self._current_item)
                self.property_changed.emit(self._current_item)

    def _send_backward(self) -> None:
        """Send selected element one step backward (behind adjacent element)."""
        if self._current_item and self._current_item.scene():
            scene = self._current_item.scene()
            if hasattr(scene, "send_backward"):
                scene.send_backward(self._current_item)
                self.property_changed.emit(self._current_item)

    def _send_to_back(self) -> None:
        """Send selected element back to bottom of all canvas elements."""
        if self._current_item and self._current_item.scene():
            scene = self._current_item.scene()
            if hasattr(scene, "send_to_back"):
                scene.send_to_back(self._current_item)
                self.property_changed.emit(self._current_item)

    def _on_name_changed(self, text: str):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.element.name = text
            self._apply_change(_update, "Rename Element")

    def _on_pos_changed(self):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.setPos(self.spin_x.value(), self.spin_y.value())
                self._current_item.update_model_position()
            self._apply_change(_update, "Move Element")

    def _on_size_changed(self):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.set_rect(QRectF(0, 0, self.spin_w.value(), self.spin_h.value()))
            self._apply_change(_update, "Resize Element")

    def _on_lock_toggled(self, checked: bool):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.element.locked = checked
            self._apply_change(_update, "Toggle Lock")

    def _on_binding_changed(self):
        if not self._updating and self._current_item:
            val = self.cmb_binding.currentData()
            def _update():
                self._current_item.element.binding = val if val else None
            self._apply_change(_update, "Change Binding")

    def _on_static_changed(self, text: str):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.element.static_content = text
            self._apply_change(_update, "Change Static Text")

    def _on_font_changed(self, font):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.element.style.font_family = font.family()
            self._apply_change(_update, "Change Font Family")

    def _on_font_size_changed(self, val: int):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.element.style.font_size = val
            self._apply_change(_update, "Change Font Size")

    def _on_bold_toggled(self, checked: bool):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.element.style.font_bold = checked
            self._apply_change(_update, "Toggle Bold")

    def _on_italic_toggled(self, checked: bool):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.element.style.font_italic = checked
            self._apply_change(_update, "Toggle Italic")

    def _on_align_changed(self, text: str):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.element.style.text_align = text
            self._apply_change(_update, "Change Alignment")

    def _pick_font_color(self):
        if self._current_item:
            c = QColorDialog.getColor(QColor(self._current_item.element.style.font_color), self)
            if c.isValid():
                hex_c = c.name().upper()
                def _update():
                    self._current_item.element.style.font_color = hex_c
                    self.btn_font_color.setStyleSheet(f"background-color: {hex_c}; color: #FFFFFF;")
                self._apply_change(_update, "Change Font Color")

    def _pick_bg_color(self):
        if self._current_item:
            c = QColorDialog.getColor(QColor("#FFFFFF"), self)
            if c.isValid():
                hex_c = c.name().upper()
                def _update():
                    self._current_item.element.style.background_color = hex_c
                    self.btn_bg_color.setStyleSheet(f"background-color: {hex_c};")
                self._apply_change(_update, "Change Fill Color")

    def _pick_border_color(self):
        if self._current_item:
            c = QColorDialog.getColor(QColor("#000000"), self)
            if c.isValid():
                hex_c = c.name().upper()
                def _update():
                    self._current_item.element.style.border_color = hex_c
                    self.btn_border_color.setStyleSheet(f"background-color: {hex_c};")
                self._apply_change(_update, "Change Border Color")

    def _on_border_width_changed(self, val: int):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.element.style.border_width = val
            self._apply_change(_update, "Change Border Width")

    def _on_border_radius_changed(self, val: int):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.element.style.border_radius = val
            self._apply_change(_update, "Change Border Radius")

    def _on_mask_changed(self, text: str):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.element.style.mask_shape = text
            self._apply_change(_update, "Change Mask Shape")

    def _on_fit_changed(self, text: str):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.element.style.fit_mode = ImageFitMode(text)
            self._apply_change(_update, "Change Fit Mode")
