"""High-density precision numeric input well with leading axis label and unit suffix."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit
from id_card_generator.ui.studio_tokens import COLORS, TYPOGRAPHY


class NumericWell(QFrame):
    """High-density numeric property well (e.g. [X | 14.50 | mm])."""

    valueChanged = Signal(float)

    def __init__(
        self,
        label: str = "X",
        value: float = 0.0,
        unit: str = "mm",
        decimals: int = 2,
        min_val: float = -9999.0,
        max_val: float = 9999.0,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("numeric_well_frame")
        self._decimals = decimals
        self._min_val = min_val
        self._max_val = max_val

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)
        self.setFixedHeight(26)

        # Leading Axis Tag
        self.lbl_tag = QLabel(label)
        self.lbl_tag.setStyleSheet(
            f"color: {COLORS.TEXT_MUTED}; font-family: {TYPOGRAPHY.FONT_FAMILY_MONO}; "
            f"font-size: 10px; font-weight: bold;"
        )
        layout.addWidget(self.lbl_tag)

        # Center Numeric LineEdit
        self.input_field = QLineEdit()
        self.input_field.setFrame(False)
        self.input_field.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.input_field.setStyleSheet(
            f"background: transparent; color: {COLORS.ON_SURFACE}; "
            f"font-family: {TYPOGRAPHY.FONT_FAMILY_MONO}; font-size: 11px; padding: 0;"
        )
        validator = QDoubleValidator(min_val, max_val, decimals, self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.input_field.setValidator(validator)
        self.set_value(value)
        self.input_field.editingFinished.connect(self._on_editing_finished)
        layout.addWidget(self.input_field, stretch=1)

        # Trailing Unit Suffix
        self.lbl_unit = QLabel(unit)
        self.lbl_unit.setStyleSheet(
            f"color: {COLORS.TEXT_MUTED}; font-family: {TYPOGRAPHY.FONT_FAMILY_MONO}; "
            f"font-size: 9px;"
        )
        if not unit:
            self.lbl_unit.setVisible(False)
        layout.addWidget(self.lbl_unit)

        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"QFrame#numeric_well_frame {{"
            f"  background-color: {COLORS.SURFACE_CONTAINER};"
            f"  border: 1px solid {COLORS.BORDER_HAIRLINE};"
            f"  border-radius: 4px;"
            f"}}"
            f"QFrame#numeric_well_frame:hover {{"
            f"  border-color: {COLORS.PRIMARY_CONTAINER};"
            f"}}"
        )

    def _on_editing_finished(self) -> None:
        val = self.value()
        self.valueChanged.emit(val)

    def value(self) -> float:
        try:
            return float(self.input_field.text().strip())
        except ValueError:
            return 0.0

    def set_value(self, val: float) -> None:
        text = f"{val:.{self._decimals}f}"
        self.input_field.setText(text)

    def set_label(self, label: str) -> None:
        self.lbl_tag.setText(label)

    def set_unit(self, unit: str) -> None:
        self.lbl_unit.setText(unit)
        self.lbl_unit.setVisible(bool(unit))
