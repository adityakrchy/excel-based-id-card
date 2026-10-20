"""Layers hierarchy panel showing all canvas elements, ordering, visibility, and locking."""

import logging
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.editor.canvas_items import CanvasItem
from id_card_generator.editor.canvas_scene import CanvasScene

logger = logging.getLogger(__name__)


class LayersPanel(QWidget):
    """Hierarchy tree displaying all canvas elements with layer ordering, visibility, and locking."""

    item_selected = Signal(object)  # CanvasItem
    order_changed = Signal()

    def __init__(self, scene: CanvasScene, parent=None):
        super().__init__(parent)
        self.scene = scene
        self._updating = False

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Header with action buttons
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<b>Layers</b>"))
        header_layout.addStretch()

        self.btn_to_top = QPushButton("⏫")
        self.btn_to_top.setToolTip("Bring to Front (Top of all elements)")
        self.btn_to_top.setFixedWidth(28)
        self.btn_to_top.clicked.connect(self._bring_to_front)
        header_layout.addWidget(self.btn_to_top)

        self.btn_up = QPushButton("▲")
        self.btn_up.setToolTip("Bring Forward (Move Layer Up)")
        self.btn_up.setFixedWidth(28)
        self.btn_up.clicked.connect(self._move_layer_up)
        header_layout.addWidget(self.btn_up)

        self.btn_down = QPushButton("▼")
        self.btn_down.setToolTip("Send Backward (Move Layer Down)")
        self.btn_down.setFixedWidth(28)
        self.btn_down.clicked.connect(self._move_layer_down)
        header_layout.addWidget(self.btn_down)

        self.btn_to_bottom = QPushButton("⏬")
        self.btn_to_bottom.setToolTip("Send to Back (Bottom of all elements)")
        self.btn_to_bottom.setFixedWidth(28)
        self.btn_to_bottom.clicked.connect(self._send_to_back)
        header_layout.addWidget(self.btn_to_bottom)

        self.btn_dup = QPushButton("⧉")
        self.btn_dup.setToolTip("Duplicate Layer")
        self.btn_dup.setFixedWidth(28)
        self.btn_dup.clicked.connect(self._duplicate_current)
        header_layout.addWidget(self.btn_dup)

        self.btn_del = QPushButton("🗑")
        self.btn_del.setToolTip("Delete Layer")
        self.btn_del.setFixedWidth(28)
        self.btn_del.setObjectName("btn_danger")
        self.btn_del.clicked.connect(self._delete_current)
        header_layout.addWidget(self.btn_del)

        layout.addLayout(header_layout)

        # Tree Widget for Layers
        self.tree = QTreeWidget()
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.setHeaderLabels(["Layer / Element", "Vis", "Lock"])
        self.tree.setColumnCount(3)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.header().resizeSection(1, 40)
        self.tree.header().setSectionResizeMode(2, QHeaderView.Fixed)
        self.tree.header().resizeSection(2, 40)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)

        # Bottom layer ordering toolbar for clear, labeled access
        order_bar = QHBoxLayout()
        order_bar.setContentsMargins(0, 2, 0, 2)
        order_bar.setSpacing(4)

        btn_bar_front = QPushButton("To Front ⏫")
        btn_bar_front.setToolTip("Bring layer on top of every other element")
        btn_bar_front.clicked.connect(self._bring_to_front)
        order_bar.addWidget(btn_bar_front)

        btn_bar_forward = QPushButton("Forward ▲")
        btn_bar_forward.setToolTip("Bring layer one step forward")
        btn_bar_forward.clicked.connect(self._move_layer_up)
        order_bar.addWidget(btn_bar_forward)

        btn_bar_backward = QPushButton("Backward ▼")
        btn_bar_backward.setToolTip("Send layer one step backward")
        btn_bar_backward.clicked.connect(self._move_layer_down)
        order_bar.addWidget(btn_bar_backward)

        btn_bar_back = QPushButton("To Back ⏬")
        btn_bar_back.setToolTip("Send layer back to bottom of all elements")
        btn_bar_back.clicked.connect(self._send_to_back)
        order_bar.addWidget(btn_bar_back)

        layout.addLayout(order_bar)

    def _connect_signals(self) -> None:
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)
        # The rows must be gone before the canvas items are destroyed.
        self.scene.about_to_clear.connect(self._on_scene_about_to_clear)

    def _on_scene_about_to_clear(self) -> None:
        """Drop the tree rows before the canvas items are destroyed."""
        self._updating = True
        try:
            self.tree.clear()
        finally:
            self._updating = False

    def refresh_layers(self) -> None:
        """Rebuild the layers tree from current canvas items sorted descending by z-index."""
        self._updating = True
        self.tree.clear()

        # Canvas items sorted descending so top layer is at top of list
        items = [it for it in self.scene.items() if isinstance(it, CanvasItem)]
        sorted_items = sorted(items, key=lambda x: x.zValue(), reverse=True)

        for item in sorted_items:
            elem = item.element
            type_tag = elem.type.replace("_", " ").title()
            binding_info = f" [{elem.binding}]" if elem.binding else ""
            display_text = f"{elem.name} ({type_tag}){binding_info}"

            tree_item = QTreeWidgetItem([display_text, "", ""])
            # Store the element id, never the canvas item itself: the item is
            # a QObject that is destroyed when the scene is cleared, and a
            # stale pointer inside a QVariant crashes the interpreter.
            tree_item.setData(0, Qt.UserRole, item.element.id)

            # Visibility checkbox
            tree_item.setCheckState(1, Qt.Checked if elem.visible else Qt.Unchecked)
            # Lock checkbox
            tree_item.setCheckState(2, Qt.Checked if elem.locked else Qt.Unchecked)

            if item.isSelected():
                tree_item.setSelected(True)

            self.tree.addTopLevelItem(tree_item)

        self._updating = False

    def _canvas_item_for(self, tree_item: QTreeWidgetItem) -> Optional[CanvasItem]:
        """Resolve the canvas item of a tree row.

        The row only knows the element id; the item itself is looked up in the
        scene and may already be gone.
        """
        if tree_item is None:
            return None
        element_id = tree_item.data(0, Qt.UserRole)
        if not isinstance(element_id, str):
            return None
        return self.scene.item_for_element_id(element_id)

    def _on_tree_item_clicked(self, tree_item: QTreeWidgetItem, column: int) -> None:
        """Explicitly focus and select item on canvas with TBox when clicked in layers tab."""
        if column in (1, 2):
            return  # Handled by check state in _on_item_changed
        if len(self.tree.selectedItems()) <= 1:
            canvas_item = self._canvas_item_for(tree_item)
            if canvas_item:
                self._select_and_focus_item(canvas_item)

    def _select_and_focus_item(self, canvas_item: CanvasItem) -> None:
        """Select item on canvas, trigger transform box (TBox) rendering and inspector sync."""
        if self._updating:
            return
        self._updating = True
        try:
            self.scene.clearSelection()
            canvas_item.setSelected(True)
            canvas_item.update()
            self.scene.update()
            self.scene.element_selected.emit(canvas_item)
            self.item_selected.emit(canvas_item)

            # Ensure the selected item and its TBox are visible in view
            views = self.scene.views()
            if views:
                views[0].ensureVisible(canvas_item, 40, 40)
        finally:
            self._updating = False

    def _on_tree_selection_changed(self) -> None:
        if self._updating:
            return
        selected = self.tree.selectedItems()
        self._updating = True
        try:
            self.scene.clearSelection()
            selected_canvas_items = []
            for tree_row in selected:
                c_item = self._canvas_item_for(tree_row)
                if c_item is not None and c_item.scene() == self.scene:
                    c_item.setSelected(True)
                    selected_canvas_items.append(c_item)

            if selected_canvas_items:
                last_item = selected_canvas_items[-1]
                self.scene.element_selected.emit(last_item)
                self.item_selected.emit(last_item)
                views = self.scene.views()
                if views:
                    views[0].ensureVisible(last_item, 40, 40)
            else:
                self.scene.element_selected.emit(None)
                self.item_selected.emit(None)
            self.scene.update()
        finally:
            self._updating = False

    def _on_scene_selection_changed(self) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            try:
                selected_canvas_items = self.scene.selectedItems()
            except RuntimeError:
                return
            self.tree.clearSelection()

            selected_ids = {
                item.element.id for item in selected_canvas_items
            }
            for idx in range(self.tree.topLevelItemCount()):
                t_item = self.tree.topLevelItem(idx)
                if t_item.data(0, Qt.UserRole) in selected_ids:
                    t_item.setSelected(True)
        finally:
            self._updating = False

    def _on_item_changed(self, tree_item: QTreeWidgetItem, column: int) -> None:
        if self._updating:
            return
        canvas_item = self._canvas_item_for(tree_item)
        if canvas_item is None:
            return

        if column == 1:  # Visibility
            is_vis = tree_item.checkState(1) == Qt.Checked
            canvas_item.element.visible = is_vis
            canvas_item.setVisible(is_vis)
            self.scene.update()
        elif column == 2:  # Lock
            is_locked = tree_item.checkState(2) == Qt.Checked
            canvas_item.set_locked(is_locked)

    def _get_selected_canvas_item(self) -> Optional[CanvasItem]:
        selected = self.tree.selectedItems()
        if selected:
            item = self._canvas_item_for(selected[0])
            if item is not None:
                return item
        return self.scene.get_selected_item()

    def _bring_to_front(self) -> None:
        """Bring layer to top of every other element on canvas."""
        item = self._get_selected_canvas_item()
        if item:
            self.scene.bring_to_front(item)
            self.refresh_layers()
            self.order_changed.emit()

    def _move_layer_up(self) -> None:
        """Bring layer one step forward (above adjacent element)."""
        item = self._get_selected_canvas_item()
        if item:
            self.scene.bring_forward(item)
            self.refresh_layers()
            self.order_changed.emit()

    def _move_layer_down(self) -> None:
        """Send layer one step backward (behind adjacent element)."""
        item = self._get_selected_canvas_item()
        if item:
            self.scene.send_backward(item)
            self.refresh_layers()
            self.order_changed.emit()

    def _send_to_back(self) -> None:
        """Send layer back to bottom of all canvas elements."""
        item = self._get_selected_canvas_item()
        if item:
            self.scene.send_to_back(item)
            self.refresh_layers()
            self.order_changed.emit()

    def _duplicate_current(self) -> None:
        self.scene.duplicate_selected()
        self.refresh_layers()

    def _delete_current(self) -> None:
        self.scene.delete_selected()
        self.refresh_layers()
