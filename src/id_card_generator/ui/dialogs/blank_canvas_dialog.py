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
    """Dialog allowing users to create a clean blank canvas with physical dimensions and DPI."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Blank Canvas")
        self.setMinimumWidth(440)
        self.template_definition: Optional[TemplateDefinition] = None

        self._bg_color = "#FFFFFF"
        self._bg_image_path: Optional[str] = None

        self._setup_ui()
        self._on_preset_changed(0)  # Standard CR80 default

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # Header
        lbl_head = QLabel("<b>Create New Blank Canvas</b>")
        lbl_head.setStyleSheet("font-size: 15px;")
        layout.addWidget(lbl_head)
        lbl_desc = QLabel("Configure physical card dimensions, DPI, and background properties.")
        lbl_desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(lbl_desc)

        form_group = QGroupBox("Document Specifications")
        form_layout = QFormLayout(form_group)

        # Name
        self.txt_name = QLineEdit("Blank ID Card")
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
        bg_layout.addRow("Background Image:", img_box)

        layout.addWidget(bg_group)

        # Dialog Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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

    def _on_accept(self) -> None:
        unit = self.combo_unit.currentText()
        w = self.spin_width.value()
        h = self.spin_height.value()
        dpi = self.spin_dpi.value()
        orient = "portrait" if self.radio_portrait.isChecked() else "landscape"

        w_px, h_px, _, _ = calculate_card_dimensions(w, h, unit, dpi, orient)

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
            elements=[],
        )
        self.accept()
