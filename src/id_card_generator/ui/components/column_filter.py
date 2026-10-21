"""The menu that filters a column of a table.

The connector filters the records of the sheet and the export filters the
cards that are written.  Both use the same menu, so the filter behaves the
same everywhere.

The values are picked with a check mark and the filter is only applied when
the button at the end of the menu is pressed.  A menu that closes after the
first click cannot pick more than one value.
"""

from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QWidget,
    QWidgetAction,
)

from id_card_generator.ui.studio_tokens import SIZES, TYPOGRAPHY, active_palette


def _menu_style(palette) -> str:
    """The look of the menu, in the colours of the theme."""
    return (
        "QMenu {"
        f"  background-color: {palette.SURFACE_CONTAINER};"
        f"  border: 1px solid {palette.BORDER_HAIRLINE};"
        "  border-radius: 6px;"
        "  padding: 6px;"
        "}"
        "QMenu::item {"
        f"  color: {palette.ON_SURFACE};"
        "  padding: 5px 24px 5px 8px;"
        "  border-radius: 4px;"
        "}"
        "QMenu::item:selected {"
        f"  background-color: {palette.SURFACE_HIGH};"
        "}"
        "QMenu::item:disabled {"
        f"  color: {palette.TEXT_MUTED};"
        "}"
        "QMenu::separator {"
        f"  height: 1px; background: {palette.BORDER_HAIRLINE}; margin: 5px 8px;"
        "}"
        "QLabel#menu_title {"
        f"  color: {palette.PRIMARY_CONTAINER};"
        "  font-size: 11px;"
        "  font-weight: 700;"
        "  padding: 4px 8px 6px 8px;"
        "}"
        "QLabel#menu_count {"
        f"  color: {palette.TEXT_MUTED};"
        "  font-size: 10px;"
        "  padding: 2px 8px 4px 8px;"
        "}"
        "QLineEdit {"
        f"  background-color: {palette.SURFACE_LOWEST};"
        f"  border: 1px solid {palette.BORDER_HAIRLINE};"
        "  border-radius: 4px;"
        "  padding: 4px 8px;"
        f"  color: {palette.ON_SURFACE};"
        f"  font-size: 11px; margin: 2px 6px 6px 6px;"
        "}"
        "QListWidget {"
        f"  background-color: {palette.SURFACE_LOWEST};"
        f"  border: 1px solid {palette.BORDER_HAIRLINE};"
        "  border-radius: 4px;"
        f"  color: {palette.ON_SURFACE};"
        f"  font-family: {TYPOGRAPHY.FONT_FAMILY_MONO};"
        "  font-size: 11px;"
        "  padding: 2px;"
        "  margin: 2px 6px 4px 6px;"
        "}"
        "QListWidget::item {"
        "  padding: 4px 6px;"
        "  border-radius: 3px;"
        "}"
        "QListWidget::item:hover {"
        f"  background-color: {palette.SURFACE_HIGH};"
        "}"
        "QPushButton {"
        f"  background-color: {palette.SURFACE_HIGH};"
        f"  color: {palette.ON_SURFACE};"
        f"  border: 1px solid {palette.BORDER_HAIRLINE};"
        "  border-radius: 4px;"
        "  padding: 4px 10px;"
        "  font-size: 11px;"
        "}"
        "QPushButton:hover {"
        f"  background-color: {palette.SURFACE_HIGHEST};"
        f"  border-color: {palette.OUTLINE_VARIANT};"
        "}"
        "QPushButton#btn_primary {"
        f"  background-color: {palette.PRIMARY_CONTAINER};"
        f"  color: {palette.ON_PRIMARY_CONTAINER};"
        f"  border: 1px solid {palette.PRIMARY};"
        "  font-weight: 600;"
        "}"
        "QPushButton#btn_primary:hover {"
        f"  background-color: {palette.PRIMARY};"
        f"  color: {palette.ON_PRIMARY_CONTAINER};"
        "}"
    )


