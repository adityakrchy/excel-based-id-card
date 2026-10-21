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
    QFrame,
    QGridLayout,
    QGroupBox,
    QLayout,
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
from id_card_generator.ui.studio_tokens import active_palette

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
            palette = active_palette()
            p.setPen(QPen(QColor(palette.OUTLINE_VARIANT), 1))
            p.setBrush(QColor(palette.SURFACE_LOWEST))
            p.drawRoundedRect(1, 1, size - 2, size - 2, 2.5, 2.5)
            p.setPen(QPen(QColor(palette.ERROR), 1.5))
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
        # The look of the well comes from the application stylesheet, only
        # the swatch shows the colour of the element itself.
        btn.setObjectName("swatch_button")

    def _setup_ui(self) -> None:
        # Only the type of the inputs is set here - the colours, the spacing
        # and the borders come from the token driven application stylesheet,
        # so the panel follows the theme of the application.
        self.setStyleSheet("""
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QFontComboBox {
                font-family: 'JetBrains Mono', monospace;
                font-size: 11px;
            }
        """)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Header
        self.lbl_section = QLabel("PROPERTIES")
        self.lbl_section.setProperty("role", "sectionLabel")
        main_layout.addWidget(self.lbl_section)

        self.lbl_title = QLabel("<i>No element selected</i>")
        self.lbl_title.setProperty("role", "cardTitle")
        self.lbl_title.setWordWrap(True)
        main_layout.addWidget(self.lbl_title)

        # Scroll Area for properties
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        container = QWidget()
        container.setProperty("role", "flat")
        self.form_layout = QVBoxLayout(container)
        self.form_layout.setContentsMargins(0, 0, 4, 0)
        self.form_layout.setSpacing(10)

        # 1. Identity & Geometry Group
        geom_group = QGroupBox("Transform && Position")
        geom_layout = self._make_form(geom_group)

        self.txt_name = QLineEdit()
        self.txt_name.textChanged.connect(self._on_name_changed)
        self._add_row(geom_layout, "Name:", self.txt_name)

        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-5000, 5000)
        self.spin_x.setSuffix(" px")
        self.spin_x.valueChanged.connect(self._on_pos_changed)
        self._add_row(geom_layout, "X:", self.spin_x)

        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-5000, 5000)
        self.spin_y.setSuffix(" px")
        self.spin_y.valueChanged.connect(self._on_pos_changed)
        self._add_row(geom_layout, "Y:", self.spin_y)

        self.spin_w = QDoubleSpinBox()
        self.spin_w.setRange(5, 5000)
        self.spin_w.setSuffix(" px")
        self.spin_w.valueChanged.connect(self._on_size_changed)
        self._add_row(geom_layout, "Width:", self.spin_w)

        self.spin_h = QDoubleSpinBox()
        self.spin_h.setRange(5, 5000)
        self.spin_h.setSuffix(" px")
        self.spin_h.valueChanged.connect(self._on_size_changed)
        self._add_row(geom_layout, "Height:", self.spin_h)

        self.chk_locked = QCheckBox("Lock element on canvas")
        self.chk_locked.toggled.connect(self._on_lock_toggled)
        self._add_full_row(geom_layout, self.chk_locked)

        self.cmb_side = QComboBox()
        self.cmb_side.addItem("Front", "front")
        self.cmb_side.addItem("Back", "back")
        self.cmb_side.currentIndexChanged.connect(self._on_side_changed)
        self._add_row(geom_layout, "Card side:", self.cmb_side)

        self.form_layout.addWidget(geom_group)

        # Layer Arrangement Group (Bring to top, send to bottom, step forward/backward)
        arrange_group = QGroupBox("Layer Order && Stacking")
        arrange_layout = QHBoxLayout(arrange_group)
        arrange_layout.setContentsMargins(12, 10, 12, 12)
        arrange_layout.setSpacing(6)

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
        binding_layout = self._make_form(binding_group)

        self.cmb_binding = QComboBox()
        self.cmb_binding.currentIndexChanged.connect(self._on_binding_changed)
        self._add_row(binding_layout, "Bind Column:", self.cmb_binding)

        self.txt_static = QLineEdit()
        self.txt_static.textChanged.connect(self._on_static_changed)
        self._add_row(binding_layout, "Static Text:", self.txt_static)

        self.form_layout.addWidget(binding_group)

        # 3. Typography Group
        self.type_group = QGroupBox("Typography")
        type_layout = self._make_form(self.type_group)

        from id_card_generator.rendering.font_manager import FontManager
        FontManager.register_system_fonts_with_qt()

        self.cmb_font = QFontComboBox()
        self.cmb_font.setFontFilters(QFontComboBox.FontFilter.AllFonts)
        self.cmb_font.setWritingSystem(QFontDatabase.WritingSystem.Any)
        # The longest font name would make the panel wider than the dock.
        self.cmb_font.setMinimumContentsLength(10)
        self.cmb_font.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_font.currentFontChanged.connect(self._on_font_changed)
        self._add_row(type_layout, "Font:", self.cmb_font)

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(4, 144)
        self.spin_font_size.setSuffix(" pt")
        self.spin_font_size.setValue(10)
        self.spin_font_size.valueChanged.connect(self._on_font_size_changed)
        self._add_row(type_layout, "Size:", self.spin_font_size)

        style_row = QHBoxLayout()
        style_row.setSpacing(6)
        self.chk_bold = QCheckBox("Bold")
        self.chk_bold.toggled.connect(self._on_bold_toggled)
        self.chk_italic = QCheckBox("Italic")
        self.chk_italic.toggled.connect(self._on_italic_toggled)
        style_row.addWidget(self.chk_bold)
        style_row.addWidget(self.chk_italic)
        style_row.addStretch()
        self._add_row(type_layout, "Style:", style_row)

        self.btn_font_color = QPushButton()
        self.btn_font_color.setFixedHeight(28)
        self._set_color_button_state(self.btn_font_color, "#1A1A1A")
        self.btn_font_color.clicked.connect(self._pick_font_color)
        self._add_row(type_layout, "Text Color:", self.btn_font_color, stretch=False)

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
        self.btn_align_left.setMinimumWidth(54)

        self.btn_align_center = QToolButton()
        self.btn_align_center.setObjectName("btn_align_center")
        self.btn_align_center.setText("Center")
        self.btn_align_center.setToolTip("Align Center")
        self.btn_align_center.setCheckable(True)
        self.btn_align_center.setMinimumWidth(64)

        self.btn_align_right = QToolButton()
        self.btn_align_right.setObjectName("btn_align_right")
        self.btn_align_right.setText("Right")
        self.btn_align_right.setToolTip("Align Right")
        self.btn_align_right.setCheckable(True)
        self.btn_align_right.setMinimumWidth(54)

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

        self._add_row(type_layout, "Align:", self.align_frame)

        self.cmb_align = QComboBox()
        self.cmb_align.addItems(["left", "center", "right"])
        self.cmb_align.setVisible(False)
        self.cmb_align.currentTextChanged.connect(self._sync_align_from_combo)
        type_layout.addWidget(self.cmb_align)

        self.btn_align_left.setChecked(True)

        self.form_layout.addWidget(self.type_group)

        # 4. Appearance & Borders Group
        self.app_group = QGroupBox("Appearance && Borders")
        app_layout = self._make_form(self.app_group)

        self.btn_bg_color = QPushButton()
        self.btn_bg_color.setFixedHeight(28)
        self._set_color_button_state(self.btn_bg_color, "transparent", "None (Transparent)")
        self.btn_bg_color.clicked.connect(self._pick_bg_color)
        self._add_row(app_layout, "Background:", self.btn_bg_color, stretch=False)

        self.btn_border_color = QPushButton()
        self.btn_border_color.setFixedHeight(28)
        self._set_color_button_state(self.btn_border_color, "transparent", "None (Transparent)")
        self.btn_border_color.clicked.connect(self._pick_border_color)
        self._add_row(app_layout, "Border Color:", self.btn_border_color, stretch=False)

        self.spin_border_width = QSpinBox()
        self.spin_border_width.setRange(0, 50)
        self.spin_border_width.setSuffix(" px")
        self.spin_border_width.valueChanged.connect(self._on_border_width_changed)
        self._add_row(app_layout, "Border Width:", self.spin_border_width)

        self.spin_border_radius = QSpinBox()
        self.spin_border_radius.setRange(0, 500)
        self.spin_border_radius.setSuffix(" px")
        self.spin_border_radius.valueChanged.connect(self._on_border_radius_changed)
        self._add_row(app_layout, "Corner Radius:", self.spin_border_radius)

        self.form_layout.addWidget(self.app_group)

        # 5. Image & Masking Group
        self.img_group = QGroupBox("Photo / Image Options")
        img_layout = self._make_form(self.img_group)

        self.cmb_mask = QComboBox()
        self.cmb_mask.addItems(["rect", "circle", "rounded"])
        self.cmb_mask.currentTextChanged.connect(self._on_mask_changed)
        self._add_row(img_layout, "Mask Shape:", self.cmb_mask)

        self.cmb_fit = QComboBox()
        self.cmb_fit.addItems(["cover", "contain", "stretch", "crop"])
        self.cmb_fit.currentTextChanged.connect(self._on_fit_changed)
        self._add_row(img_layout, "Fit Mode:", self.cmb_fit)

        self.form_layout.addWidget(self.img_group)

        self.form_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        self.setEnabled(False)

    # -- the form of a group --------------------------------------------
    LABEL_WIDTH = 92

    def _make_form(self, group: QGroupBox) -> QGridLayout:
        """Build the two column form of a group.

        The caption column has a fixed width, so every group of the panel
        starts its fields at the same place and the rows read as one column.
        """
        layout = QGridLayout(group)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)
        layout.setColumnMinimumWidth(0, self.LABEL_WIDTH)
        layout.setColumnStretch(1, 1)
        return layout

    def _add_row(
        self,
        layout: QGridLayout,
        label: str,
        widget: QWidget,
        stretch: bool = True,
    ) -> None:
        """Add a caption and its field to a group."""
        row = layout.rowCount()

        caption = QLabel(label)
        caption.setProperty("role", "specKey")
        caption.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        caption.setFixedWidth(self.LABEL_WIDTH)
        layout.addWidget(caption, row, 0)

        if isinstance(widget, QLayout):
            # A row of controls is hosted by a plain widget.
            holder = QWidget()
            holder.setProperty("role", "flat")
            holder.setLayout(widget)
            widget = holder

        if stretch:
            layout.addWidget(widget, row, 1)
        else:
            # A colour well keeps its own size instead of filling the row.
            layout.addWidget(widget, row, 1, 1, 1, Qt.AlignLeft | Qt.AlignVCenter)

    def _add_full_row(self, layout: QGridLayout, widget: QWidget) -> None:
        """Add a widget that spans the whole width of a group."""
        row = layout.rowCount()
        layout.addWidget(widget, row, 0, 1, 2, Qt.AlignLeft | Qt.AlignVCenter)

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

        # Card face
        side = getattr(elem, "side", "front") or "front"
        idx = self.cmb_side.findData(side)
        if idx >= 0 and self.cmb_side.currentIndex() != idx:
            self.cmb_side.setCurrentIndex(idx)

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

    def _on_side_changed(self):
        if not self._updating and self._current_item:
            val = self.cmb_side.currentData() or "front"
            def _update():
                self._current_item.element.side = val
            self._apply_change(_update, "Change Card Side")

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
