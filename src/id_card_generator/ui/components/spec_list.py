"""A quiet key/value list used to present template specifications."""

from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from id_card_generator.ui.studio_tokens import (
    FONT_FAMILY_MONO,
    TEXT_MUTED,
    TEXT_PRIMARY,
)


class SpecList(QWidget):
    """Renders specifications as neat label / value rows.

    Replaces the dense monospace blob with a scannable list.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(7)
        self._grid.setColumnStretch(1, 1)
        self._rows: List[Tuple[str, str]] = []

    def set_rows(self, rows: List[Tuple[str, str]]) -> None:
        """Replace the content with the given label / value pairs."""
        self._rows = list(rows)
        self._rebuild()

    def add_row(self, label: str, value: str) -> None:
        """Append a label / value pair."""
        self._rows.append((label, value))
        self._rebuild()

    def clear(self) -> None:
        self.set_rows([])

    def _rebuild(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for row, (label, value) in enumerate(self._rows):
            key = QLabel(label)
            key.setProperty("role", "specKey")
            key.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self._grid.addWidget(key, row, 0)

            val = QLabel(value)
            val.setProperty("role", "specValue")
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._grid.addWidget(val, row, 1)
