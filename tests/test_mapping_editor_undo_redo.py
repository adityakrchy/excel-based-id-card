"""Tests for Canvas Mapping Editor Undo and Redo actions, tool buttons, and shortcuts."""

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from id_card_generator.core.models import CanvasElement, TemplateDefinition
from id_card_generator.editor.canvas_items import CanvasItem
from id_card_generator.ui.editor_page import EditorPage


@pytest.fixture
def editor_page(qtbot):
    """Fixture providing initialized EditorPage."""
    page = EditorPage()
    qtbot.addWidget(page)
    # Load sample template
    tmpl = TemplateDefinition(name="Test Template", width_px=800, height_px=500)
    page.load_template(tmpl)
    return page


def test_undo_redo_initial_state(editor_page: EditorPage):
    """Verify undo and redo buttons are initially disabled."""
    assert not editor_page.btn_undo.isEnabled()
    assert not editor_page.btn_redo.isEnabled()
    assert not editor_page.scene.undo_stack.canUndo()
    assert not editor_page.scene.undo_stack.canRedo()


def test_undo_redo_add_and_delete_tool_buttons(editor_page: EditorPage, qtbot):
    """Verify adding elements can be undone and redone via tool buttons."""
    # 1. Add static text
    editor_page._add_static_text()
    assert len(editor_page.scene.template.elements) == 1
    assert editor_page.btn_undo.isEnabled()
    assert not editor_page.btn_redo.isEnabled()

    elem_id = editor_page.scene.template.elements[0].id

    # 2. Click Undo button
    editor_page.btn_undo.click()
    assert len(editor_page.scene.template.elements) == 0
    assert elem_id not in editor_page.scene._items_by_id
    assert not editor_page.btn_undo.isEnabled()
    assert editor_page.btn_redo.isEnabled()

    # 3. Click Redo button
    editor_page.btn_redo.click()
    assert len(editor_page.scene.template.elements) == 1
    assert elem_id in editor_page.scene._items_by_id
    assert editor_page.btn_undo.isEnabled()
    assert not editor_page.btn_redo.isEnabled()


def test_undo_redo_delete_selected(editor_page: EditorPage):
    """Verify deleting elements can be undone and redone."""
    editor_page._add_static_text()
    assert len(editor_page.scene.template.elements) == 1

    # Delete selected
    editor_page.scene.delete_selected()
    assert len(editor_page.scene.template.elements) == 0

    # Undo deletion
    editor_page.scene.undo()
    assert len(editor_page.scene.template.elements) == 1

    # Redo deletion
    editor_page.scene.redo()
    assert len(editor_page.scene.template.elements) == 0


def test_undo_redo_nudge_and_move(editor_page: EditorPage):
    """Verify nudging with arrows records undo and reverts positions."""
    editor_page.scene.snap_to_grid = False
    editor_page._add_static_text()
    item = editor_page.scene.get_selected_item()
    assert item is not None
    orig_x = item.pos().x()

    # Simulate Arrow Right key
    key_event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Right, Qt.NoModifier)
    editor_page.scene.keyPressEvent(key_event)
    assert item.pos().x() == orig_x + 1.0

    # Undo
    editor_page.scene.undo()
    assert item.pos().x() == orig_x

    # Redo
    editor_page.scene.redo()
    assert item.pos().x() == orig_x + 1.0


def test_undo_redo_shortcuts_windows_and_mac(editor_page: EditorPage):
    """Verify keyboard shortcuts for both Windows (Ctrl+Z, Ctrl+Y) and Mac (Cmd+Z, Cmd+Y)."""
    editor_page._add_photo_element()
    assert len(editor_page.scene.template.elements) == 1

    # Windows Ctrl+Z (Undo)
    ctrl_z = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Z, Qt.ControlModifier)
    editor_page.scene.keyPressEvent(ctrl_z)
    assert len(editor_page.scene.template.elements) == 0

    # Windows Ctrl+Y (Redo)
    ctrl_y = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Y, Qt.ControlModifier)
    editor_page.scene.keyPressEvent(ctrl_y)
    assert len(editor_page.scene.template.elements) == 1

    # Mac Cmd+Z (MetaModifier + Z for Undo)
    cmd_z = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Z, Qt.MetaModifier)
    editor_page.scene.keyPressEvent(cmd_z)
    assert len(editor_page.scene.template.elements) == 0

    # Mac Cmd+Y (MetaModifier + Y for Redo)
    cmd_y = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Y, Qt.MetaModifier)
    editor_page.scene.keyPressEvent(cmd_y)
    assert len(editor_page.scene.template.elements) == 1

    # Mac Shift+Cmd+Z (MetaModifier + ShiftModifier + Z for Redo)
    editor_page.scene.undo()
    assert len(editor_page.scene.template.elements) == 0
    cmd_shift_z = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Z, Qt.MetaModifier | Qt.ShiftModifier)
    editor_page.scene.keyPressEvent(cmd_shift_z)
    assert len(editor_page.scene.template.elements) == 1


