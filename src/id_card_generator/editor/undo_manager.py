"""Undo/Redo command stack for canvas manipulations."""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QUndoCommand, QUndoStack

from id_card_generator.core.models import CanvasElement

logger = logging.getLogger(__name__)


class MoveElementCommand(QUndoCommand):
    """Command for translating a single canvas item."""

    def __init__(self, item, old_pos: QPointF, new_pos: QPointF, text: str = "Move Element"):
        super().__init__(text)
        self.item = item
        self.old_pos = QPointF(old_pos)
        self.new_pos = QPointF(new_pos)
        self._applied = True

    def id(self) -> int:
        return 1001

    def mergeWith(self, other: QUndoCommand) -> bool:
        if isinstance(other, MoveElementCommand) and other.item == self.item:
            self.new_pos = other.new_pos
            return True
        return False

    def undo(self):
        self.item.setPos(self.old_pos)
        self.item.update_model_position()
        if self.item.scene():
            self.item.scene().update()
            self.item.scene().template_modified.emit()

    def redo(self):
        if not self._applied:
            self.item.setPos(self.new_pos)
            self.item.update_model_position()
            if self.item.scene():
                self.item.scene().update()
                self.item.scene().template_modified.emit()
        self._applied = False


class MoveMultipleElementsCommand(QUndoCommand):
    """Command for translating multiple canvas items simultaneously."""

    def __init__(self, moves: List[Tuple[Any, QPointF, QPointF]], text: str = "Move Elements"):
        super().__init__(text)
        self.moves = [(item, QPointF(op), QPointF(np)) for item, op, np in moves]
        self._applied = True

    def undo(self):
        scene = None
        for item, old_pos, _ in self.moves:
            item.setPos(old_pos)
            item.update_model_position()
            scene = item.scene() or scene
        if scene:
            scene.update()
            scene.template_modified.emit()

    def redo(self):
        if not self._applied:
            scene = None
            for item, _, new_pos in self.moves:
                item.setPos(new_pos)
                item.update_model_position()
                scene = item.scene() or scene
            if scene:
                scene.update()
                scene.template_modified.emit()
        self._applied = False


class ResizeElementCommand(QUndoCommand):
    """Command for element geometry resize."""

    def __init__(self, item, old_rect: QRectF, new_rect: QRectF, text: str = "Resize Element"):
        super().__init__(text)
        self.item = item
        self.old_rect = QRectF(old_rect)
        self.new_rect = QRectF(new_rect)
        self._applied = True

    def undo(self):
        self.item.set_rect(self.old_rect)
        if self.item.scene():
            self.item.scene().update()
            self.item.scene().template_modified.emit()

    def redo(self):
        if not self._applied:
            self.item.set_rect(self.new_rect)
            if self.item.scene():
                self.item.scene().update()
                self.item.scene().template_modified.emit()
        self._applied = False


class AddElementCommand(QUndoCommand):
    """Command for adding an element to template and scene."""

    def __init__(self, scene, element: CanvasElement, text: str = "Add Element"):
        super().__init__(text)
        self.scene = scene
        self.element = element

    def redo(self):
        # Calculate maximum existing z-index so new element is always on top of all canvas elements
        existing_z = [it.element.z_index for it in self.scene._items_by_id.values() if it.element.id != self.element.id]
        if existing_z:
            max_z = max(existing_z)
            if self.element.z_index <= max_z:
                self.element.z_index = max_z + 1
        else:
            if self.element.z_index <= 0:
                self.element.z_index = 1

        if self.scene.template and self.element not in self.scene.template.elements:
            self.scene.template.elements.append(self.element)
        item = self.scene._items_by_id.get(self.element.id)
        if not item:
            item = self.scene._create_and_add_item(self.element)
        else:
            if item.scene() != self.scene:
                self.scene.addItem(item)
            item.setZValue(self.element.z_index)
        self.scene.clearSelection()
        item.setSelected(True)
        item.update()
        self.scene.update()
        self.scene.element_selected.emit(item)
        self.scene.template_modified.emit()

    def undo(self):
        item = self.scene._items_by_id.get(self.element.id)
        if item:
            self.scene.removeItem(item)
            if self.element.id in self.scene._items_by_id:
                del self.scene._items_by_id[self.element.id]
        if self.scene.template and self.element in self.scene.template.elements:
            self.scene.template.elements.remove(self.element)
        self.scene.clearSelection()
        self.scene.update()
        self.scene.element_selected.emit(None)
        self.scene.template_modified.emit()


class DeleteElementsCommand(QUndoCommand):
    """Command for removing one or more elements from scene and template."""

    def __init__(self, scene, items_or_elements: list, text: str = "Delete Element(s)"):
        super().__init__(text)
        self.scene = scene
        self.elements: List[CanvasElement] = [
            it.element if hasattr(it, "element") else it for it in items_or_elements
        ]

    def redo(self):
        for elem in self.elements:
            item = self.scene._items_by_id.get(elem.id)
            if item:
                self.scene.removeItem(item)
                if elem.id in self.scene._items_by_id:
                    del self.scene._items_by_id[elem.id]
            if self.scene.template and elem in self.scene.template.elements:
                self.scene.template.elements.remove(elem)
        self.scene.clearSelection()
        self.scene.update()
        self.scene.template_modified.emit()

    def undo(self):
        for elem in self.elements:
            if self.scene.template and elem not in self.scene.template.elements:
                self.scene.template.elements.append(elem)
            if elem.id not in self.scene._items_by_id:
                self.scene._create_and_add_item(elem)
        self.scene.clearSelection()
        for elem in self.elements:
            it = self.scene._items_by_id.get(elem.id)
            if it:
                it.setSelected(True)
        self.scene.update()
        self.scene.template_modified.emit()


