"""Tests for multi-element selection and group movement on canvas and layers panel."""

import pytest
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QMouseEvent, QKeyEvent
from PySide6.QtTest import QTest

from id_card_generator.core.models import CanvasElement, CanvasElementStyle, TemplateDefinition
from id_card_generator.editor.canvas_items import CanvasItem
from id_card_generator.editor.canvas_scene import CanvasScene
from id_card_generator.editor.canvas_view import CanvasView
from id_card_generator.editor.layers_panel import LayersPanel


@pytest.fixture
def canvas_setup(qtbot):
    scene = CanvasScene()
    template = TemplateDefinition(
        id="tpl_multi",
        name="Multi Select Template",
        width=500.0,
        height=300.0,
        background_color="#FFFFFF",
        elements=[],
    )
    scene.load_template(template)
    view = CanvasView(scene)
    view.resize(800, 600)
    view.show()
    qtbot.addWidget(view)
    qtbot.waitExposed(view)

    # Add three test elements
    e1 = CanvasElement(
        id="elem_1",
        type="text",
        name="Element 1",
        x=50.0,
        y=50.0,
        width=100.0,
        height=40.0,
        style=CanvasElementStyle(content="First", font_size=10.0),
    )
    e2 = CanvasElement(
        id="elem_2",
        type="text",
        name="Element 2",
        x=200.0,
        y=50.0,
        width=100.0,
        height=40.0,
        style=CanvasElementStyle(content="Second", font_size=10.0),
    )
    e3 = CanvasElement(
        id="elem_3",
        type="text",
        name="Element 3",
        x=50.0,
        y=150.0,
        width=100.0,
        height=40.0,
        style=CanvasElementStyle(content="Third", font_size=10.0),
    )

    item1 = scene.add_element(e1, push_undo=False)
    item2 = scene.add_element(e2, push_undo=False)
    item3 = scene.add_element(e3, push_undo=False)

    return scene, view, item1, item2, item3


def test_shift_click_multi_selects_elements(canvas_setup, qtbot):
    """Holding Shift while clicking elements adds them to selection."""
    scene, view, item1, item2, item3 = canvas_setup

    p1 = view.mapFromScene(item1.sceneBoundingRect().center())
    p2 = view.mapFromScene(item2.sceneBoundingRect().center())
    p3 = view.mapFromScene(item3.sceneBoundingRect().center())

    # Regular click on item 1
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, p1)
    assert len(scene.selectedItems()) == 1
    assert item1.isSelected()

    # Shift + click on item 2
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.ShiftModifier, p2)
    assert len(scene.selectedItems()) == 2
    assert item1.isSelected()
    assert item2.isSelected()

    # Shift + click on item 3
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.ShiftModifier, p3)
    assert len(scene.selectedItems()) == 3
    assert item1.isSelected()
    assert item2.isSelected()
    assert item3.isSelected()


def test_cmd_meta_click_multi_selects_and_toggles(canvas_setup, qtbot):
    """Holding Cmd (MetaModifier on macOS) adds to and toggles selection."""
    scene, view, item1, item2, item3 = canvas_setup

    p1 = view.mapFromScene(item1.sceneBoundingRect().center())
    p2 = view.mapFromScene(item2.sceneBoundingRect().center())

    # Click item 1
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, p1)
    assert item1.isSelected()
    assert not item2.isSelected()

    # Meta + click on item 2
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.MetaModifier, p2)
    assert item1.isSelected()
    assert item2.isSelected()
    assert len(scene.selectedItems()) == 2

    # Meta + click again on item 2 toggles it off
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.MetaModifier, p2)
    assert item1.isSelected()
    assert not item2.isSelected()
    assert len(scene.selectedItems()) == 1


def test_ctrl_click_multi_selects_elements(canvas_setup, qtbot):
    """Holding Ctrl also adds to selection."""
    scene, view, item1, item2, item3 = canvas_setup

    p1 = view.mapFromScene(item1.sceneBoundingRect().center())
    p2 = view.mapFromScene(item2.sceneBoundingRect().center())

    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, p1)
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.ControlModifier, p2)

    assert len(scene.selectedItems()) == 2
    assert item1.isSelected()
    assert item2.isSelected()


def test_drag_moves_all_selected_elements(canvas_setup, qtbot):
    """Clicking and dragging any selected element moves all selected elements together."""
    scene, view, item1, item2, item3 = canvas_setup

    p1 = view.mapFromScene(item1.sceneBoundingRect().center())
    p2 = view.mapFromScene(item2.sceneBoundingRect().center())

    # Select both item 1 and item 2
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, p1)
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.ShiftModifier, p2)
    assert item1.isSelected() and item2.isSelected()

    init_pos1 = QPointF(item1.pos())
    init_pos2 = QPointF(item2.pos())
    init_pos3 = QPointF(item3.pos())

    # Drag from item 1's position by dx=40, dy=25
    dx, dy = 40, 25
    QTest.mousePress(view.viewport(), Qt.LeftButton, Qt.NoModifier, p1)
    p1_moved = QPoint(p1.x() + dx, p1.y() + dy)
    from PySide6.QtWidgets import QApplication
    move_ev = QMouseEvent(QMouseEvent.Type.MouseMove, p1_moved, p1_moved, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(view.viewport(), move_ev)
    QTest.mouseRelease(view.viewport(), Qt.LeftButton, Qt.NoModifier, p1_moved)

    # Both selected items should move by roughly (dx, dy), unselected item 3 remains unchanged
    delta1 = item1.pos() - init_pos1
    delta2 = item2.pos() - init_pos2
    delta3 = item3.pos() - init_pos3

    # Both moved by identical displacement
    assert delta1.x() == delta2.x()
    assert delta1.y() == delta2.y()
    assert delta1.x() != 0
    assert delta1.y() != 0
    # Unselected item did not move
    assert delta3.x() == 0 and delta3.y() == 0


def test_arrow_keys_nudge_all_selected_elements(canvas_setup, qtbot):
    """Arrow keys nudge all selected elements simultaneously."""
    scene, view, item1, item2, item3 = canvas_setup

    item1.setSelected(True)
    item2.setSelected(True)
    item3.setSelected(False)

    init_pos1 = QPointF(item1.pos())
    init_pos2 = QPointF(item2.pos())
    init_pos3 = QPointF(item3.pos())

    # Press Right arrow key 3 times
    for _ in range(3):
        ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_Right, Qt.NoModifier)
        scene.keyPressEvent(ev)

    assert item1.pos().x() == init_pos1.x() + 3.0
    assert item2.pos().x() == init_pos2.x() + 3.0
    assert item3.pos().x() == init_pos3.x()  # Unselected


def test_layers_panel_multi_selection(canvas_setup, qtbot):
    """Selecting multiple rows in layers panel updates scene selection."""
    scene, view, item1, item2, item3 = canvas_setup
    panel = LayersPanel(scene)
    qtbot.addWidget(panel)
    panel.refresh_layers()

    assert panel.tree.topLevelItemCount() == 3

    # Multi-select first two items in tree
    panel.tree.clearSelection()
    panel.tree.topLevelItem(0).setSelected(True)
    panel.tree.topLevelItem(1).setSelected(True)

    # Verify scene has 2 items selected
    selected_in_scene = [it for it in scene.selectedItems() if isinstance(it, CanvasItem)]
    assert len(selected_in_scene) == 2

    # And canvas selection changes sync back to tree
    scene.clearSelection()
    item3.setSelected(True)
    selected_in_tree = panel.tree.selectedItems()
    assert len(selected_in_tree) == 1
    assert selected_in_tree[0].data(0, Qt.UserRole) == item3