def test_undo_redo_inspector_property_change(editor_page: EditorPage):
    """Verify inspector property changes can be cleanly undone and redone."""
    editor_page._add_static_text()
    item = editor_page.scene.get_selected_item()
    assert item is not None
    editor_page.inspector.set_selected_item(item)

    # Change name via inspector
    editor_page.inspector.txt_name.setText("Header Title")
    assert item.element.name == "Header Title"

    # Undo
    editor_page.scene.undo()
    assert item.element.name == "Static Label"

    # Redo
    editor_page.scene.redo()
    assert item.element.name == "Header Title"


def test_new_element_created_on_top(editor_page: EditorPage):
    """Verify new elements are always created on top of all existing canvas elements."""
    # Add first element (photo)
    editor_page._add_photo_element()
    item1 = editor_page.scene.get_selected_item()
    assert item1 is not None
    z1 = item1.zValue()

    # Add second element (rect)
    editor_page._add_rect_element()
    item2 = editor_page.scene.get_selected_item()
    assert item2 is not None
    z2 = item2.zValue()
    assert z2 > z1
    assert item2.isSelected()

    # Add third element (static text)
    editor_page._add_static_text()
    item3 = editor_page.scene.get_selected_item()
    assert item3 is not None
    z3 = item3.zValue()
    assert z3 > z2
    assert item3.isSelected()


def test_layer_reordering_bring_to_front_and_send_to_back(editor_page: EditorPage):
    """Verify layer reordering (to front, to back, forward, backward) and undo/redo."""
    editor_page._add_photo_element()      # item1
    editor_page._add_rect_element()       # item2
    editor_page._add_static_text()        # item3

    item1 = editor_page.scene._items_by_id[editor_page.scene.template.elements[0].id]
    item2 = editor_page.scene._items_by_id[editor_page.scene.template.elements[1].id]
    item3 = editor_page.scene._items_by_id[editor_page.scene.template.elements[2].id]

    # Initially item1 < item2 < item3
    assert item1.zValue() < item2.zValue() < item3.zValue()

    # 1. Bring bottom element (item1) to front
    editor_page.scene.bring_to_front(item1)
    assert item1.zValue() > item3.zValue()
    assert item1.zValue() > item2.zValue()

    # Undo bring to front
    editor_page.scene.undo()
    assert item1.zValue() < item2.zValue() < item3.zValue()

    # 2. Send top element (item3) to back
    editor_page.scene.send_to_back(item3)
    assert item3.zValue() < item1.zValue()
    assert item3.zValue() < item2.zValue()

    # Redo and Undo
    editor_page.scene.undo()
    assert item1.zValue() < item2.zValue() < item3.zValue()

    # 3. Bring forward: item1 swaps with item2
    editor_page.scene.bring_forward(item1)
    assert item2.zValue() < item1.zValue() < item3.zValue()

    # 4. Send backward: item1 swaps back with item2
    editor_page.scene.send_backward(item1)
    assert item1.zValue() < item2.zValue() < item3.zValue()


def test_layers_panel_click_selects_and_shows_tbox(editor_page: EditorPage):
    """Verify clicking an element in the layers tab selects it and triggers TBox."""
    editor_page._add_photo_element()
    editor_page._add_static_text()

    photo_elem = editor_page.scene.template.elements[0]
    photo_item = editor_page.scene._items_by_id[photo_elem.id]

    # Clear selection first
    editor_page.scene.clearSelection()
    assert not photo_item.isSelected()

    # Find photo item in layers tree
    tree = editor_page.layers_panel.tree
    target_tree_item = None
    for idx in range(tree.topLevelItemCount()):
        t_item = tree.topLevelItem(idx)
        if t_item.data(0, Qt.UserRole) == photo_item.element.id:
            target_tree_item = t_item
            break

    assert target_tree_item is not None

    # Simulate manual user click on layers tab item
    editor_page.layers_panel._on_tree_item_clicked(target_tree_item, 0)

    # Canvas item must now be selected, triggering TBox rendering
    assert photo_item.isSelected()
    assert editor_page.scene.get_selected_item() == photo_item
    assert editor_page.inspector._current_item == photo_item


def test_side_panel_layer_buttons_to_front_and_to_back(editor_page: EditorPage):
    """Verify side buttons in Layers and Properties panels move layers to front and back."""
    editor_page._add_photo_element()   # item 1
    editor_page._add_rect_element()    # item 2
    editor_page._add_static_text()     # item 3

    item1 = editor_page.scene._items_by_id[editor_page.scene.template.elements[0].id]
    item3 = editor_page.scene._items_by_id[editor_page.scene.template.elements[2].id]

    # Select bottom item (item1)
    editor_page.scene.clearSelection()
    item1.setSelected(True)
    editor_page.inspector.set_selected_item(item1)

    # Click 'To Front' in Properties inspector
    editor_page.inspector.btn_prop_to_front.click()
    assert item1.zValue() > item3.zValue()

    # Click 'To Back' in Properties inspector
    editor_page.inspector.btn_prop_to_back.click()
    assert item1.zValue() < item3.zValue()

    # Undo restores state
    editor_page.scene.undo()
    assert item1.zValue() > item3.zValue()

