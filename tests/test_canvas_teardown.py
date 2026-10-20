"""Regression tests for the canvas teardown crash.

The layers panel used to store the live ``CanvasItem`` (a QObject) in the
tree item data.  When the scene was cleared the items were destroyed while
the tree still referenced them, and PySide converted the dangling pointer
inside the QVariant - which segfaulted the interpreter.

The tree now stores the element id and resolves the item through the scene.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from id_card_generator.core.models import CanvasElement, TemplateDefinition
from id_card_generator.editor.canvas_items import CanvasItem
from id_card_generator.editor.canvas_scene import CanvasScene
from id_card_generator.editor.layers_panel import LayersPanel


def _template(count: int = 4, prefix: str = "el") -> TemplateDefinition:
    template = TemplateDefinition(name="Layers", width_px=400, height_px=250)
    template.elements = [
        CanvasElement(
            id=f"{prefix}-{i}",
            name=f"Element {i}",
            type="static_text",
            x=10 + i * 10,
            y=10 + i * 10,
            width=100,
            height=30,
            static_content=f"E{i}",
            z_index=i,
        )
        for i in range(count)
    ]
    return template


def test_tree_never_holds_a_live_canvas_item(qtbot):
    """The invariant that prevents the crash: no QObject in the tree data.

    A QVariant that holds a QObject is converted by PySide while the object
    is being destroyed - that is what segfaulted the interpreter.
    """
    from PySide6.QtCore import Qt

    scene = CanvasScene()
    panel = LayersPanel(scene)
    qtbot.addWidget(panel)

    scene.load_template(_template())
    panel.refresh_layers()

    row = panel.tree.topLevelItem(0)
    stored = row.data(0, Qt.UserRole)
    assert isinstance(stored, str), "the tree must only store the element id"
    assert not isinstance(stored, CanvasItem)


def test_layers_panel_survives_a_scene_clear(qtbot):
    """Clearing the scene while the tree holds rows must not crash."""
    scene = CanvasScene()
    panel = LayersPanel(scene)
    qtbot.addWidget(panel)

    scene.load_template(_template())
    panel.refresh_layers()
    assert panel.tree.topLevelItemCount() == 4

    # This is the exact sequence that used to crash: the scene destroys the
    # canvas items while the tree still holds the rows.
    scene.load_template(_template(2))
    panel.refresh_layers()

    assert panel.tree.topLevelItemCount() == 2
    # The rows resolve to the *new* items.
    from PySide6.QtCore import Qt

    row = panel.tree.topLevelItem(0)
    item = panel._canvas_item_for(row)
    assert item is not None
    assert item.element.id == row.data(0, Qt.UserRole)


def test_layers_panel_handles_a_vanished_item(qtbot):
    """A row whose item is gone resolves to None instead of a stale pointer."""
    scene = CanvasScene()
    panel = LayersPanel(scene)
    qtbot.addWidget(panel)

    scene.load_template(_template())
    panel.refresh_layers()
    row = panel.tree.topLevelItem(0)

    # Remove the item behind the panel's back, exactly like a scene teardown.
    from PySide6.QtCore import Qt

    element_id = row.data(0, Qt.UserRole)
    item = scene.item_for_element_id(element_id)
    scene._items_by_id.pop(element_id, None)
    scene.removeItem(item)
    assert panel._canvas_item_for(row) is None


def test_scene_drops_item_references_before_clearing(qtbot):
    """The scene must not hand out items that are being destroyed."""
    from PySide6.QtCore import Qt

    scene = CanvasScene()
    scene.load_template(_template(2, prefix="old"))
    element_id = next(iter(scene._items_by_id))
    assert scene.item_for_element_id(element_id) is not None

    scene.load_template(_template(3, prefix="new"))
    # The old element is gone, the new ones are reachable.
    assert scene.item_for_element_id(element_id) is None
    assert len(scene._items_by_id) == 3


CRASH_SCRIPT = """
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
app = QApplication([])

from id_card_generator.core.models import CanvasElement, TemplateDefinition
from id_card_generator.editor.canvas_items import CanvasItem
from id_card_generator.editor.canvas_scene import CanvasScene
from id_card_generator.editor.layers_panel import LayersPanel

def make_template(count):
    t = TemplateDefinition(name="L", width_px=400, height_px=250)
    t.elements = [
        CanvasElement(id=f"el-{i}", name=f"E{i}", type="static_text",
                      x=10, y=10, width=100, height=30, static_content="x", z_index=i)
        for i in range(count)
    ]
    return t

scene = CanvasScene()
panel = LayersPanel(scene)
scene.load_template(make_template(4))
panel.refresh_layers()
# Clear the scene while the tree still holds the rows, then rebuild.
scene.load_template(make_template(2))
panel.refresh_layers()
print("survived")
"""


def test_clearing_the_scene_never_crashes_the_interpreter(tmp_path: Path):
    """Run the teardown sequence in a subprocess: a segfault must fail the test."""
    script = tmp_path / "crash_check.py"
    script.write_text(CRASH_SCRIPT)

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        f"the interpreter died with code {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "survived" in result.stdout


def test_layers_rows_are_dropped_before_the_items_die(qtbot):
    """The tree must be empty before the scene destroys the canvas items.

    This is the deterministic version of the crash: a QObject that is
    destroyed while a QVariant still references it makes PySide dereference
    a freed pointer.
    """
    scene = CanvasScene()
    panel = LayersPanel(scene)
    qtbot.addWidget(panel)

    seen = {}

    def _on_clearing():
        # While the scene announces the teardown the tree must be empty.
        seen["rows"] = panel.tree.topLevelItemCount()

    scene.about_to_clear.connect(_on_clearing)

    scene.load_template(_template())
    panel.refresh_layers()
    assert panel.tree.topLevelItemCount() == 4

    scene.load_template(_template(2))
    assert seen.get("rows") == 0, "the tree still held rows while the items died"
