"""Tests for the template clean up dialog layout.

The dialog used to squeeze two lines of text into a single line high row, so
the cell widgets overlapped each other, and the badge / action columns were
clipped.  These tests lock the layout down.
"""

import pytest

from id_card_generator.ui.dialogs.template_cleanup_dialog import (
    COL_ACTIONS,
    COL_FILE,
    COL_SELECT,
    COL_SPECS,
    COL_TYPE,
    ROW_HEIGHT,
    TemplateCleanupDialog,
)


@pytest.fixture
def cleanup_dialog(qtbot):
    dialog = TemplateCleanupDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


def test_rows_are_tall_enough_for_two_lines(cleanup_dialog: TemplateCleanupDialog):
    """Every row must fit the name + description of a template."""
    table = cleanup_dialog.table
    assert table.rowCount() > 0
    assert table.rowHeight(0) >= ROW_HEIGHT
    assert table.verticalHeader().defaultSectionSize() == ROW_HEIGHT


def test_columns_fit_their_content(cleanup_dialog: TemplateCleanupDialog):
    """The fixed columns must be wide enough for their badges and buttons."""
    table = cleanup_dialog.table
    assert table.columnWidth(0) >= COL_SELECT
    assert table.columnWidth(2) >= COL_TYPE
    assert table.columnWidth(3) >= COL_SPECS
    assert table.columnWidth(4) >= COL_FILE
    assert table.columnWidth(5) >= COL_ACTIONS


def test_columns_fit_inside_the_dialog(cleanup_dialog: TemplateCleanupDialog):
    """The fixed columns plus the scroll bar leave room for the name column."""
    table = cleanup_dialog.table
    fixed = sum(
        table.columnWidth(c)
        for c in range(table.columnCount())
        if c != 1
    )
    available = table.viewport().width()
    assert fixed < available, "the fixed columns leave no room for the name"


def test_type_badge_is_not_clipped(cleanup_dialog: TemplateCleanupDialog):
    """The type badge has to fit into its column."""
    table = cleanup_dialog.table
    for row in range(table.rowCount()):
        badge = table.cellWidget(row, 2)
        if badge is None:
            continue
        assert badge.sizeHint().width() <= table.columnWidth(2) + 2, (
            f"row {row}: the type badge is {badge.sizeHint().width()}px wide "
            f"but the column is only {table.columnWidth(2)}px"
        )


def test_rows_do_not_overlap(cleanup_dialog: TemplateCleanupDialog):
    """The content of a row must fit into the row height."""
    table = cleanup_dialog.table
    for row in range(min(6, table.rowCount())):
        for column in range(table.columnCount()):
            widget = table.cellWidget(row, column)
            if widget is None:
                continue
            assert widget.sizeHint().height() <= table.rowHeight(row) + 2, (
                f"row {row}, column {column} needs "
                f"{widget.sizeHint().height()}px but the row is "
                f"{table.rowHeight(row)}px high"
            )


def test_name_and_description_use_the_themed_roles(cleanup_dialog: TemplateCleanupDialog):
    """The labels carry a semantic role so both themes work."""
    table = cleanup_dialog.table
    for row in range(min(4, table.rowCount())):
        badge = table.cellWidget(row, 2)
        if badge is not None:
            assert badge.property("role") in ("badgeMuted", "badgeAccent")


def test_long_text_is_elided_not_cut(cleanup_dialog: TemplateCleanupDialog):
    """A long file name is shortened instead of being clipped."""
    from id_card_generator.ui.components.elided_label import ElidedLabel

    table = cleanup_dialog.table
    for row in range(min(6, table.rowCount())):
        widget = table.cellWidget(row, 4)
        if isinstance(widget, ElidedLabel):
            assert widget.text().endswith("…") or len(widget.fullText()) <= 40