class ChangeElementStateCommand(QUndoCommand):
    """Command for updating a canvas element's full property/style dictionary."""

    def __init__(
        self,
        scene,
        element_id: str,
        old_state: Dict[str, Any],
        new_state: Dict[str, Any],
        text: str = "Change Property",
    ):
        super().__init__(text)
        self.scene = scene
        self.element_id = element_id
        self.old_state = old_state
        self.new_state = new_state
        self._applied = True

    def id(self) -> int:
        return abs(hash(self.element_id)) % 1000000 + 2000

    def mergeWith(self, other: QUndoCommand) -> bool:
        if isinstance(other, ChangeElementStateCommand) and other.element_id == self.element_id:
            self.new_state = other.new_state
            return True
        return False

    def undo(self):
        self._apply_state(self.old_state)

    def redo(self):
        if not self._applied:
            self._apply_state(self.new_state)
        self._applied = False

    def _apply_state(self, state: Dict[str, Any]):
        item = self.scene._items_by_id.get(self.element_id)
        if not item:
            return
        new_elem = CanvasElement.model_validate(state)
        item.element.__dict__.update(new_elem.__dict__)
        item.prepareGeometryChange()
        item._rect = QRectF(0, 0, item.element.width, item.element.height)
        item.setPos(item.element.x, item.element.y)
        item.setZValue(item.element.z_index)
        item.setVisible(item.element.visible)
        item.update()
        self.scene.update()
        self.scene.template_modified.emit()


class BatchStateChangeCommand(QUndoCommand):
    """Command for batch property changes across multiple elements."""

    def __init__(
        self,
        scene,
        changes: List[Tuple[str, Dict[str, Any], Dict[str, Any]]],
        text: str = "Change Properties",
    ):
        super().__init__(text)
        self.scene = scene
        # list of (element_id, old_state, new_state)
        self.changes = changes
        self._applied = True

    def undo(self):
        for eid, old_state, _ in self.changes:
            item = self.scene._items_by_id.get(eid)
            if item:
                new_elem = CanvasElement.model_validate(old_state)
                item.element.__dict__.update(new_elem.__dict__)
                item.prepareGeometryChange()
                item._rect = QRectF(0, 0, item.element.width, item.element.height)
                item.setPos(item.element.x, item.element.y)
                item.setZValue(item.element.z_index)
                item.setVisible(item.element.visible)
                item.update()
        self.scene.update()
        self.scene.template_modified.emit()

    def redo(self):
        if not self._applied:
            for eid, _, new_state in self.changes:
                item = self.scene._items_by_id.get(eid)
                if item:
                    new_elem = CanvasElement.model_validate(new_state)
                    item.element.__dict__.update(new_elem.__dict__)
                    item.prepareGeometryChange()
                    item._rect = QRectF(0, 0, item.element.width, item.element.height)
                    item.setPos(item.element.x, item.element.y)
                    item.setZValue(item.element.z_index)
                    item.setVisible(item.element.visible)
                    item.update()
            self.scene.update()
            self.scene.template_modified.emit()
        self._applied = False


class ChangeZOrderCommand(QUndoCommand):
    """Command for changing layer z-order."""

    def __init__(self, item, old_z: int, new_z: int, text: str = "Reorder Layer"):
        super().__init__(text)
        self.item = item
        self.old_z = old_z
        self.new_z = new_z
        self._applied = True

    def undo(self):
        self.item.setZValue(self.old_z)
        self.item.element.z_index = self.old_z
        if self.item.scene():
            self.item.scene().update()
            self.item.scene().template_modified.emit()

    def redo(self):
        if not self._applied:
            self.item.setZValue(self.new_z)
            self.item.element.z_index = self.new_z
            if self.item.scene():
                self.item.scene().update()
                self.item.scene().template_modified.emit()
        self._applied = False


class ChangePropertyCommand(QUndoCommand):
    """Generic command for updating a style or attribute via callable."""

    def __init__(
        self,
        item,
        apply_fn: Callable[[Any], None],
        old_val: Any,
        new_val: Any,
        text: str = "Change Property",
    ):
        super().__init__(text)
        self.item = item
        self.apply_fn = apply_fn
        self.old_val = old_val
        self.new_val = new_val
        self._applied = True

    def undo(self):
        self.apply_fn(self.old_val)
        if self.item.scene():
            self.item.scene().update()
            self.item.scene().template_modified.emit()

    def redo(self):
        if not self._applied:
            self.apply_fn(self.new_val)
            if self.item.scene():
                self.item.scene().update()
                self.item.scene().template_modified.emit()
        self._applied = False


class ReorderLayersCommand(QUndoCommand):
    """Command for updating z-order across all elements."""

    def __init__(
        self,
        scene,
        old_z_map: Dict[str, int],
        new_z_map: Dict[str, int],
        text: str = "Reorder Layers",
    ):
        super().__init__(text)
        self.scene = scene
        self.old_z_map = old_z_map
        self.new_z_map = new_z_map
        self._applied = True

    def undo(self):
        for eid, z in self.old_z_map.items():
            it = self.scene._items_by_id.get(eid)
            if it:
                it.setZValue(z)
                it.element.z_index = z
        self.scene.update()
        self.scene.template_modified.emit()

    def redo(self):
        if not self._applied:
            for eid, z in self.new_z_map.items():
                it = self.scene._items_by_id.get(eid)
                if it:
                    it.setZValue(z)
                    it.element.z_index = z
            self.scene.update()
            self.scene.template_modified.emit()
        self._applied = False
