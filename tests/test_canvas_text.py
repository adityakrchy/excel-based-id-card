"""Tests for the text elements on the canvas.

The text of an element has a size of its own.  It used to shrink while the
frame of the element was resized, which changed the design behind the back
of the user, and the text of a new element did not fit into its frame.
"""

import pytest
from PySide6.QtCore import QRectF

from id_card_generator.core.models import CanvasElement, TemplateDefinition
from id_card_generator.editor.canvas_items import (
    CanvasItem,
    measure_text_size,
    resolve_text_font,
)


def _text_element(width: float = 320.0, height: float = 48.0) -> CanvasElement:
    """A static text element."""
    return CanvasElement(
        name="Static Label",
        type="static_text",
        x=60.0,
        y=60.0,
        width=width,
        height=height,
        static_content="Sample Text",
    )


# ---------------------------------------------------------------------------
# The font
# ---------------------------------------------------------------------------
def test_the_font_keeps_the_size_of_the_element():
    """The font is built from the size of the element."""
    element = _text_element()
    font = resolve_text_font(element, "Sample Text", 300)

    # 10 points at 300 DPI are 41.67 pixels.
    assert font.pixelSize() == 42


def test_resizing_the_frame_does_not_change_the_font(qtbot):
    """Dragging a handle never scales the text."""
    item = CanvasItem(_text_element())

    before = resolve_text_font(item.element, "Sample Text", 300).pixelSize()

    item.set_rect(QRectF(0, 0, 120, 20))

    after = resolve_text_font(item.element, "Sample Text", 300).pixelSize()
    assert after == before
    assert item.element.style.font_size == 10.0


def test_the_text_is_measured_at_its_own_size():
    """The natural size of a text is the size of its font."""
    element = _text_element()
    width, height = measure_text_size(element, "Sample Text", 300)

    assert width > 0
    assert height > 0
    # A line of text is never wider than the box it was measured for.
    assert height < 80


# ---------------------------------------------------------------------------
# The frame
# ---------------------------------------------------------------------------
def test_a_new_text_element_gets_a_frame_that_fits(qtbot):
    """The frame of a new text is as big as its text."""
    from id_card_generator.ui.editor_page import EditorPage

    page = EditorPage()
    qtbot.addWidget(page)

    page.scene.template = TemplateDefinition(name="CR80", width_px=1012, height_px=638, dpi=300)
    page._add_static_text()

    items = [
        item
        for item in page.scene.items()
        if hasattr(item, "element") and item.element.type == "static_text"
    ]
    assert items, "the text element was not added"

    item = items[0]
    width, height = measure_text_size(item.element, "Sample Text", 300)

    assert item.element.width >= width
    assert item.element.height >= height


def test_a_text_that_does_not_fit_is_marked(qtbot):
    """A frame that is too small is marked, so the cut text is noticed."""
    from id_card_generator.editor.canvas_scene import CanvasScene

    scene = CanvasScene()
    scene.template = TemplateDefinition(name="CR80", width_px=1012, height_px=638, dpi=300)

    item = CanvasItem(_text_element(width=320.0, height=48.0))
    scene.addItem(item)

    assert item.text_overflows() is False

    item.set_rect(QRectF(0, 0, 60, 20))
    assert item.text_overflows() is True
