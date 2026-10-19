"""Status pill indicator with a colored dot and clean label."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel
from id_card_generator.ui.studio_tokens import COLORS, TYPOGRAPHY


class StatusPill(QFrame):
    """Pill badge for status indicators (e.g. Connected, Auto-saved, Warnings)."""

    def __init__(
        self,
        text: str = "",
        dot_color: str = COLORS.TERTIARY,
        parent=None,
        show_dot: bool = True,
        color: str = "",
    ):
        super().__init__(parent)
        self.setObjectName("status_pill")
        self._dot_color = color or dot_color
        self._show_dot = show_dot

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        self.dot = QLabel()
        self.dot.setFixedSize(6, 6)
        self.set_dot_color(self._dot_color)
        if not show_dot:
            self.dot.setVisible(False)
        layout.addWidget(self.dot)

        self.lbl_text = QLabel(text)
        self.lbl_text.setStyleSheet(
            f"color: {COLORS.ON_SURFACE_VARIANT}; font-family: {TYPOGRAPHY.FONT_FAMILY_MONO}; "
            f"font-size: 11px; font-weight: 500;"
        )
        layout.addWidget(self.lbl_text)

        self._apply_frame_style()

    def _apply_frame_style(self) -> None:
        self.setStyleSheet(
            f"QFrame#status_pill {{"
            f"  background-color: {COLORS.SURFACE_CONTAINER};"
            f"  border: 1px solid {COLORS.OUTLINE_VARIANT};"
            f"  border-radius: 4px;"
            f"}}"
        )

    def set_dot_color(self, hex_color: str) -> None:
        self._dot_color = hex_color
        self.dot.setStyleSheet(
            f"background-color: {hex_color}; border-radius: 3px;"
        )

    def set_text(self, text: str) -> None:
        self.lbl_text.setText(text)

    def set_status(self, text: str, color: str = "") -> None:
        self.lbl_text.setText(text)
        if color:
            self.set_dot_color(color)

    def text(self) -> str:
        return self.lbl_text.text()