def open_column_filter_menu(
    parent: QWidget,
    model,
    column: int,
    pos: QPoint,
    on_changed=None,
) -> QMenu:
    """Open the menu that filters a column of a table.

    ``model`` has to be a :class:`FilterableTableModel`.  The values of the
    column are listed with the number of the rows that have them, a search
    narrows the list, and the button at the end applies the picked values.
    """
    palette = active_palette()

    values = model.distinct_values(column)
    counts = model.value_counts(column)
    current = model.column_filter(column)
    title = model.headerData(column, Qt.Horizontal) or f"Column {column}"

    menu = QMenu(parent)
    menu.setObjectName("column_filter_menu")
    menu.setStyleSheet(_menu_style(palette))

    # The name of the column.
    title_label = QLabel(title)
    title_label.setObjectName("menu_title")
    title_action = QWidgetAction(menu)
    title_action.setDefaultWidget(title_label)
    menu.addAction(title_action)

    # A search for the values of the column.
    search = QLineEdit()
    search.setPlaceholderText(f"Search {str(title).split(' ')[0].lower()}...")
    search_action = QWidgetAction(menu)
    search_action.setDefaultWidget(search)
    menu.addAction(search_action)

    # The values of the column, with a check mark for the picked ones.
    list_widget = QListWidget()
    list_widget.setObjectName("filter_values")
    list_widget.setSelectionMode(QAbstractItemView.NoSelection)
    list_widget.setUniformItemSizes(True)
    list_widget.setFixedHeight(min(260, 26 * len(values) + 10))
    for value in values:
        label = value if value else "(empty)"
        item = QListWidgetItem(f"{label}  ({counts.get(value, 0)})")
        item.setData(Qt.UserRole, value)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(
            Qt.Checked if (value in current or not current) else Qt.Unchecked
        )
        list_widget.addItem(item)
    list_action = QWidgetAction(menu)
    list_action.setDefaultWidget(list_widget)
    menu.addAction(list_action)

    # The two helpers.
    helper_row = QWidget()
    helper_layout = QHBoxLayout(helper_row)
    helper_layout.setContentsMargins(6, 2, 6, 4)
    helper_layout.setSpacing(6)

    btn_all = QPushButton(f"Select all ({len(values)})")
    btn_clear = QPushButton("Clear the filter")
    helper_layout.addWidget(btn_all)
    helper_layout.addWidget(btn_clear)
    helper_action = QWidgetAction(menu)
    helper_action.setDefaultWidget(helper_row)
    menu.addAction(helper_action)

    # How many values are picked.
    count_label = QLabel("")
    count_label.setObjectName("menu_count")
    count_action = QWidgetAction(menu)
    count_action.setDefaultWidget(count_label)
    menu.addAction(count_action)

    # The button that applies the filter.
    apply_button = QPushButton("Apply the filter")
    apply_button.setObjectName("btn_primary")
    apply_button.setFixedHeight(SIZES.CONTROL_HEIGHT)
    apply_button.setMinimumWidth(170)
    apply_action = QWidgetAction(menu)
    apply_action.setDefaultWidget(apply_button)
    menu.addAction(apply_action)

    def _picked():
        """The values that are checked."""
        return {
            list_widget.item(row).data(Qt.UserRole)
            for row in range(list_widget.count())
            if list_widget.item(row).checkState() == Qt.Checked
            and not list_widget.item(row).isHidden()
        }

    def _update_count() -> None:
        count_label.setText(f"{len(_picked())} of {len(values)} values picked")

    def _apply() -> None:
        """Write the picked values into the model."""
        allowed = _picked()
        if len(allowed) == len(values):
            # Every value is picked - that is no filter at all.
            model.clear_column_filter(column)
        else:
            model.set_column_filter(column, allowed)
        if on_changed is not None:
            on_changed()

    def _on_all() -> None:
        """Check every value."""
        for row in range(list_widget.count()):
            list_widget.item(row).setCheckState(Qt.Checked)
        _update_count()

    def _on_clear() -> None:
        """Remove the filter of the column."""
        model.clear_column_filter(column)
        for row in range(list_widget.count()):
            list_widget.item(row).setCheckState(Qt.Unchecked)
        _update_count()
        if on_changed is not None:
            on_changed()
        menu.close()

    def _on_search(text: str) -> None:
        needle = text.lower().strip()
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            value = str(item.data(Qt.UserRole)).lower()
            item.setHidden(bool(needle) and needle not in value)
        _update_count()

    def _on_item_changed(item: QListWidgetItem) -> None:
        # The values are only counted here - the filter is applied with the
        # button, so the menu stays open while the values are picked.
        _update_count()

    list_widget.itemChanged.connect(_on_item_changed)
    btn_all.clicked.connect(_on_all)
    btn_clear.clicked.connect(_on_clear)
    search.textChanged.connect(_on_search)
    apply_button.clicked.connect(lambda: (_apply(), menu.close()))

    _update_count()
    menu.popup(pos)
    return menu
