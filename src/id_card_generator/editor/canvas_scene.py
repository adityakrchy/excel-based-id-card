"""QGraphicsScene managing the card canvas, background, grid snapping, and items."""

import logging
from typing import Dict, List, Optional
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QKeyEvent,
    QPainter,
    QPen,
    QPixmap,
    QUndoStack,
)
from PySide6.QtWidgets import QGraphicsScene

from id_card_generator.core.models import CanvasElement, SourceRecord, TemplateDefinition
from id_card_generator.editor.canvas_items import CanvasItem

logger = logging.getLogger(__name__)


class CanvasScene(QGraphicsScene):
    """Custom graphics scene representing the card template workspace."""

    element_selected = Signal(object)  # CanvasItem or None
    template_modified = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.template: Optional[TemplateDefinition] = None
        self._items_by_id: Dict[str, CanvasItem] = {}
        self.undo_stack = QUndoStack(self)

        self.snap_to_grid = True
        self.grid_size = 10.0
        self.show_grid = True
        self.show_safe_area = True

        self._sample_record: Optional[SourceRecord] = None
        self._sample_photo_path: Optional[str] = None
        self._background_pixmap: Optional[QPixmap] = None

        self.selectionChanged.connect(self._on_selection_changed)

    def undo(self) -> None:
        """Undo last canvas action."""
        self.undo_stack.undo()
        self.update()
        self.template_modified.emit()

    def redo(self) -> None:
        """Redo last undone canvas action."""
        self.undo_stack.redo()
        self.update()
        self.template_modified.emit()

    def load_template(self, template: TemplateDefinition) -> None:
        """Load a template definition into the scene."""
        self.clear()
        self._items_by_id.clear()
        self.template = template

        w = template.width_px
        h = template.height_px
        self.setSceneRect(0, 0, w, h)

        if template.background_image_path:
            self._background_pixmap = QPixmap(template.background_image_path)
        else:
            self._background_pixmap = None

        # Add elements
        for elem in template.elements:
            self._create_and_add_item(elem)

        self.update()

    def _create_and_add_item(self, elem: CanvasElement) -> CanvasItem:
        item = CanvasItem(elem)
        item.set_sample_data(self._sample_record, self._sample_photo_path)
        item.geometry_changed.connect(self._on_item_geometry_changed)
        self.addItem(item)
        self._items_by_id[elem.id] = item
        return item

    def set_sample_data(self, record: Optional[SourceRecord], photo_path: Optional[str]) -> None:
        """Set sample data for live canvas preview."""
        self._sample_record = record
        self._sample_photo_path = photo_path
        for item in self._items_by_id.values():
            item.set_sample_data(record, photo_path)
        self.update()

    def get_selected_item(self) -> Optional[CanvasItem]:
        selected = self.selectedItems()
        for it in selected:
            if isinstance(it, CanvasItem):
                return it
        return None

    def add_element(self, element: CanvasElement) -> CanvasItem:
        """Add a new element to current template and scene."""
        if self.template:
            self.template.elements.append(element)
        item = self._create_and_add_item(element)
        self.clearSelection()
        item.setSelected(True)
        self.template_modified.emit()
        return item

    def delete_selected(self) -> None:
        """Delete selected elements from scene and template."""
        selected = [it for it in self.selectedItems() if isinstance(it, CanvasItem)]
        for item in selected:
            if self.template and item.element in self.template.elements:
                self.template.elements.remove(item.element)
            if item.element.id in self._items_by_id:
                del self._items_by_id[item.element.id]
            self.removeItem(item)
        self.template_modified.emit()

    def duplicate_selected(self) -> None:
        """Duplicate selected elements."""
        selected = self.get_selected_item()
        if not selected or not self.template:
            return

        import uuid
        data = selected.element.model_dump(mode="json")
        data["id"] = str(uuid.uuid4())
        data["name"] = f"{selected.element.name} (Copy)"
        data["x"] += 20.0
        data["y"] += 20.0

        new_elem = CanvasElement.model_validate(data)
        self.add_element(new_elem)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """Draw card background, image, and optional grid."""
        if not self.template:
            return

        scene_rect = self.sceneRect()
        painter.save()

        # Fill card background color
        bg_col = QColor(self.template.background_color or "#FFFFFF")
        painter.fillRect(scene_rect, bg_col)

        # Draw background image if set
        if self._background_pixmap and not self._background_pixmap.isNull():
            painter.drawPixmap(scene_rect.toRect(), self._background_pixmap)

        # Draw grid lines if enabled
        if self.show_grid and self.grid_size > 0:
            grid_pen = QPen(QColor(220, 226, 235), 0.5, Qt.DotLine)
            painter.setPen(grid_pen)

            x = scene_rect.left()
            while x <= scene_rect.right():
                painter.drawLine(QPointF(x, scene_rect.top()), QPointF(x, scene_rect.bottom()))
                x += self.grid_size

            y = scene_rect.top()
            while y <= scene_rect.bottom():
                painter.drawLine(QPointF(scene_rect.left(), y), QPointF(scene_rect.right(), y))
                y += self.grid_size

        # Safe area indicator (20px margin inside card)
        if self.show_safe_area:
            safe_rect = scene_rect.adjusted(20, 20, -20, -20)
            safe_pen = QPen(QColor(59, 130, 246, 60), 1.0, Qt.DashLine)
            painter.setPen(safe_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(safe_rect)

        # Outer card boundary shadow outline
        painter.setPen(QPen(QColor(148, 163, 184), 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(scene_rect)

        painter.restore()

    def keyPressEvent(self, event: QKeyEvent):
        """Keyboard navigation: nudge with arrows, delete with Del/Backspace."""
        item = self.get_selected_item()
        if not item or item.element.locked:
            super().keyPressEvent(event)
            return

        step = 10.0 if (event.modifiers() & Qt.ShiftModifier) else 1.0

        if event.key() == Qt.Key_Left:
            item.setPos(item.pos().x() - step, item.pos().y())
            item.update_model_position()
            self.template_modified.emit()
            event.accept()
        elif event.key() == Qt.Key_Right:
            item.setPos(item.pos().x() + step, item.pos().y())
            item.update_model_position()
            self.template_modified.emit()
            event.accept()
        elif event.key() == Qt.Key_Up:
            item.setPos(item.pos().x(), item.pos().y() - step)
            item.update_model_position()
            self.template_modified.emit()
            event.accept()
        elif event.key() == Qt.Key_Down:
            item.setPos(item.pos().x(), item.pos().y() + step)
            item.update_model_position()
            self.template_modified.emit()
            event.accept()
        elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _on_selection_changed(self):
        item = self.get_selected_item()
        self.element_selected.emit(item)

    def _on_item_geometry_changed(self, item: CanvasItem):
        # Snap to grid if active
        if self.snap_to_grid and self.grid_size > 0:
            gs = self.grid_size
            snapped_x = round(item.pos().x() / gs) * gs
            snapped_y = round(item.pos().y() / gs) * gs
            item.setPos(snapped_x, snapped_y)
            item.element.x = snapped_x
            item.element.y = snapped_y

        self.template_modified.emit()
