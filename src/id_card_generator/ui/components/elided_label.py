"""Labels that elide their text instead of clipping it."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel, QSizePolicy


class ElidedLabel(QLabel):
    """A label that shortens its text with an ellipsis when space is tight.

    Toolbar rows carry long values (template names, file paths, dimensions).
    A plain QLabel simply cuts the text off, which looks broken - this label
    keeps the full value in the tooltip and elides the visible text.
    """

    def __init__(self, text: str = "", mode=Qt.ElideRight, parent=None):
        super().__init__(parent)
        self._full_text = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setMinimumWidth(48)
        super().setText(text)

    # -- content ----------------------------------------------------
    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._full_text = text
        self._apply_elide()

    def fullText(self) -> str:  # noqa: N802 - Qt naming
        """Return the unelided text."""
        return self._full_text

    def setElideMode(self, mode) -> None:  # noqa: N802 - Qt naming
        self._mode = mode
        self._apply_elide()

    # -- internals --------------------------------------------------
    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        available = max(0, self.width() - 4)
        if not self._full_text:
            super().setText("")
            return

        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(self._full_text, self._mode, available)
        super().setText(elided)
        self.setToolTip(self._full_text)
