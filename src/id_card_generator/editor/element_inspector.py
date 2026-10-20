"""Properties inspector panel for editing selected canvas element attributes."""

import logging
from typing import List, Optional
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
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

    @staticmethod
    def _create_color_swatch_icon(color_hex: Optional[str], size: int = 16) -> QIcon:
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not color_hex or color_hex.lower() in ("transparent", "none"):
            p.setPen(QPen(QColor("#52525B"), 1))
            p.setBrush(QColor("#18181B"))
            p.drawRoundedRect(1, 1, size - 2, size - 2, 2.5, 2.5)
            p.setPen(QPen(QColor("#EF4444"), 1.5))
            p.drawLine(3, size - 4, size - 4, 3)
        else:
            c = QColor(color_hex)
            p.setBrush(c)
            p.setPen(QPen(QColor("#52525B"), 1))
            p.drawRoundedRect(1, 1, size - 2, size - 2, 2.5, 2.5)
        p.end()
        return QIcon(pix)

    def _set_color_button_state(self, btn: QPushButton, color_hex: Optional[str], default_label: str = "None") -> None:
        btn.setIcon(self._create_color_swatch_icon(color_hex))
        btn.setIconSize(QSize(16, 16))
        if color_hex and color_hex.lower() not in ("transparent", "none"):
            btn.setText(f" {color_hex.upper()}")
        else:
            btn.setText(f" {default_label}")
        btn.setStyleSheet("""
            QPushButton {
                background-color: #202023;
                color: #F4F4F5;
                border: 1px solid #3F3F46;
                border-radius: 4px;
                padding: 2px 8px;
                text-align: left;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #2A2A2E;
                border-color: #52525B;
            }
            QPushButton:pressed {
                background-color: #18181B;
                border-color: #0078D4;
            }
        """)

    def _setup_ui(self) -> None:
        self.setStyleSheet("""
            QWidget {
                font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }
            QGroupBox {
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.5px;
                text-transform: uppercase;
                color: #b6c4ff;
                border: 1px solid #383d47;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 12px;
                background-color: #1a1c20;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                background: #1a1c20;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QFontComboBox {
                background-color: #0c0e12;
                border: 1px solid #383d47;
                border-radius: 4px;
                color: #e2e2e8;
                font-family: 'JetBrains Mono', monospace;
                font-size: 11px;
                padding: 3px 6px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QFontComboBox:focus {
                border: 1px solid #6c8cff;
            }
            QPushButton {
                background-color: #282a2e;
                border: 1px solid #383d47;
                border-radius: 4px;
                color: #e2e2e8;
                font-size: 11px;
                font-weight: 500;
                padding: 3px 8px;
            }
            QPushButton:hover {
                background-color: #333539;
                border-color: #6c8cff;
            }
            QLabel {
                color: #c4c5d5;
                font-size: 11px;
            }
        """)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # Header
        self.lbl_title = QLabel("<b>ELEMENT PROPERTIES</b>")
        self.lbl_title.setStyleSheet("color: #ffffff; font-size: 11px; letter-spacing: 0.5px;")
        main_layout.addWidget(self.lbl_title)

        # Scroll Area for properties
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self.form_layout = QVBoxLayout(container)
        self.form_layout.setContentsMargins(2, 2, 2, 2)
        self.form_layout.setSpacing(8)

        # 1. Identity & Geometry Group
        geom_group = QGroupBox("Transform && Position")
        geom_layout = QFormLayout(geom_group)
        geom_layout.setContentsMargins(8, 12, 8, 8)
        geom_layout.setHorizontalSpacing(8)
        geom_layout.setVerticalSpacing(6)

        self.txt_name = QLineEdit()
        self.txt_name.textChanged.connect(self._on_name_changed)
        geom_layout.addRow("Name:", self.txt_name)

        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-5000, 5000)
        self.spin_x.setSuffix(" px")
        self.spin_x.valueChanged.connect(self._on_pos_changed)
        geom_layout.addRow("X:", self.spin_x)

        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-5000, 5000)
        self.spin_y.setSuffix(" px")
        self.spin_y.valueChanged.connect(self._on_pos_changed)
        geom_layout.addRow("Y:", self.spin_y)

        self.spin_w = QDoubleSpinBox()
        self.spin_w.setRange(5, 5000)
        self.spin_w.setSuffix(" px")
        self.spin_w.valueChanged.connect(self._on_size_changed)
        geom_layout.addRow("Width:", self.spin_w)

        self.spin_h = QDoubleSpinBox()
        self.spin_h.setRange(5, 5000)
        self.spin_h.setSuffix(" px")
        self.spin_h.valueChanged.connect(self._on_size_changed)
        geom_layout.addRow("Height:", self.spin_h)

        self.chk_locked = QCheckBox("Lock element on canvas")
        self.chk_locked.toggled.connect(self._on_lock_toggled)
        geom_layout.addRow("", self.chk_locked)

        self.form_layout.addWidget(geom_group)

        # Layer Arrangement Group (Bring to top, send to bottom, step forward/backward)
        arrange_group = QGroupBox("Layer Order && Stacking")
        arrange_layout = QHBoxLayout(arrange_group)
        arrange_layout.setContentsMargins(6, 12, 6, 8)
        arrange_layout.setSpacing(4)

        self.btn_prop_to_front = QPushButton("Top ⏫")
        self.btn_prop_to_front.setFixedHeight(26)
        self.btn_prop_to_front.setToolTip("Bring element on top of every other element")
        self.btn_prop_to_front.clicked.connect(self._bring_to_front)
        arrange_layout.addWidget(self.btn_prop_to_front)

        self.btn_prop_forward = QPushButton("Up ▲")
        self.btn_prop_forward.setFixedHeight(26)
        self.btn_prop_forward.setToolTip("Bring element one step forward")
        self.btn_prop_forward.clicked.connect(self._bring_forward)
        arrange_layout.addWidget(self.btn_prop_forward)

        self.btn_prop_backward = QPushButton("Down ▼")
        self.btn_prop_backward.setFixedHeight(26)
        self.btn_prop_backward.setToolTip("Send element one step backward")
        self.btn_prop_backward.clicked.connect(self._send_backward)
        arrange_layout.addWidget(self.btn_prop_backward)

        self.btn_prop_to_back = QPushButton("Bottom ⏬")
        self.btn_prop_to_back.setFixedHeight(26)
        self.btn_prop_to_back.setToolTip("Send element back to bottom of all elements")
        self.btn_prop_to_back.clicked.connect(self._send_to_back)
        arrange_layout.addWidget(self.btn_prop_to_back)

        self.form_layout.addWidget(arrange_group)

        # 2. Data Binding Group
        binding_group = QGroupBox("Data Binding")
        binding_layout = QFormLayout(binding_group)
        binding_layout.setContentsMargins(8, 12, 8, 8)
        binding_layout.setHorizontalSpacing(8)
        binding_layout.setVerticalSpacing(6)

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
        type_layout.setContentsMargins(8, 12, 8, 8)
        type_layout.setHorizontalSpacing(8)
        type_layout.setVerticalSpacing(6)

        from id_card_generator.rendering.font_manager import FontManager
        FontManager.register_system_fonts_with_qt()

        self.cmb_font = QFontComboBox()
        self.cmb_font.setFontFilters(QFontComboBox.FontFilter.AllFonts)
        self.cmb_font.setWritingSystem(QFontDatabase.WritingSystem.Any)
        self.cmb_font.currentFontChanged.connect(self._on_font_changed)
        type_layout.addRow("Font:", self.cmb_font)

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(4, 144)
        self.spin_font_size.setSuffix(" pt")
        self.spin_font_size.setValue(10)
        self.spin_font_size.valueChanged.connect(self._on_font_size_changed)
        type_layout.addRow("Size:", self.spin_font_size)

        style_row = QHBoxLayout()
        style_row.setSpacing(6)
        self.chk_bold = QCheckBox("Bold")
        self.chk_bold.toggled.connect(self._on_bold_toggled)
        self.chk_italic = QCheckBox("Italic")
        self.chk_italic.toggled.connect(self._on_italic_toggled)
        style_row.addWidget(self.chk_bold)
        style_row.addWidget(self.chk_italic)
        style_row.addStretch()
        type_layout.addRow("Style:", style_row)

        self.btn_font_color = QPushButton()
        self.btn_font_color.setFixedHeight(28)
        self._set_color_button_state(self.btn_font_color, "#1A1A1A")
        self.btn_font_color.clicked.connect(self._pick_font_color)
        type_layout.addRow("Text Color:", self.btn_font_color)

        # Segmented alignment buttons in a rectangle
        self.align_frame = QFrame()
        self.align_frame.setObjectName("insp_align_rect")
        self.align_frame.setFixedHeight(28)
        align_layout = QHBoxLayout(self.align_frame)
        align_layout.setContentsMargins(0, 0, 0, 0)
        align_layout.setSpacing(0)

        self.btn_align_left = QToolButton()
        self.btn_align_left.setObjectName("btn_align_left")
        self.btn_align_left.setText("Left")
        self.btn_align_left.setToolTip("Align Left")
        self.btn_align_left.setCheckable(True)
        self.btn_align_left.setFixedHeight(26)

        self.btn_align_center = QToolButton()
        self.btn_align_center.setObjectName("btn_align_center")
        self.btn_align_center.setText("Center")
        self.btn_align_center.setToolTip("Align Center")
        self.btn_align_center.setCheckable(True)
        self.btn_align_center.setFixedHeight(26)

        self.btn_align_right = QToolButton()
        self.btn_align_right.setObjectName("btn_align_right")
        self.btn_align_right.setText("Right")
        self.btn_align_right.setToolTip("Align Right")
        self.btn_align_right.setCheckable(True)
        self.btn_align_right.setFixedHeight(26)

        self.align_group = QButtonGroup(self.type_group)
        self.align_group.setExclusive(True)
        self.align_group.addButton(self.btn_align_left)
        self.align_group.addButton(self.btn_align_center)
        self.align_group.addButton(self.btn_align_right)

        self.btn_align_left.clicked.connect(lambda: self._on_align_btn_clicked("left"))
        self.btn_align_center.clicked.connect(lambda: self._on_align_btn_clicked("center"))
        self.btn_align_right.clicked.connect(lambda: self._on_align_btn_clicked("right"))

        align_layout.addWidget(self.btn_align_left)
        align_layout.addWidget(self.btn_align_center)
        align_layout.addWidget(self.btn_align_right)

        self.align_frame.setStyleSheet("""
            QFrame#insp_align_rect {
                background-color: #202023;
                border: 1px solid #3F3F46;
                border-radius: 4px;
            }
            QFrame#insp_align_rect QToolButton {
                background-color: transparent;
                color: #A1A1AA;
                border: none;
                font-size: 11px;
                font-weight: 500;
                padding: 2px 8px;
            }
            QFrame#insp_align_rect QToolButton:hover {
                background-color: #2E2E33;
                color: #FFFFFF;
            }
            QFrame#insp_align_rect QToolButton:checked {
                background-color: #0078D4;
                color: #FFFFFF;
                font-weight: 600;
            }
            QFrame#insp_align_rect QToolButton#btn_align_left {
                border-top-left-radius: 3px;
                border-bottom-left-radius: 3px;
                border-right: 1px solid #3F3F46;
            }
            QFrame#insp_align_rect QToolButton#btn_align_center {
                border-radius: 0px;
                border-right: 1px solid #3F3F46;
            }
            QFrame#insp_align_rect QToolButton#btn_align_right {
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
            }
        """)
        type_layout.addRow("Align:", self.align_frame)

        self.cmb_align = QComboBox()
        self.cmb_align.addItems(["left", "center", "right"])
        self.cmb_align.setVisible(False)
        self.cmb_align.currentTextChanged.connect(self._sync_align_from_combo)
        type_layout.addRow(self.cmb_align)

        self.btn_align_left.setChecked(True)

        self.form_layout.addWidget(self.type_group)

        # 4. Appearance & Borders Group
        self.app_group = QGroupBox("Appearance && Borders")
        app_layout = QFormLayout(self.app_group)
        app_layout.setContentsMargins(8, 12, 8, 8)
        app_layout.setHorizontalSpacing(8)
        app_layout.setVerticalSpacing(6)

        self.btn_bg_color = QPushButton()
        self.btn_bg_color.setFixedHeight(28)
        self._set_color_button_state(self.btn_bg_color, "transparent", "None (Transparent)")
        self.btn_bg_color.clicked.connect(self._pick_bg_color)
        app_layout.addRow("Background:", self.btn_bg_color)

        self.btn_border_color = QPushButton()
        self.btn_border_color.setFixedHeight(28)
        self._set_color_button_state(self.btn_border_color, "transparent", "None (Transparent)")
        self.btn_border_color.clicked.connect(self._pick_border_color)
        app_layout.addRow("Border Color:", self.btn_border_color)

        self.spin_border_width = QSpinBox()
        self.spin_border_width.setRange(0, 50)
        self.spin_border_width.setSuffix(" px")
        self.spin_border_width.valueChanged.connect(self._on_border_width_changed)
        app_layout.addRow("Border Width:", self.spin_border_width)

        self.spin_border_radius = QSpinBox()
        self.spin_border_radius.setRange(0, 500)
        self.spin_border_radius.setSuffix(" px")
        self.spin_border_radius.valueChanged.connect(self._on_border_radius_changed)
        app_layout.addRow("Corner Radius:", self.spin_border_radius)

        self.form_layout.addWidget(self.app_group)

        # 5. Image & Masking Group
        self.img_group = QGroupBox("Photo / Image Options")
        img_layout = QFormLayout(self.img_group)
        img_layout.setContentsMargins(8, 12, 8, 8)
        img_layout.setHorizontalSpacing(8)
        img_layout.setVerticalSpacing(6)

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
            self._invalidate_current_item()
            self.lbl_title.setText("<i>No element selected</i>")
            self.setEnabled(False)
            return

        self.setEnabled(True)
        self._updating = True
        elem = item.element
        self.lbl_title.setText(f"<b>{elem.name}</b> ({elem.type})")

        # Position & Size
        if not self.txt_name.hasFocus() and self.txt_name.text() != elem.name:
            self.txt_name.setText(elem.name)
        if not self.spin_x.hasFocus():
            self.spin_x.setValue(item.pos().x())
        if not self.spin_y.hasFocus():
            self.spin_y.setValue(item.pos().y())
        if not self.spin_w.hasFocus():
            self.spin_w.setValue(elem.width)
        if not self.spin_h.hasFocus():
            self.spin_h.setValue(elem.height)
        self.chk_locked.setChecked(elem.locked)

        # Binding
        self._refresh_binding_combo()
        if elem.binding:
            idx = self.cmb_binding.findText(elem.binding)
            if idx >= 0 and self.cmb_binding.currentIndex() != idx:
                self.cmb_binding.setCurrentIndex(idx)
        else:
            if self.cmb_binding.currentIndex() != 0:
                self.cmb_binding.setCurrentIndex(0)

        if not self.txt_static.hasFocus() and self.txt_static.text() != (elem.static_content or ""):
            self.txt_static.setText(elem.static_content or "")

        # Typography
        if not self.cmb_font.hasFocus() and self.cmb_font.currentFont().family() != elem.style.font_family:
            self.cmb_font.setCurrentFont(QFont(elem.style.font_family))
        sz_val = int(round(elem.style.font_size))
        if not self.spin_font_size.hasFocus() and self.spin_font_size.value() != sz_val:
            self.spin_font_size.setValue(sz_val)
        self.chk_bold.setChecked(elem.style.font_bold)
        self.chk_italic.setChecked(elem.style.font_italic)
        self._set_align_ui(elem.style.text_align)
        self._set_color_button_state(self.btn_font_color, elem.style.font_color, "#1A1A1A")

        # Appearance
        self._set_color_button_state(self.btn_bg_color, elem.style.background_color, "None (Transparent)")
        self._set_color_button_state(self.btn_border_color, elem.style.border_color, "None (Transparent)")
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

    def _invalidate_current_item(self) -> None:
        """Drop a reference to an item whose C++ object may be gone.

        The canvas item is destroyed whenever the scene is reloaded; keeping
        the wrapper alive would let a stale object be used later on.
        """
        self._current_item = None
        try:
            self.setEnabled(False)
        except RuntimeError:
            pass

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
                self._current_item.element.style.font_size = float(val)
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

    def _on_align_btn_clicked(self, text: str):
        self._set_align_ui(text)
        self._on_align_changed(text)

    def _sync_align_from_combo(self, text: str):
        self._set_align_ui(text)
        self._on_align_changed(text)

    def _set_align_ui(self, align: str):
        align = (align or "left").lower().strip()
        if align == "center":
            self.btn_align_center.setChecked(True)
        elif align == "right":
            self.btn_align_right.setChecked(True)
        else:
            self.btn_align_left.setChecked(True)
        self.cmb_align.blockSignals(True)
        self.cmb_align.setCurrentText(align)
        self.cmb_align.blockSignals(False)

    def _on_align_changed(self, text: str):
        if not self._updating and self._current_item:
            def _update():
                self._current_item.element.style.text_align = text
            self._apply_change(_update, "Change Alignment")

    def _pick_font_color(self):
        if self._current_item:
            initial = self._current_item.element.style.font_color or "#1A1A1A"
            c = QColorDialog.getColor(QColor(initial), self, "Select Text Color")
            if c.isValid():
                hex_c = c.name().upper()
                def _update():
                    self._current_item.element.style.font_color = hex_c
                    self._set_color_button_state(self.btn_font_color, hex_c)
                self._apply_change(_update, "Change Font Color")

    def _pick_bg_color(self):
        if self._current_item:
            initial = self._current_item.element.style.background_color
            if not initial or initial.lower() == "transparent":
                initial = "#FFFFFF"
            c = QColorDialog.getColor(QColor(initial), self, "Select Background Fill Color")
            if c.isValid():
                hex_c = c.name().upper()
                def _update():
                    self._current_item.element.style.background_color = hex_c
                    self._set_color_button_state(self.btn_bg_color, hex_c, "None (Transparent)")
                self._apply_change(_update, "Change Fill Color")

    def _pick_border_color(self):
        if self._current_item:
            initial = self._current_item.element.style.border_color
            if not initial or initial.lower() == "transparent":
                initial = "#000000"
            c = QColorDialog.getColor(QColor(initial), self, "Select Border Color")
            if c.isValid():
                hex_c = c.name().upper()
                def _update():
                    self._current_item.element.style.border_color = hex_c
                    self._set_color_button_state(self.btn_border_color, hex_c, "None (Transparent)")
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
