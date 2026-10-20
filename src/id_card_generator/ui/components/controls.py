"""Helpers that keep the input controls of a screen visually even."""

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QTextEdit,
    QWidget,
)

from id_card_generator.ui.studio_tokens import SIZES

INPUT_TYPES = (
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QFontComboBox,
)


def normalize_control_heights(
    root: QWidget,
    height: int = SIZES.CONTROL_HEIGHT,
) -> None:
    """Give every input control the same height.

    Spin boxes are naturally taller than combo boxes (their stepper buttons
    stack vertically), so a row of controls ends up with mismatched boxes.
    Fixing the height keeps every toolbar and form row on one baseline.
    """
    for child in root.findChildren(QWidget):
        if isinstance(child, INPUT_TYPES):
            child.setFixedHeight(height)
        elif isinstance(child, (QTextEdit, QPlainTextEdit)):
            # Multi line editors keep their natural height.
            continue
