"""Rolling throughput chart for the batch generation engine.

The graph keeps a short history of the render rate (cards per second) and
draws it as a filled area chart, so a slow batch is obvious at a glance.
"""

from collections import deque
from typing import Deque, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from id_card_generator.ui.studio_tokens import (
    FONT_FAMILY_MONO,
    FONT_FAMILY_UI,
    active_palette,
)


class SpeedGraph(QWidget):
    """Area chart of the recent render throughput."""

    def __init__(
        self,
        parent=None,
        capacity: int = 90,
        minimum_height: int = 92,
    ):
        super().__init__(parent)
        self._capacity = max(4, int(capacity))
        self._samples: Deque[float] = deque(maxlen=self._capacity)
        self._peak = 0.0

        # The chart is hand painted, so it must not paint a surface of its own.
        self.setProperty("role", "flat")
        self.setMinimumHeight(minimum_height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # -- state ------------------------------------------------------
    @property
    def peak(self) -> float:
        """The highest rate that was recorded since the last reset."""
        return self._peak

    @property
    def last_value(self) -> float:
        """The most recent sample (0.0 when the graph is empty)."""
        return self._samples[-1] if self._samples else 0.0

    def push_sample(self, value: float) -> None:
        """Append a throughput sample (cards per second)."""
        try:
            value = float(value)
        except (TypeError, ValueError):
            return
        value = max(0.0, value)
        self._samples.append(value)
        if value > self._peak:
            self._peak = value
        self.update()

    def clear_samples(self) -> None:
        """Drop the history and the peak."""
        self._samples.clear()
        self._peak = 0.0
        self.update()

    # -- painting ---------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        palette = active_palette()
        grid = QColor(palette.OUTLINE_VARIANT)
        line = QColor(palette.PRIMARY_CONTAINER)
        muted = QColor(palette.TEXT_MUTED)
        text_color = QColor(palette.ON_SURFACE)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        # Background grid - three quiet horizontal rules.
        painter.setPen(QPen(grid, 1))
        for fraction in (0.0, 0.5, 1.0):
            y = rect.top() + rect.height() * fraction
            painter.drawLine(
                QPointF(rect.left(), y), QPointF(rect.right(), y)
            )

        samples = list(self._samples)
        if not samples:
            self._paint_empty(painter, rect, muted)
            return

        top = max(self._peak, 1.0)
        count = len(samples)
        step = rect.width() / float(max(1, self._capacity - 1))

        points = []
        for index, value in enumerate(samples):
            x = rect.left() + step * (self._capacity - count + index)
            y = rect.bottom() - (value / top) * (rect.height() - 12.0)
            points.append(QPointF(x, y))

        # Filled area under the curve.
        area = QPainterPath()
        area.moveTo(points[0].x(), rect.bottom())
        for point in points:
            area.lineTo(point.x(), point.y())
        area.lineTo(points[-1].x(), rect.bottom())
        area.closeSubpath()

        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, QColor(line.red(), line.green(), line.blue(), 90))
        gradient.setColorAt(1.0, QColor(line.red(), line.green(), line.blue(), 8))
        painter.fillPath(area, gradient)

        # The line itself.
        stroke = QPainterPath()
        stroke.moveTo(points[0])
        for point in points[1:]:
            stroke.lineTo(point)
        painter.setPen(QPen(line, 2))
        painter.drawPath(stroke)

        # The most recent point gets a dot.
        painter.setBrush(line)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(points[-1], 3.0, 3.0)

        # Labels: the current rate on the left, the peak on the right.
        font = QFont()
        font.setFamily(FONT_FAMILY_MONO)
        font.setPointSizeF(9.0)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(
            QRectF(rect.left() + 2, rect.top() + 2, 160, 16),
            Qt.AlignLeft | Qt.AlignTop,
            f"{self.last_value:.1f} /s",
        )

        font = QFont()
        font.setFamily(FONT_FAMILY_UI)
        font.setPointSizeF(8.0)
        painter.setFont(font)
        painter.setPen(muted)
        painter.drawText(
            QRectF(rect.right() - 160, rect.top() + 3, 158, 16),
            Qt.AlignRight | Qt.AlignTop,
            f"peak {self._peak:.1f} /s",
        )

    def _paint_empty(self, painter: QPainter, rect: QRectF, muted: QColor) -> None:
        font = QFont()
        font.setFamily(FONT_FAMILY_UI)
        font.setPointSizeF(9.0)
        painter.setFont(font)
        painter.setPen(muted)
        painter.drawText(rect, Qt.AlignCenter, "Waiting for the first card...")
