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
        self.tree.setHeaderLabels(["Layer / Element", "Vis", "Lock"])
        self.tree.setColumnCount(3)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.header().resizeSection(1, 40)
        self.tree.header().setSectionResizeMode(2, QHeaderView.Fixed)
        self.tree.header().resizeSection(2, 40)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)

    def _connect_signals(self) -> None:
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)

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
            tree_item.setData(0, Qt.UserRole, item)

            # Visibility checkbox
            tree_item.setCheckState(1, Qt.Checked if elem.visible else Qt.Unchecked)
            # Lock checkbox
            tree_item.setCheckState(2, Qt.Checked if elem.locked else Qt.Unchecked)

            if item.isSelected():
                tree_item.setSelected(True)

            self.tree.addTopLevelItem(tree_item)

        self._updating = False

    def _on_tree_selection_changed(self) -> None:
        if self._updating:
            return
        selected = self.tree.selectedItems()
        if not selected:
            return

        self._updating = True
        self.scene.clearSelection()
        for t_item in selected:
            canvas_item: Optional[CanvasItem] = t_item.data(0, Qt.UserRole)
            if canvas_item:
                canvas_item.setSelected(True)
                self.item_selected.emit(canvas_item)
        self._updating = False

    def _on_scene_selection_changed(self) -> None:
        if self._updating:
            return
        self._updating = True
        self.tree.clearSelection()
        selected_canvas_items = self.scene.selectedItems()

        for idx in range(self.tree.topLevelItemCount()):
            t_item = self.tree.topLevelItem(idx)
            if t_item.data(0, Qt.UserRole) in selected_canvas_items:
                t_item.setSelected(True)
        self._updating = False

    def _on_item_changed(self, tree_item: QTreeWidgetItem, column: int) -> None:
        if self._updating:
            return
        canvas_item: Optional[CanvasItem] = tree_item.data(0, Qt.UserRole)
        if not canvas_item:
            return

        if column == 1:  # Visibility
            is_vis = tree_item.checkState(1) == Qt.Checked
            canvas_item.element.visible = is_vis
            canvas_item.setVisible(is_vis)
            self.scene.update()
        elif column == 2:  # Lock
            is_locked = tree_item.checkState(2) == Qt.Checked
            canvas_item.set_locked(is_locked)

    def _move_layer_up(self) -> None:
        selected = self.tree.selectedItems()
        if not selected:
            return
        item: CanvasItem = selected[0].data(0, Qt.UserRole)
        if item:
            item.setZValue(item.zValue() + 1)
            item.element.z_index = int(item.zValue())
            self.refresh_layers()
            self.order_changed.emit()

    def _move_layer_down(self) -> None:
        selected = self.tree.selectedItems()
        if not selected:
            return
        item: CanvasItem = selected[0].data(0, Qt.UserRole)
        if item:
            item.setZValue(max(0, item.zValue() - 1))
            item.element.z_index = int(item.zValue())
            self.refresh_layers()
            self.order_changed.emit()

    def _duplicate_current(self) -> None:
        self.scene.duplicate_selected()
        self.refresh_layers()

    def _delete_current(self) -> None:
        self.scene.delete_selected()
        self.refresh_layers()
