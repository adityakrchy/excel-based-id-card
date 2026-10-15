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
        if self.undo_stack.canUndo():
            self.undo_stack.undo()
            self.update()
            self.template_modified.emit()

    def redo(self) -> None:
        """Redo last undone canvas action."""
        if self.undo_stack.canRedo():
            self.undo_stack.redo()
            self.update()
            self.template_modified.emit()

    def load_template(self, template: TemplateDefinition) -> None:
        """Load a template definition into the scene."""
        self.clear()
        self._items_by_id.clear()
        self.template = template
        self.undo_stack.clear()

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
        item.setZValue(elem.z_index)
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

    def add_element(self, element: CanvasElement, push_undo: bool = True) -> CanvasItem:
        """Add a new element to current template and scene with undo support, always on top."""
        # Calculate maximum existing z-index so new layer is placed on top of all canvas elements
        existing_z = [it.element.z_index for it in self._items_by_id.values() if it.element.id != element.id]
        max_z = max(existing_z) if existing_z else 0
        if element.z_index <= max_z:
            element.z_index = max_z + 1

        if push_undo:
            from id_card_generator.editor.undo_manager import AddElementCommand
            cmd = AddElementCommand(self, element)
            self.undo_stack.push(cmd)
            return self._items_by_id.get(element.id)
        else:
            if self.template and element not in self.template.elements:
                self.template.elements.append(element)
            item = self._create_and_add_item(element)
            self.clearSelection()
            item.setSelected(True)
            item.update()
            self.update()
            self.element_selected.emit(item)
            self.template_modified.emit()
            return item

    def _get_sorted_canvas_items(self) -> List[CanvasItem]:
        """Return all canvas items sorted ascending by z-value (bottom to top)."""
        items = [it for it in self.items() if isinstance(it, CanvasItem)]
        return sorted(items, key=lambda x: (x.zValue(), x.element.z_index))

    def _apply_layer_order(self, new_ordered_items: List[CanvasItem], description: str) -> None:
        """Assign normalized z-indices (1..N) and record undo command."""
        old_z_map = {it.element.id: int(it.zValue()) for it in self._items_by_id.values()}
        new_z_map = {}
        for idx, it in enumerate(new_ordered_items, start=1):
            it.setZValue(idx)
            it.element.z_index = idx
            new_z_map[it.element.id] = idx

        from id_card_generator.editor.undo_manager import ReorderLayersCommand
        self.undo_stack.push(ReorderLayersCommand(self, old_z_map, new_z_map, description))
        self.update()
        self.template_modified.emit()

    def bring_to_front(self, item: Optional[CanvasItem] = None) -> None:
        """Move layer on top of every other element on the canvas."""
        item = item or self.get_selected_item()
        if not item:
            return
        items = self._get_sorted_canvas_items()
        if item in items:
            items.remove(item)
            items.append(item)
            self._apply_layer_order(items, "Bring to Front")

    def bring_forward(self, item: Optional[CanvasItem] = None) -> None:
        """Move layer one step forward (on top of the element immediately above it)."""
        item = item or self.get_selected_item()
        if not item:
            return
        items = self._get_sorted_canvas_items()
        if item in items:
            idx = items.index(item)
            if idx < len(items) - 1:
                items[idx], items[idx + 1] = items[idx + 1], items[idx]
                self._apply_layer_order(items, "Bring Forward")

    def send_backward(self, item: Optional[CanvasItem] = None) -> None:
        """Move layer one step backward (behind the element immediately below it)."""
        item = item or self.get_selected_item()
        if not item:
            return
        items = self._get_sorted_canvas_items()
        if item in items:
            idx = items.index(item)
            if idx > 0:
                items[idx], items[idx - 1] = items[idx - 1], items[idx]
                self._apply_layer_order(items, "Send Backward")

    def send_to_back(self, item: Optional[CanvasItem] = None) -> None:
        """Move layer back to the bottom behind every other element on the canvas."""
        item = item or self.get_selected_item()
        if not item:
            return
        items = self._get_sorted_canvas_items()
        if item in items:
            items.remove(item)
            items.insert(0, item)
            self._apply_layer_order(items, "Send to Back")

    def delete_selected(self) -> None:
        """Delete selected elements from scene and template with undo support."""
        selected = [it for it in self.selectedItems() if isinstance(it, CanvasItem)]
        if not selected:
            return
        from id_card_generator.editor.undo_manager import DeleteElementsCommand
        self.undo_stack.push(DeleteElementsCommand(self, selected))

    def duplicate_selected(self) -> None:
        """Duplicate selected elements with undo support."""
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
        self.add_element(new_elem, push_undo=True)

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

        # Safe area indicator (calculated from safe_area_margin_mm or default 20px)
        if self.show_safe_area:
            margin_mm = getattr(self.template, "safe_area_margin_mm", 3.0) or 3.0
            dpi = getattr(self.template, "dpi", 300) or 300
            margin_px = int(margin_mm / 25.4 * dpi)
            safe_rect = scene_rect.adjusted(margin_px, margin_px, -margin_px, -margin_px)
            safe_pen = QPen(QColor(59, 130, 246, 120), 1.0, Qt.DashLine)
            painter.setPen(safe_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(safe_rect)

        # Optional card border
        if getattr(self.template, "border_width", 0) > 0 and getattr(self.template, "border_color", None) and self.template.border_color != "transparent":
            bw = self.template.border_width
            b_col = QColor(self.template.border_color)
            painter.setPen(QPen(b_col, float(bw)))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(scene_rect.adjusted(bw / 2.0, bw / 2.0, -bw / 2.0, -bw / 2.0))

        # Outer card boundary shadow outline
        painter.setPen(QPen(QColor(148, 163, 184), 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(scene_rect)

        painter.restore()

    def mousePressEvent(self, event):
        self._mouse_press_positions = {
            it: QPointF(it.pos()) for it in self.selectedItems() if isinstance(it, CanvasItem)
        }
        super().mousePressEvent(event)
        for it in self.selectedItems():
            if isinstance(it, CanvasItem) and it not in self._mouse_press_positions:
                self._mouse_press_positions[it] = QPointF(it.pos())

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if hasattr(self, "_mouse_press_positions") and self._mouse_press_positions:
            moved = []
            for it, old_pos in self._mouse_press_positions.items():
                if it.scene() == self and (it.pos().x() != old_pos.x() or it.pos().y() != old_pos.y()):
                    moved.append((it, old_pos, QPointF(it.pos())))
            self._mouse_press_positions = {}
            if moved:
                from id_card_generator.editor.undo_manager import (
                    MoveElementCommand,
                    MoveMultipleElementsCommand,
                )
                if len(moved) == 1:
                    it, old_p, new_p = moved[0]
                    self.undo_stack.push(MoveElementCommand(it, old_p, new_p))
                else:
                    self.undo_stack.push(MoveMultipleElementsCommand(moved))

    def keyPressEvent(self, event: QKeyEvent):
        """Keyboard navigation: nudge with arrows, delete with Del/Backspace, undo/redo shortcuts."""
        is_ctrl_or_cmd = bool(event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier))
        if is_ctrl_or_cmd:
            if event.key() == Qt.Key_Z:
                if event.modifiers() & Qt.ShiftModifier:
                    self.redo()
                else:
                    self.undo()
                event.accept()
                return
            elif event.key() == Qt.Key_Y:
                self.redo()
                event.accept()
                return

        item = self.get_selected_item()
        if not item or item.element.locked:
            super().keyPressEvent(event)
            return

        step = 10.0 if (event.modifiers() & Qt.ShiftModifier) else 1.0

        if event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            old_pos = QPointF(item.pos())
            if event.key() == Qt.Key_Left:
                new_pos = QPointF(old_pos.x() - step, old_pos.y())
            elif event.key() == Qt.Key_Right:
                new_pos = QPointF(old_pos.x() + step, old_pos.y())
            elif event.key() == Qt.Key_Up:
                new_pos = QPointF(old_pos.x(), old_pos.y() - step)
            else:
                new_pos = QPointF(old_pos.x(), old_pos.y() + step)

            item.setPos(new_pos)
            item.update_model_position()
            from id_card_generator.editor.undo_manager import MoveElementCommand
            self.undo_stack.push(MoveElementCommand(item, old_pos, new_pos, "Nudge Element"))
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
