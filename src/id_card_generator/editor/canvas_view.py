"""Custom QGraphicsView with zoom, pan, enlarged auto-fit, and smooth navigation."""

import logging
from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QWheelEvent
from PySide6.QtWidgets import QGraphicsView

logger = logging.getLogger(__name__)


class CanvasView(QGraphicsView):
    """Interactive viewport for the ID card graphics scene with enlarged presentation."""

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

    def fit_to_view(self, enlarge_factor: float = 1.30) -> None:
        """Scale canvas to fill viewport prominently with comfortable enlargement."""
        if not self.scene():
            return
        
        scene_rect = self.scene().sceneRect()
        if scene_rect.width() <= 0 or scene_rect.height() <= 0:
            return

        self.resetTransform()
        vp = self.viewport()
        vp_w = vp.width()
        vp_h = vp.height()

        if vp_w > 50 and vp_h > 50:
            # Calculate scale that fits viewport with modest padding
            scale_x = (vp_w - 30) / scene_rect.width()
            scale_y = (vp_h - 30) / scene_rect.height()
            base_fit = min(scale_x, scale_y)
            # Apply comfortable enlargement factor so card is large and legible
            target_scale = max(0.4, base_fit * enlarge_factor)
            self.scale(target_scale, target_scale)
            self._zoom_factor = target_scale
        else:
            self.fitInView(scene_rect, Qt.KeepAspectRatio)
            self.scale(enlarge_factor, enlarge_factor)
            self._zoom_factor = self.transform().m11()

        self.centerOn(scene_rect.center())
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

    def keyPressEvent(self, event):
        """Forward undo, redo, and arrow key nudges to canvas scene."""
        is_ctrl_or_cmd = bool(event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier))
        if is_ctrl_or_cmd:
            if event.key() == Qt.Key_Z:
                if event.modifiers() & Qt.ShiftModifier:
                    if self.scene() and hasattr(self.scene(), "redo"):
                        self.scene().redo()
                else:
                    if self.scene() and hasattr(self.scene(), "undo"):
                        self.scene().undo()
                event.accept()
                return
            elif event.key() == Qt.Key_Y:
                if self.scene() and hasattr(self.scene(), "redo"):
                    self.scene().redo()
                event.accept()
                return

        # Forward arrow keys to canvas scene for element nudging instead of scrolling view
        if event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            if self.scene() and hasattr(self.scene(), "keyPressEvent"):
                self.scene().keyPressEvent(event)
                if event.isAccepted():
                    return

        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        """Translate Shift and Meta (Cmd on macOS) to ControlModifier for multi-item selection."""
        if event.modifiers() & (Qt.ShiftModifier | Qt.MetaModifier):
            event.setModifiers(event.modifiers() | Qt.ControlModifier)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Translate Shift and Meta (Cmd on macOS) to ControlModifier for multi-item selection."""
        if event.modifiers() & (Qt.ShiftModifier | Qt.MetaModifier):
            event.setModifiers(event.modifiers() | Qt.ControlModifier)
        super().mouseReleaseEvent(event)

