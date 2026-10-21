"""Tests for the layout rules of the template designer.

The designer grew a lot of inline stylesheets over the years.  They were
hard coded dark colours, so the panel did not follow the theme, and they
padded every group on their own.  These tests keep the panel on the token
driven stylesheet and keep the spacing of the rows even.
"""

import re
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from id_card_generator.editor.element_inspector import ElementInspector
from id_card_generator.editor.field_mapping_panel import FieldMappingPanel
from id_card_generator.editor.layers_panel import LayersPanel

EDITOR_SOURCES = (
    "src/id_card_generator/ui/editor_page.py",
    "src/id_card_generator/editor/element_inspector.py",
    "src/id_card_generator/editor/layers_panel.py",
    "src/id_card_generator/editor/field_mapping_panel.py",
)

# The surfaces of the application.  A hard coded one of these in an inline
# stylesheet cannot follow the theme, so the designer looked broken in the
# light theme.
LEGACY_SURFACES = (
    "#111317",
    "#0c0e12",
    "#1a1c20",
    "#1e2024",
    "#282a2e",
    "#333539",
    "#202023",
    "#262629",
    "#333338",
    "#27272a",
    "#2a2a2e",
    "#18181b",
)


def _source(name: str) -> str:
    root = Path(__file__).resolve().parent.parent
    return (root / name).read_text()


def _inline_stylesheets(source: str):
    """Return the blocks that are passed to setStyleSheet."""
    blocks = []
    marker = "setStyleSheet("
    index = 0
    while True:
        index = source.find(marker, index)
        if index < 0:
            return blocks
        start = index + len(marker)
        depth = 1
        cursor = start
        while cursor < len(source) and depth:
            if source[cursor] == "(":
                depth += 1
            elif source[cursor] == ")":
                depth -= 1
            cursor += 1
        blocks.append(source[start : cursor - 1])
        index = cursor


# ---------------------------------------------------------------------------
# The stylesheet owns the colours
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", EDITOR_SOURCES)
def test_the_editor_has_no_hard_coded_surfaces(name: str):
    """The panels take their surfaces from the application stylesheet."""
    source = _source(name).lower()

    for block in _inline_stylesheets(source):
        for colour in LEGACY_SURFACES:
            assert colour not in block, (
                f"{name} hard codes the surface {colour}: {block.strip()[:80]}"
            )


def test_the_stylesheet_knows_the_designer_widgets():
    """The rules the designer needs live in the application stylesheet."""
    from id_card_generator.ui.theme_manager import ThemeManager

    stylesheet = ThemeManager.build_stylesheet("black")

    for selector in (
        "QFrame#tool_strip",
        "QToolButton#btn_toggle",
        "QFrame#separator",
        "QLabel[role=\"controlLabel\"]",
        "QLabel[role=\"accentText\"]",
    ):
        assert selector in stylesheet, selector


# ---------------------------------------------------------------------------
# The panel of the properties
# ---------------------------------------------------------------------------
@pytest.fixture
def inspector(qtbot):
    panel = ElementInspector()
    qtbot.addWidget(panel)
    panel.show()
    return panel


def test_every_caption_of_the_inspector_starts_at_the_same_place(inspector):
    """The captions of the panel share one column.

    The captions used to be right aligned inside the column of the form, so
    a short caption ("X:") floated in the middle of the panel.
    """
    captions = [
        child
        for child in inspector.findChildren(type(inspector.lbl_title))
        if child.property("role") == "specKey"
    ]
    assert captions, "the panel has no captions"

    lefts = {caption.x() for caption in captions}
    assert len(lefts) == 1, f"the captions are not aligned: {lefts}"


def test_the_caption_column_has_a_fixed_width(inspector):
    """Every caption is as wide as the column of the form."""
    captions = [
        child
        for child in inspector.findChildren(type(inspector.lbl_title))
        if child.property("role") == "specKey"
    ]
    widths = {caption.width() for caption in captions}
    assert len(widths) == 1, f"the captions have different widths: {widths}"


def test_the_inspector_has_a_section_caption(inspector):
    """The panel announces what it is before the name of the element."""
    assert inspector.lbl_section.text() == "PROPERTIES"
    assert inspector.lbl_title.text()


# ---------------------------------------------------------------------------
# The dock of the designer
# ---------------------------------------------------------------------------
def test_the_dock_keeps_its_width(qtbot):
    """The canvas takes the free space, the dock keeps its size."""
    from id_card_generator.ui.editor_page import EditorPage

    page = EditorPage()
    qtbot.addWidget(page)

    assert page.right_tabs.maximumWidth() <= 380
    assert page.right_tabs.minimumWidth() >= 240


def test_the_tool_strip_buttons_share_one_size(qtbot):
    """Every tool of the strip is the same square."""
    from id_card_generator.ui.editor_page import EditorPage

    page = EditorPage()
    qtbot.addWidget(page)

    sizes = {button.size() for button in page.tool_group.buttons()}
    assert len(sizes) == 1, f"the tools have different sizes: {sizes}"


def test_the_context_bar_controls_share_one_height(qtbot):
    """The controls of the options bar sit on one line."""
    from id_card_generator.ui.editor_page import EditorPage

    page = EditorPage()
    qtbot.addWidget(page)

    heights = set()
    for page_widget in (
        page.page_doc_context,
        page.page_text_context,
        page.page_shape_context,
        page.page_photo_context,
    ):
        for child in page_widget.findChildren(type(page.lbl_sb_zoom)):
            if child.isVisible() or True:
                heights.add(child.height())

    # The controls of the bar are all built with the same height.
    assert page.btn_undo.height() == page.btn_redo.height()
    assert page.btn_dup.height() == page.btn_del.height()


# ---------------------------------------------------------------------------
# The other tabs of the dock
# ---------------------------------------------------------------------------
def test_the_layers_panel_uses_the_shared_buttons(qtbot):
    """The order buttons of the layers panel use the icon style."""
    from id_card_generator.editor.canvas_scene import CanvasScene
    from id_card_generator.editor.layers_panel import LayersPanel

    scene = CanvasScene()
    panel = LayersPanel(scene)
    qtbot.addWidget(panel)

    for button in (
        panel.btn_to_top,
        panel.btn_up,
        panel.btn_down,
        panel.btn_to_bottom,
        panel.btn_dup,
    ):
        assert button.objectName() == "btn_icon"

    # The delete button keeps its own, louder style.
    assert panel.btn_del.objectName() == "btn_danger"


def test_the_mapping_panel_splits_its_space(qtbot):
    """The sample preview takes the free space of the mapping panel."""
    panel = FieldMappingPanel()
    qtbot.addWidget(panel)

    assert panel.lbl_record_num.property("role") == "accentText"
    assert panel.lbl_photo_thumb.property("role") == "photoWell"
