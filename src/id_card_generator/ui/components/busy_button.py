"""A button that shows a spinner while it is busy.

The batch button is the only place where the user waits, so the wait is shown
right on the button instead of in a separate status field.
"""

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QPushButton


class BusyButton(QPushButton):
    """A push button with a small rotating spinner next to its label."""

    SPINNER_RADIUS = 7
    SPINNER_GAP = 18
    FRAME_MS = 70

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._busy = False
        self._angle = 0

        self._timer = QTimer(self)
        self._timer.setInterval(self.FRAME_MS)
        self._timer.timeout.connect(self._spin)

    # -- state ------------------------------------------------------
    @property
    def is_busy(self) -> bool:
        """True while the spinner is running."""
        return self._busy

    def set_busy(self, busy: bool) -> None:
        """Show or hide the spinner."""
        busy = bool(busy)
        if busy == self._busy:
            return
        self._busy = busy
        if busy:
            self._angle = 0
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _spin(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    # -- painting ---------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().paintEvent(event)
        if not self._busy:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        color = self.palette().color(QPalette.ButtonText)
        if not color.isValid():  # pragma: no cover - defensive
            color = QColor("#ffffff")

        metrics = self.fontMetrics()
        text_width = metrics.horizontalAdvance(self.text())
        centre_x = (self.width() - text_width) / 2.0 - self.SPINNER_GAP
        centre_y = self.height() / 2.0

        radius = self.SPINNER_RADIUS
        rect = QRectF(
            centre_x - radius, centre_y - radius, radius * 2, radius * 2
        )

        pen = QPen(color, 2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(rect, -self._angle * 16, 260 * 16)
