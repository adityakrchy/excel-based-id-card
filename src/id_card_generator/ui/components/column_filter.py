"""The menu that filters a column of a table.

The connector filters the records of the sheet and the export filters the
cards that are written.  Both use the same menu, so the filter behaves the
same everywhere.
"""

from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QMenu,
    QWidget,
    QWidgetAction,
)

from id_card_generator.ui.studio_tokens import active_palette


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
    narrows the list and the table follows while the menu is open.
    """
    palette = active_palette()

    values = model.distinct_values(column)
    counts = model.value_counts(column)
    current = model.column_filter(column)
    title = model.headerData(column, Qt.Horizontal) or f"Column {column}"

    menu = QMenu(parent)
    menu.setObjectName("column_filter_menu")
    menu.setStyleSheet(
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
        "QLineEdit {"
        f"  background-color: {palette.SURFACE_LOWEST};"
        f"  border: 1px solid {palette.BORDER_HAIRLINE};"
        "  border-radius: 4px;"
        "  padding: 4px 8px;"
        f"  color: {palette.ON_SURFACE};"
        f"  font-size: 11px; margin: 2px 6px 6px 6px;"
        "}"
    )

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
    menu.addSeparator()

    act_all = menu.addAction(f"Select all ({len(values)})")
    act_clear = menu.addAction("Clear the filter")
    menu.addSeparator()

    # One entry per value.
    entries = []
    for value in values:
        label = value if value else "(empty)"
        action = menu.addAction(f"{label}  ({counts.get(value, 0)})")
        action.setCheckable(True)
        action.setChecked(value in current or not current)
        action.setData(value)
        entries.append(action)

    def _apply() -> None:
        """Write the picked values into the model."""
        allowed = {
            action.data()
            for action in entries
            if action.isChecked() and action.isVisible()
        }
        if len(allowed) == len(values):
            # Every value is picked - that is no filter at all.
            model.clear_column_filter(column)
        else:
            model.set_column_filter(column, allowed)
        if on_changed is not None:
            on_changed()

    def _on_toggled(checked: bool) -> None:
        _apply()

    def _on_all() -> None:
        for action in entries:
            action.setChecked(True)
        _apply()

    def _on_clear() -> None:
        for action in entries:
            action.setChecked(False)
        model.clear_column_filter(column)
        if on_changed is not None:
            on_changed()
        menu.close()

    def _on_search(text: str) -> None:
        needle = text.lower().strip()
        for action in entries:
            value = str(action.data()).lower()
            action.setVisible(not needle or needle in value)

    for action in entries:
        action.toggled.connect(_on_toggled)
    act_all.triggered.connect(_on_all)
    act_clear.triggered.connect(_on_clear)
    search.textChanged.connect(_on_search)

    menu.popup(pos)
    return menu
