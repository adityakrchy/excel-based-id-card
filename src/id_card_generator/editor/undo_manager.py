"""Undo/Redo command stack for canvas manipulations."""

from typing import Any, Callable
from PySide6.QtGui import QUndoCommand, QUndoStack
from PySide6.QtCore import QPointF, QRectF


class MoveElementCommand(QUndoCommand):
    """Command for element translation."""
    def __init__(self, item, old_pos: QPointF, new_pos: QPointF, text: str = "Move Element"):
        super().__init__(text)
        self.item = item
        self.old_pos = old_pos
        self.new_pos = new_pos

    def undo(self):
        self.item.setPos(self.old_pos)
        self.item.update_model_position()

    def redo(self):
        self.item.setPos(self.new_pos)
        self.item.update_model_position()


class ResizeElementCommand(QUndoCommand):
    """Command for element geometry resize."""
    def __init__(self, item, old_rect: QRectF, new_rect: QRectF, text: str = "Resize Element"):
        super().__init__(text)
        self.item = item
        self.old_rect = old_rect
        self.new_rect = new_rect

    def undo(self):
        self.item.set_rect(self.old_rect)

    def redo(self):
        self.item.set_rect(self.new_rect)


class ChangePropertyCommand(QUndoCommand):
    """Generic command for updating a style or attribute."""
    def __init__(self, item, apply_fn: Callable[[Any], None], old_val: Any, new_val: Any, text: str = "Change Property"):
        super().__init__(text)
        self.item = item
        self.apply_fn = apply_fn
        self.old_val = old_val
        self.new_val = new_val

    def undo(self):
        self.apply_fn(self.old_val)

    def redo(self):
        self.apply_fn(self.new_val)
