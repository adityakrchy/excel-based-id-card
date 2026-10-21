"""Circular progress indicator for the batch generation engine.

The ring is split into one arc per render worker, so the operator can see at a
glance how the work is spread over the thread pool.  The overall progress of
the batch is printed in the centre.
"""

from typing import Iterable, List, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from id_card_generator.ui.studio_tokens import (
    FONT_FAMILY_MONO,
    FONT_FAMILY_UI,
    TYPOGRAPHY,
    active_palette,
)


class ProgressRing(QWidget):
    """A progress ring with one segment per render worker."""

    RING_WIDTH = 12
    SEGMENT_GAP = 6.0

    def __init__(self, parent=None, diameter: int = 168, cores: int = 1):
        super().__init__(parent)
        self._diameter = int(diameter)
        self._cores = max(1, int(cores))
        self._value = 0.0
        self._core_values: List[float] = []
        self._caption = ""
        self._detail = ""

        # The ring is hand painted, so it must not paint a surface of its own.
        self.setProperty("role", "flat")
        self.setFixedSize(self._diameter, self._diameter)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    # -- state ------------------------------------------------------
    @property
    def value(self) -> float:
        """The overall progress as a fraction between 0 and 1."""
        return self._value

    @property
    def cores(self) -> int:
        """The number of worker segments of the ring."""
        return self._cores

    def set_progress(self, value: float) -> None:
        """Set the overall progress (0..1)."""
        try:
            value = float(value)
        except (TypeError, ValueError):
            return
        value = 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)
        if abs(value - self._value) < 1e-6:
            return
        self._value = value
        self.update()

    def set_cores(self, cores: int) -> None:
        """Set the number of worker segments."""
        cores = max(1, int(cores))
        if cores == self._cores:
            return
        self._cores = cores
        self._core_values = []
        self.update()

    def set_core_values(self, values: Iterable[float]) -> None:
        """Set the per worker progress (a list of fractions)."""
        self._core_values = [
            max(0.0, min(1.0, float(value))) for value in values
        ]
        self.update()

    def set_caption(self, text: str) -> None:
        """Set the small line below the percentage."""
        text = str(text)
        if text == self._caption:
            return
        self._caption = text
        self.update()

    def set_detail(self, text: str) -> None:
        """Set the small line above the percentage."""
        text = str(text)
        if text == self._detail:
            return
        self._detail = text
        self.update()

    # -- painting ---------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        palette = active_palette()
        track = QColor(palette.SURFACE_LOWEST)
        arc = QColor(palette.PRIMARY_CONTAINER)
        text_color = QColor(palette.ON_SURFACE)
        muted = QColor(palette.TEXT_MUTED)

        thickness = self.RING_WIDTH
        side = min(self.width(), self.height())
        radius = (side - thickness) / 2.0 - 2.0
        centre_x = self.width() / 2.0
        centre_y = self.height() / 2.0

        ring_rect = QRectF(
            centre_x - radius, centre_y - radius, radius * 2.0, radius * 2.0
        )

        track_pen = QPen(track, thickness)
        track_pen.setCapStyle(Qt.FlatCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(ring_rect, 0, 360 * 16)

        if self._cores == 1:
            span = int(-360 * 16 * self._value)
            if span:
                painter.setPen(QPen(arc, thickness, Qt.SolidLine, Qt.RoundCap))
                painter.drawArc(ring_rect, 90 * 16, span)
        else:
            segment = 360.0 / self._cores
            for index in range(self._cores):
                if index < len(self._core_values):
                    value = self._core_values[index]
                else:
                    value = self._value
                start = 90.0 - index * segment
                painter.setPen(QPen(track, thickness, Qt.SolidLine, Qt.FlatCap))
                painter.drawArc(
                    ring_rect,
                    int(start * 16),
                    int(-(segment - self.SEGMENT_GAP) * 16),
                )
                if value > 0:
                    painter.setPen(QPen(arc, thickness, Qt.SolidLine, Qt.RoundCap))
                    painter.drawArc(
                        ring_rect,
                        int(start * 16),
                        int(-(segment - self.SEGMENT_GAP) * value * 16),
                    )

        # --- centre text ------------------------------------------------
        percent = int(round(self._value * 100))

        if self._detail:
            font = QFont()
            font.setFamily(FONT_FAMILY_UI)
            font.setPointSizeF(8.0)
            painter.setFont(font)
            painter.setPen(muted)
            painter.drawText(
                QRectF(
                    centre_x - radius,
                    centre_y - radius * 0.62,
                    radius * 2.0,
                    18,
                ),
                Qt.AlignCenter,
                self._detail,
            )

        font = QFont()
        font.setFamily(FONT_FAMILY_MONO)
        font.setPointSizeF(26.0)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(
            QRectF(centre_x - radius, centre_y - radius * 0.42, radius * 2.0, 44),
            Qt.AlignCenter,
            f"{percent}%",
        )

        if self._caption:
            font = QFont()
            font.setFamily(FONT_FAMILY_UI)
            font.setPointSizeF(8.0)
            painter.setFont(font)
            painter.setPen(muted)
            painter.drawText(
                QRectF(
                    centre_x - radius,
                    centre_y + radius * 0.30,
                    radius * 2.0,
                    18,
                ),
                Qt.AlignCenter,
                self._caption,
            )

    def sizeHint(self):  # noqa: N802 - Qt naming
        from PySide6.QtCore import QSize

        return QSize(self._diameter, self._diameter)
