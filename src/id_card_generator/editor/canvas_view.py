"""Custom QGraphicsView with zoom, pan, and smooth navigation."""

import logging
from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QWheelEvent
from PySide6.QtWidgets import QGraphicsView

logger = logging.getLogger(__name__)


class CanvasView(QGraphicsView):
    """Interactive viewport for the ID card graphics scene."""

    zoom_changed = Signal(float)

    def __init__(self, scene=None, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(
            QPainter.Antialiasing
            | QPainter.SmoothPixmapTransform
            | QPainter.TextAntialiasing
        )
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._zoom_factor = 1.0
        self._min_zoom = 0.2
        self._max_zoom = 5.0

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom_factor * 1.2)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom_factor / 1.2)

    def reset_zoom(self) -> None:
        self.set_zoom(1.0)

    def fit_to_view(self) -> None:
        """Scale canvas to fit completely within the viewport."""
        if not self.scene():
            return
        self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)
        # Update current zoom factor estimate
        self._zoom_factor = self.transform().m11()
        self.zoom_changed.emit(self._zoom_factor)

    def set_zoom(self, factor: float) -> None:
        factor = max(self._min_zoom, min(self._max_zoom, factor))
        scale_delta = factor / self._zoom_factor
        self.scale(scale_delta, scale_delta)
        self._zoom_factor = factor
        self.zoom_changed.emit(self._zoom_factor)

    def wheelEvent(self, event: QWheelEvent):
        """Zoom with mouse wheel when Ctrl is held, or pan vertically."""
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)
