"""Dialog for configuring and creating a completely blank custom ID card canvas."""

import logging
from pathlib import Path
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from id_card_generator.core.constants import DEFAULT_DPI
from id_card_generator.core.geometry import (
    calculate_card_dimensions,
    convert_unit,
)
from id_card_generator.core.models import TemplateDefinition

logger = logging.getLogger(__name__)


class BlankCanvasDialog(QDialog):
    """Dialog allowing users to create a clean blank canvas or edit existing template canvas properties."""

    def __init__(self, parent=None, existing_template: Optional[TemplateDefinition] = None):
        super().__init__(parent)
        self.existing_template = existing_template
        is_edit = existing_template is not None
        self.setWindowTitle(f"Edit Canvas Properties - {existing_template.name}" if is_edit else "Create Blank Canvas")
        self.setMinimumWidth(460)
        self.template_definition: Optional[TemplateDefinition] = None

        self._bg_color = (existing_template.background_color or "#FFFFFF") if existing_template else "#FFFFFF"
        self._bg_image_path: Optional[str] = existing_template.background_image_path if existing_template else None

        self._setup_ui()

        if existing_template:
            self._load_from_template(existing_template)
        else:
            self._on_preset_changed(0)  # Standard CR80 default

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # Header
        is_edit = self.existing_template is not None
        title_text = "<b>Edit Canvas Properties</b>" if is_edit else "<b>Create New Blank Canvas</b>"
        lbl_head = QLabel(title_text)
        lbl_head.setStyleSheet("font-size: 15px;")
        layout.addWidget(lbl_head)

        desc_text = (
            "Modify physical card dimensions, print DPI, orientation, and card surface properties."
            if is_edit else
            "Configure physical card dimensions, DPI, and background properties."
        )
        lbl_desc = QLabel(desc_text)
        lbl_desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(lbl_desc)

        form_group = QGroupBox("Document Specifications")
        form_layout = QFormLayout(form_group)

        # Name
        default_name = self.existing_template.name if self.existing_template else "Blank ID Card"
        self.txt_name = QLineEdit(default_name)
        form_layout.addRow("Template Name:", self.txt_name)

        # Presets
        self.combo_presets = QComboBox()
        self.combo_presets.addItem("CR80 Standard (85.60 × 53.98 mm) - Credit / ID Card")
        self.combo_presets.addItem("CR79 (83.90 × 52.10 mm) - Adhesive Backed")
        self.combo_presets.addItem("Visitor Badge (100.00 × 70.00 mm)")
        self.combo_presets.addItem("Custom Dimensions")
        self.combo_presets.currentIndexChanged.connect(self._on_preset_changed)
        form_layout.addRow("Standard Preset:", self.combo_presets)

        # Measurement unit
        self.combo_unit = QComboBox()
        self.combo_unit.addItems(["mm", "cm", "inch"])
        self.combo_unit.currentTextChanged.connect(self._on_unit_changed)
        form_layout.addRow("Measurement Unit:", self.combo_unit)

        # Dimensions
        dim_box = QHBoxLayout()
        self.spin_width = QDoubleSpinBox()
        self.spin_width.setRange(1.0, 2000.0)
        self.spin_width.setDecimals(2)
        self.spin_width.setValue(85.6)
        self.spin_width.valueChanged.connect(self._update_pixel_preview)
        dim_box.addWidget(QLabel("W:"))
        dim_box.addWidget(self.spin_width)

        self.spin_height = QDoubleSpinBox()
        self.spin_height.setRange(1.0, 2000.0)
        self.spin_height.setDecimals(2)
        self.spin_height.setValue(54.0)
        self.spin_height.valueChanged.connect(self._update_pixel_preview)
        dim_box.addWidget(QLabel("H:"))
        dim_box.addWidget(self.spin_height)
        form_layout.addRow("Dimensions:", dim_box)

        # Orientation
        orient_box = QHBoxLayout()
        self.radio_landscape = QRadioButton("Landscape")
        self.radio_portrait = QRadioButton("Portrait")
        self.radio_landscape.setChecked(True)
        self.radio_landscape.toggled.connect(self._on_orientation_toggled)
        orient_box.addWidget(self.radio_landscape)
        orient_box.addWidget(self.radio_portrait)
        orient_box.addStretch()
        form_layout.addRow("Orientation:", orient_box)

        # DPI
        self.spin_dpi = QSpinBox()
        self.spin_dpi.setRange(72, 2400)
        self.spin_dpi.setValue(DEFAULT_DPI)
        self.spin_dpi.setSingleStep(50)
        self.spin_dpi.valueChanged.connect(self._update_pixel_preview)
        form_layout.addRow("Print Resolution (DPI):", self.spin_dpi)

        # Pixel preview readout
        self.lbl_pixels = QLabel("Output Resolution: ~1011 × 638 pixels")
        self.lbl_pixels.setStyleSheet("color: #38BDF8; font-weight: 500;")
        form_layout.addRow("", self.lbl_pixels)

        layout.addWidget(form_group)

        # Background properties
        bg_group = QGroupBox("Card Surface & Background")
        bg_layout = QFormLayout(bg_group)

        # Color picker
        color_box = QHBoxLayout()
        self.btn_bg_color = QPushButton()
        self.btn_bg_color.setFixedSize(36, 24)
        self._update_color_btn()
        self.btn_bg_color.clicked.connect(self._pick_color)
        color_box.addWidget(self.btn_bg_color)
        self.lbl_color_hex = QLabel(self._bg_color)
        color_box.addWidget(self.lbl_color_hex)
        color_box.addStretch()
        bg_layout.addRow("Background Color:", color_box)

        # Optional background image
        img_box = QHBoxLayout()
        self.txt_bg_image = QLineEdit()
        self.txt_bg_image.setPlaceholderText("Optional image file...")
        self.txt_bg_image.setReadOnly(True)
        img_box.addWidget(self.txt_bg_image)

        self.btn_browse_img = QPushButton("Browse...")
        self.btn_browse_img.clicked.connect(self._browse_image)
        img_box.addWidget(self.btn_browse_img)

        self.btn_clear_img = QPushButton("Clear")
        self.btn_clear_img.setToolTip("Remove background image")
        self.btn_clear_img.clicked.connect(self._clear_image)
        img_box.addWidget(self.btn_clear_img)

        # Optional border
        border_box = QHBoxLayout()
        self.btn_border_color = QPushButton()
        self.btn_border_color.setFixedSize(36, 24)
        self._border_color = (self.existing_template.border_color if self.existing_template and self.existing_template.border_color else "transparent")
        self._update_border_color_btn()
        self.btn_border_color.clicked.connect(self._pick_border_color)
        border_box.addWidget(self.btn_border_color)

        border_box.addWidget(QLabel("Width (px):"))
        self.spin_border_width = QSpinBox()
        self.spin_border_width.setRange(0, 50)
        self.spin_border_width.setValue(self.existing_template.border_width if self.existing_template else 0)
        border_box.addWidget(self.spin_border_width)
        border_box.addStretch()
        bg_layout.addRow("Optional Border:", border_box)

        # Margin & Safe Area
        safe_box = QHBoxLayout()
        self.spin_margin = QDoubleSpinBox()
        self.spin_margin.setRange(0.0, 50.0)
        self.spin_margin.setDecimals(1)
        self.spin_margin.setValue(self.existing_template.safe_area_margin_mm if self.existing_template else 3.0)
        self.spin_margin.setSuffix(" mm")
        safe_box.addWidget(self.spin_margin)
        safe_box.addWidget(QLabel("(print guide margin from card edges)"))
        safe_box.addStretch()
        bg_layout.addRow("Safe Area Margin:", safe_box)

        layout.addWidget(bg_group)

        # Dialog Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_from_template(self, tmpl: TemplateDefinition) -> None:
        """Pre-populate dialog controls from an existing template."""
        self.txt_name.setText(tmpl.name)

        unit = tmpl.unit or "mm"
        idx = self.combo_unit.findText(unit)
        if idx >= 0:
            self.combo_unit.blockSignals(True)
            self.combo_unit.setCurrentIndex(idx)
            self.combo_unit.blockSignals(False)

        dpi = tmpl.dpi or DEFAULT_DPI
        self.spin_dpi.blockSignals(True)
        self.spin_dpi.setValue(dpi)
        self.spin_dpi.blockSignals(False)

        # Determine physical dimensions
        if tmpl.width_physical and tmpl.height_physical:
            w_val = tmpl.width_physical
            h_val = tmpl.height_physical
        else:
            w_mm = tmpl.width_px / dpi * 25.4
            h_mm = tmpl.height_px / dpi * 25.4
            w_val = convert_unit(w_mm, "mm", unit)
            h_val = convert_unit(h_mm, "mm", unit)

        is_portrait = (tmpl.orientation.lower() == "portrait") or (tmpl.height_px > tmpl.width_px)
        self.radio_portrait.blockSignals(True)
        self.radio_landscape.blockSignals(True)
        self.radio_portrait.setChecked(is_portrait)
        self.radio_landscape.setChecked(not is_portrait)
        self.radio_portrait.blockSignals(False)
        self.radio_landscape.blockSignals(False)

        self.spin_width.blockSignals(True)
        self.spin_height.blockSignals(True)
        self.spin_width.setValue(round(w_val, 2))
        self.spin_height.setValue(round(h_val, 2))
        self.spin_width.blockSignals(False)
        self.spin_height.blockSignals(False)

        # Match preset
        w_mm = convert_unit(w_val, unit, "mm")
        h_mm = convert_unit(h_val, unit, "mm")
        dim_pair = (min(round(w_mm, 1), round(h_mm, 1)), max(round(w_mm, 1), round(h_mm, 1)))
        self.combo_presets.blockSignals(True)
        if dim_pair == (54.0, 85.6):
            self.combo_presets.setCurrentIndex(0)
        elif dim_pair == (52.1, 83.9):
            self.combo_presets.setCurrentIndex(1)
        elif dim_pair == (70.0, 100.0):
            self.combo_presets.setCurrentIndex(2)
        else:
            self.combo_presets.setCurrentIndex(3)
        self.combo_presets.blockSignals(False)

        # Surface
        self._bg_color = tmpl.background_color or "#FFFFFF"
        self._update_color_btn()

        if tmpl.border_color:
            self._border_color = tmpl.border_color
            self._update_border_color_btn()
        self.spin_border_width.setValue(tmpl.border_width or 0)
        self.spin_margin.setValue(tmpl.safe_area_margin_mm or 3.0)

        if tmpl.background_image_path:
            self._bg_image_path = tmpl.background_image_path
            self.txt_bg_image.setText(Path(tmpl.background_image_path).name)
        else:
            self._bg_image_path = None
            self.txt_bg_image.clear()

        self._update_pixel_preview()

    def _on_preset_changed(self, index: int) -> None:
        unit = self.combo_unit.currentText()
        if index == 0:  # CR80
            w_mm, h_mm = 85.6, 54.0
        elif index == 1:  # CR79
            w_mm, h_mm = 83.9, 52.1
        elif index == 2:  # Visitor badge
            w_mm, h_mm = 100.0, 70.0
        else:
            return

        w = convert_unit(w_mm, "mm", unit)
        h = convert_unit(h_mm, "mm", unit)

        if self.radio_portrait.isChecked():
            self.spin_width.setValue(round(h, 2))
            self.spin_height.setValue(round(w, 2))
        else:
            self.spin_width.setValue(round(w, 2))
            self.spin_height.setValue(round(h, 2))

        self._update_pixel_preview()

    def _on_unit_changed(self, new_unit: str) -> None:
        self._update_pixel_preview()

    def _on_orientation_toggled(self) -> None:
        w = self.spin_width.value()
        h = self.spin_height.value()
        if self.radio_portrait.isChecked() and w > h:
            self.spin_width.setValue(h)
            self.spin_height.setValue(w)
        elif self.radio_landscape.isChecked() and h > w:
            self.spin_width.setValue(h)
            self.spin_height.setValue(w)
        self._update_pixel_preview()

    def _update_pixel_preview(self) -> None:
        unit = self.combo_unit.currentText()
        w = self.spin_width.value()
        h = self.spin_height.value()
        dpi = self.spin_dpi.value()
        orient = "portrait" if self.radio_portrait.isChecked() else "landscape"

        w_px, h_px, _, _ = calculate_card_dimensions(w, h, unit, dpi, orient)
        self.lbl_pixels.setText(f"Output Resolution: {w_px} × {h_px} pixels")

    def _pick_color(self) -> None:
        col = QColorDialog.getColor(QColor(self._bg_color), self, "Select Card Background Color")
        if col.isValid():
            self._bg_color = col.name().upper()
            self._update_color_btn()

    def _update_color_btn(self) -> None:
        self.btn_bg_color.setStyleSheet(f"background-color: {self._bg_color}; border: 1px solid #64748B; border-radius: 4px;")
        if hasattr(self, "lbl_color_hex"):
            self.lbl_color_hex.setText(self._bg_color)

    def _pick_border_color(self) -> None:
        cur_col = QColor(self._border_color) if self._border_color != "transparent" else QColor("#000000")
        col = QColorDialog.getColor(cur_col, self, "Select Border Color")
        if col.isValid():
            self._border_color = col.name().upper()
            self._update_border_color_btn()

    def _update_border_color_btn(self) -> None:
        if hasattr(self, "btn_border_color"):
            bg_css = self._border_color if self._border_color != "transparent" else "#E2E8F0"
            self.btn_border_color.setStyleSheet(f"background-color: {bg_css}; border: 1px solid #64748B; border-radius: 4px;")

    def _browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Background Image",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            self._bg_image_path = path
            self.txt_bg_image.setText(Path(path).name)

    def _clear_image(self) -> None:
        self._bg_image_path = None
        self.txt_bg_image.clear()

    def _on_accept(self) -> None:
        unit = self.combo_unit.currentText()
        w = self.spin_width.value()
        h = self.spin_height.value()
        dpi = self.spin_dpi.value()
        orient = "portrait" if self.radio_portrait.isChecked() else "landscape"

        w_px, h_px, _, _ = calculate_card_dimensions(w, h, unit, dpi, orient)

        bw = self.spin_border_width.value() if hasattr(self, "spin_border_width") else 0
        b_col = self._border_color if (bw > 0 and self._border_color != "transparent") else None
        safe_margin = self.spin_margin.value() if hasattr(self, "spin_margin") else 3.0

        if self.existing_template:
            # Preserve all existing canvas elements and IDs while updating canvas properties
            self.template_definition = self.existing_template.model_copy(deep=True)
            self.template_definition.name = self.txt_name.text().strip() or self.existing_template.name
            self.template_definition.width_px = w_px
            self.template_definition.height_px = h_px
            self.template_definition.dpi = dpi
            self.template_definition.unit = unit
            self.template_definition.width_physical = w
            self.template_definition.height_physical = h
            self.template_definition.orientation = orient
            self.template_definition.background_color = self._bg_color
            self.template_definition.background_image_path = self._bg_image_path
            self.template_definition.border_color = b_col
            self.template_definition.border_width = bw
            self.template_definition.safe_area_margin_mm = safe_margin
        else:
            self.template_definition = TemplateDefinition(
                name=self.txt_name.text().strip() or "Blank ID Card",
                width_px=w_px,
                height_px=h_px,
                dpi=dpi,
                unit=unit,
                width_physical=w,
                height_physical=h,
                orientation=orient,
                background_color=self._bg_color,
                background_image_path=self._bg_image_path,
                border_color=b_col,
                border_width=bw,
                safe_area_margin_mm=safe_margin,
                elements=[],
            )
        self.accept()


# Semantic alias for explicit property editing
CanvasPropertiesDialog = BlankCanvasDialog
