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


def test_the_frame_never_gets_smaller_than_the_text(qtbot):
    """Dragging a handle can not shrink the frame below its text."""
    item = CanvasItem(_text_element())
    width, height = measure_text_size(item.element, "Sample Text", 300)

    item.set_rect(QRectF(0, 0, 40, 20))

    assert item._rect.width() >= width
    assert item._rect.height() >= height
    assert item.text_overflows() is False


def test_the_anchor_of_the_handle_stays_where_it_is(qtbot):
    """The edge that does not move stays where it is."""
    item = CanvasItem(_text_element())
    min_width, min_height = item._minimum_size()

    # The bottom right handle is dragged to the top left: the top left
    # corner of the frame stays where it was.
    item.set_rect(QRectF(0, 0, 40, 20))

    assert item._rect.left() == 0
    assert item._rect.top() == 0
    assert item._rect.width() == pytest.approx(min_width)
    assert item._rect.height() == pytest.approx(min_height)


def test_a_text_that_does_not_fit_is_marked(qtbot):
    """A text that is bigger than its frame is marked."""
    from id_card_generator.editor.canvas_scene import CanvasScene

    scene = CanvasScene()
    scene.template = TemplateDefinition(name="CR80", width_px=1012, height_px=638, dpi=300)

    item = CanvasItem(_text_element(width=320.0, height=48.0))
    scene.addItem(item)

    assert item.text_overflows() is False

    # A longer text does not fit into the frame any more.
    item.element.static_content = "A much longer text that does not fit"
    assert item.text_overflows() is True


def test_the_text_is_drawn_in_full(qtbot):
    """A text that is bigger than its frame is not cut away.

    drawText clips into the rectangle it is given, so the rectangle has to
    grow with the text - otherwise the text would disappear behind the
    frame of the element.
    """
    from PySide6.QtGui import QColor, QImage, QPainter

    item = CanvasItem(_text_element(width=80.0, height=24.0))

    image = QImage(400, 120, QImage.Format_ARGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    item.paint(painter, None, None)
    painter.end()

    # The text reaches beyond the right edge of the frame.
    ink = [
        x
        for x in range(81, 380)
        if any(image.pixelColor(x, y).black() < 200 for y in range(120))
    ]
    assert ink, "the text was cut away by the frame"


# ---------------------------------------------------------------------------
# The inline editor
# ---------------------------------------------------------------------------
@pytest.fixture
def designer(qtbot):
    """A designer with a static text on the canvas."""
    from id_card_generator.ui.editor_page import EditorPage
    from id_card_generator.ui.theme_manager import ThemeManager

    ThemeManager.instance().set_theme("black")

    page = EditorPage()
    qtbot.addWidget(page)
    page.resize(1400, 900)
    page.show()
    qtbot.wait(50)

    page._add_static_text()
    qtbot.wait(50)

    return page


def _static_item(page):
    """The static text of the canvas."""
    return next(
        it
        for it in page.scene.items()
        if hasattr(it, "element") and it.element.type == "static_text"
    )


def test_a_double_click_opens_the_inline_editor(designer, qtbot):
    """A double click on a text lets the user write it in place."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    item = _static_item(designer)
    item.setSelected(True)
    qtbot.wait(20)

    view = designer.view
    scene_pos = item.mapToScene(QPointF(item._rect.center()))
    view_pos = view.mapFromScene(scene_pos)

    QTest.mouseDClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, view_pos)
    qtbot.wait(50)

    assert designer._text_editor is not None
    assert designer._text_editor.toPlainText() == "Sample Text"
    # The whole text is selected, so typing replaces it.
    assert designer._text_editor.textCursor().hasSelection()


def test_the_inline_editor_writes_the_text_back(designer, qtbot):
    """What is typed becomes the text of the element."""
    item = _static_item(designer)

    designer._begin_text_edit(item)
    assert designer._text_editor is not None

    designer._text_editor.setPlainText("Card Holder")
    designer._close_text_editor(commit=True)
    qtbot.wait(20)

    assert item.element.static_content == "Card Holder"
    assert designer._text_editor is None
    # The frame grew with the text.
    assert item.element.width > 0


def test_escape_cancels_the_inline_editor(designer, qtbot):
    """Escape leaves the text of the element alone."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    item = _static_item(designer)
    designer._begin_text_edit(item)
    designer._text_editor.setPlainText("Something else")

    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    designer.eventFilter(designer._text_editor, event)

    assert designer._text_editor is None
    assert item.element.static_content == "Sample Text"


def test_the_inline_editor_keeps_the_size_of_the_font(designer, qtbot):
    """The text is edited in the size of the element, not in a small font."""
    from id_card_generator.core.geometry import points_to_document_pixels

    item = _static_item(designer)
    designer._begin_text_edit(item)

    editor = designer._text_editor
    zoom = designer.view.transform().m11()
    expected = round(
        points_to_document_pixels(
            float(item.element.style.font_size), designer._document_dpi()
        )
        * zoom
    )

    assert editor.font().pixelSize() == expected
    # The size of the font belongs into the style, a style sheet wins over
    # the font of the widget.
    assert f"font-size: {expected}px" in editor.styleSheet()


def test_the_inline_editor_is_not_black(designer, qtbot):
    """The editor is a light box, so it can be read on the card."""
    item = _static_item(designer)
    designer._begin_text_edit(item)

    assert "background-color: #ffffff" in designer._text_editor.styleSheet()


def test_a_dynamic_field_is_not_edited(designer, qtbot):
    """The text of a dynamic field comes from the spreadsheet."""
    from id_card_generator.core.models import CanvasElement

    element = CanvasElement(
        name="Dynamic Name",
        type="dynamic_text",
        x=60.0,
        y=110.0,
        width=280.0,
        height=40.0,
        binding="Name",
    )
    designer.scene.add_element(element)
    qtbot.wait(20)

    item = next(
        it
        for it in designer.scene.items()
        if getattr(it, "element", None) is element
    )
    designer._begin_text_edit(item)

    assert designer._text_editor is None
    assert "spreadsheet" in designer.notice.text()
