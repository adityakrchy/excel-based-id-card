"""Alignment, distribution, and centering tools for canvas elements."""

from typing import List
from id_card_generator.editor.canvas_items import CanvasItem


class AlignmentTools:
    """Provides coordinate alignment and distribution routines."""

    @staticmethod
    def align_left(items: List[CanvasItem]) -> None:
        if len(items) < 2:
            return
        min_x = min(item.pos().x() for item in items)
        for item in items:
            item.setPos(min_x, item.pos().y())
            item.update_model_position()

    @staticmethod
    def align_right(items: List[CanvasItem]) -> None:
        if len(items) < 2:
            return
        max_right = max(item.pos().x() + item.element.width for item in items)
        for item in items:
            new_x = max_right - item.element.width
            item.setPos(new_x, item.pos().y())
            item.update_model_position()

    @staticmethod
    def align_top(items: List[CanvasItem]) -> None:
        if len(items) < 2:
            return
        min_y = min(item.pos().y() for item in items)
        for item in items:
            item.setPos(item.pos().x(), min_y)
            item.update_model_position()

    @staticmethod
    def align_bottom(items: List[CanvasItem]) -> None:
        if len(items) < 2:
            return
        max_bottom = max(item.pos().y() + item.element.height for item in items)
        for item in items:
            new_y = max_bottom - item.element.height
            item.setPos(item.pos().x(), new_y)
            item.update_model_position()

    @staticmethod
    def center_horizontally_on_card(items: List[CanvasItem], card_width: float) -> None:
        for item in items:
            new_x = max(0.0, (card_width - item.element.width) / 2.0)
            item.setPos(new_x, item.pos().y())
            item.update_model_position()

    @staticmethod
    def center_vertically_on_card(items: List[CanvasItem], card_height: float) -> None:
        for item in items:
            new_y = max(0.0, (card_height - item.element.height) / 2.0)
            item.setPos(item.pos().x(), new_y)
            item.update_model_position()

    @staticmethod
    def distribute_horizontally(items: List[CanvasItem]) -> None:
        if len(items) < 3:
            return
        sorted_items = sorted(items, key=lambda it: it.pos().x())
        start_x = sorted_items[0].pos().x()
        end_x = sorted_items[-1].pos().x() + sorted_items[-1].element.width
        total_items_w = sum(it.element.width for it in sorted_items)
        available_space = end_x - start_x - total_items_w
        gap = available_space / (len(sorted_items) - 1)

        curr_x = start_x
        for it in sorted_items:
            it.setPos(curr_x, it.pos().y())
            it.update_model_position()
            curr_x += it.element.width + gap

    @staticmethod
    def distribute_vertically(items: List[CanvasItem]) -> None:
        if len(items) < 3:
            return
        sorted_items = sorted(items, key=lambda it: it.pos().y())
        start_y = sorted_items[0].pos().y()
        end_y = sorted_items[-1].pos().y() + sorted_items[-1].element.height
        total_items_h = sum(it.element.height for it in sorted_items)
        available_space = end_y - start_y - total_items_h
        gap = available_space / (len(sorted_items) - 1)

        curr_y = start_y
        for it in sorted_items:
            it.setPos(it.pos().x(), curr_y)
            it.update_model_position()
            curr_y += it.element.height + gap
