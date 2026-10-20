"""QGraphicsScene managing the card canvas, background, grid snapping, and items."""

import logging
from typing import Dict, List, Optional, Set
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
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
from id_card_generator.editor.smart_alignment import (
    GuideLine,
    GuideRenderer,
    SmartAlignmentEngine,
    SnapSettings,
    SpacingBadge,
)

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

        # Smart Alignment and Snapping Subsystem
        self._snap_settings = SnapSettings(unit="mm", dpi=300)
        self.smart_alignment_engine = SmartAlignmentEngine(self._snap_settings)
        self._active_guides: List[GuideLine] = []
        self._active_spacing_badges: List[SpacingBadge] = []
        self._in_smart_drag: bool = False
        self._nudge_timer: Optional[QTimer] = None

        self.show_grid = True
        self.show_safe_area = True

        self._sample_record: Optional[SourceRecord] = None
        self._sample_photo_path: Optional[str] = None
        self._background_pixmap: Optional[QPixmap] = None

        self.selectionChanged.connect(self._on_selection_changed)

    @property
    def snap_settings(self) -> SnapSettings:
        return self._snap_settings

    @property
    def snap_to_grid(self) -> bool:
        return self._snap_settings.snap_to_grid_enabled

    @snap_to_grid.setter
    def snap_to_grid(self, val: bool) -> None:
        self._snap_settings.snap_to_grid_enabled = val

    @property
    def grid_size(self) -> float:
        return self._snap_settings.grid_size

    @grid_size.setter
    def grid_size(self, val: float) -> None:
        self._snap_settings.grid_size = val

    def set_active_guides(self, guides: List[GuideLine], spacing_badges: List[SpacingBadge]) -> None:
        """Update active smart alignment and spacing guides for overlay rendering."""
        self._active_guides = guides
        self._active_spacing_badges = spacing_badges

    def clear_guides(self) -> None:
        """Clear all active smart guide lines and spacing indicators."""
        self._active_guides = []
        self._active_spacing_badges = []

    def get_reference_targets(self, exclude_items: Optional[Set[CanvasItem]] = None) -> List[QRectF]:
        """Return scene bounding rectangles of all visible canvas elements excluding specified items.
        
        Locked elements are included as alignment references, but cannot be dragged.
        Hidden elements are excluded.
        """
        exclude = exclude_items or set()
        targets = []
        for it in self.items():
            if isinstance(it, CanvasItem) and it not in exclude:
                if it.element.visible:
                    targets.append(it.scene_element_rect())
        return targets

    def get_zoom_factor(self) -> float:
        """Return current view zoom factor for screen-space threshold conversion."""
        views = self.views()
        if views:
            v = views[0]
            if hasattr(v, "_zoom_factor"):
                return float(v._zoom_factor)
            return float(v.transform().m11())
        return 1.0

    def set_smart_guides_enabled(self, enabled: bool) -> None:
        self._snap_settings.smart_guides_enabled = enabled
        if not enabled:
            self.clear_guides()
            self.update()

    def set_object_snapping_enabled(self, enabled: bool) -> None:
        self._snap_settings.object_snapping_enabled = enabled
        if not enabled:
            self.clear_guides()
            self.update()

    def set_smart_spacing_enabled(self, enabled: bool) -> None:
        self._snap_settings.smart_spacing_enabled = enabled

    def set_snap_to_canvas_enabled(self, enabled: bool) -> None:
        self._snap_settings.snap_to_canvas_enabled = enabled

    def set_snap_to_grid_enabled(self, enabled: bool) -> None:
        self._snap_settings.snap_to_grid_enabled = enabled

    def set_snap_threshold(self, threshold_screen: float) -> None:
        self._snap_settings.snap_threshold_screen = threshold_screen

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """Render temporary smart guides and spacing indicators on top of all canvas items."""
        super().drawForeground(painter, rect)
        if self._active_guides or self._active_spacing_badges:
            zoom = self.get_zoom_factor()
            GuideRenderer.render(painter, self._active_guides, self._active_spacing_badges, zoom)

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
        if template:
            self._snap_settings.unit = getattr(template, "unit", "mm") or "mm"
            self._snap_settings.dpi = getattr(template, "dpi", 300) or 300
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

    def get_current_template_definition(self) -> Optional[TemplateDefinition]:
        """Return a fresh TemplateDefinition reflecting current canvas items and properties."""
        if not self.template:
            return None
        tmpl = self.template.model_copy(deep=True)
        items = self._get_sorted_canvas_items()
        tmpl.elements = [it.element.model_copy(deep=True) for it in items]
        return tmpl

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
        self.fit_text_elements_to_content()
        self.update()

    def fit_text_elements_to_content(self) -> None:
        """Grow text elements whose box is too small for their content.

        Text must never disappear behind its own bounding box, so whenever the
        rendered content needs more room (longer value, bigger font, ...) the
        box grows.  Boxes are never shrunk automatically.
        """
        if getattr(self, "_in_fit_text_elements", False):
            return
        self._in_fit_text_elements = True
        try:
            changed = False
            for item in self._items_by_id.values():
                if item.grow_to_fit_content():
                    changed = True
            if changed:
                self.update()
        finally:
            self._in_fit_text_elements = False

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

    def mousePressEvent(self, event):
        if event.modifiers() & (Qt.ShiftModifier | Qt.MetaModifier):
            event.setModifiers(event.modifiers() | Qt.ControlModifier)
        self._mouse_press_positions = {
            it: QPointF(it.pos()) for it in self.selectedItems() if isinstance(it, CanvasItem)
        }
        super().mousePressEvent(event)
        for it in self.selectedItems():
            if isinstance(it, CanvasItem) and it not in self._mouse_press_positions:
                self._mouse_press_positions[it] = QPointF(it.pos())

    def mouseReleaseEvent(self, event):
        if event.modifiers() & (Qt.ShiftModifier | Qt.MetaModifier):
            event.setModifiers(event.modifiers() | Qt.ControlModifier)
        self.clear_guides()
        self._in_smart_drag = False
        self.update()
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

    def _start_nudge_guide_timer(self, msec: int = 700) -> None:
        """Start a one-shot timer to clear temporary guide lines after keyboard nudge."""
        if self._nudge_timer is not None:
            self._nudge_timer.stop()
        else:
            self._nudge_timer = QTimer(self)
            self._nudge_timer.setSingleShot(True)
            self._nudge_timer.timeout.connect(self._clear_nudge_guides)
        self._nudge_timer.start(msec)

    def _clear_nudge_guides(self) -> None:
        self.clear_guides()
        self.update()

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

        selected_items = [it for it in self.selectedItems() if isinstance(it, CanvasItem) and not it.element.locked]
        if not selected_items:
            super().keyPressEvent(event)
            return

        step = 10.0 if (event.modifiers() & Qt.ShiftModifier) else 1.0

        if event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            dx, dy = 0.0, 0.0
            if event.key() == Qt.Key_Left:
                dx = -step
            elif event.key() == Qt.Key_Right:
                dx = step
            elif event.key() == Qt.Key_Up:
                dy = -step
            elif event.key() == Qt.Key_Down:
                dy = step

            # Calculate collective bounding box of all moving items
            lefts = [it.pos().x() + it._rect.x() for it in selected_items]
            rights = [it.pos().x() + it._rect.x() + it._rect.width() for it in selected_items]
            tops = [it.pos().y() + it._rect.y() for it in selected_items]
            bottoms = [it.pos().y() + it._rect.y() + it._rect.height() for it in selected_items]

            group_rect = QRectF(min(lefts), min(tops), max(rights) - min(lefts), max(bottoms) - min(tops))
            proposed_rect = group_rect.translated(dx, dy)

            # In professional tools like Figma and Photoshop, arrow-key nudging moves strictly
            # by the nudge step (1px normal, 10px with Shift) so precision placement is never
            # neutralized or trapped by magnetic snapping suction.
            final_dx = dx
            final_dy = dy

            # If smart guides are enabled, flash alignment guides only when the position lands
            # directly on an alignment guide line (within 0.5px tolerance)
            if self._snap_settings.smart_guides_enabled and not (event.modifiers() & Qt.AltModifier):
                targets = self.get_reference_targets(exclude_items=set(selected_items))
                align_check = self.smart_alignment_engine.snap_move(
                    moving_rect=proposed_rect,
                    targets=targets,
                    canvas_rect=self.sceneRect(),
                    zoom_factor=self.get_zoom_factor(),
                    bypass_snap=False,
                )
                if abs(align_check.delta_x) <= 0.5 and abs(align_check.delta_y) <= 0.5 and (align_check.guides or align_check.spacing_badges):
                    self.set_active_guides(align_check.guides, align_check.spacing_badges)
                    self.update()
                    self._start_nudge_guide_timer(600)
                else:
                    self.clear_guides()
            else:
                self.clear_guides()

            moves = []
            for it in selected_items:
                old_p = QPointF(it.pos())
                new_p = QPointF(old_p.x() + final_dx, old_p.y() + final_dy)
                it.setPos(new_p)
                it.update_model_position()
                moves.append((it, old_p, new_p))

            from id_card_generator.editor.undo_manager import (
                MoveElementCommand,
                MoveMultipleElementsCommand,
            )
            if len(moves) == 1:
                it, old_p, new_p = moves[0]
                self.undo_stack.push(MoveElementCommand(it, old_p, new_p, "Nudge Element"))
            elif len(moves) > 1:
                self.undo_stack.push(MoveMultipleElementsCommand(moves, "Nudge Elements"))

            self.template_modified.emit()
            event.accept()
            return
        elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
            event.accept()
            return
        else:
            super().keyPressEvent(event)

    def _on_selection_changed(self):
        self.clear_guides()
        self.update()
        item = self.get_selected_item()
        self.element_selected.emit(item)

    def _on_item_geometry_changed(self, item: CanvasItem):
        # Snap to grid if active and not in an interactive smart drag session
        if not getattr(self, "_in_smart_drag", False) and self.snap_to_grid and self.grid_size > 0:
            gs = self.grid_size
            snapped_x = round(item.pos().x() / gs) * gs
            snapped_y = round(item.pos().y() / gs) * gs
            item.setPos(snapped_x, snapped_y)
            item.element.x = snapped_x
            item.element.y = snapped_y

        self.template_modified.emit()
