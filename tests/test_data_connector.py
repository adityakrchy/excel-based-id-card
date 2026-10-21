"""Tests for the Excel & CSV connector.

The connector is the first workspace of the production pipeline.  It has to

* list the placeholders of the template with their mapping state and whether
  they are required,
* infer the type of every column and offer it in the mapping inspector,
* let the operator bind the photo lookup and choose the policy for missing
  photographs,
* show the imported records in a virtual table that can be filtered.
"""

from pathlib import Path

import pandas as pd
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from id_card_generator.core.constants import MissingPhotoPolicy
from id_card_generator.core.models import SourceRecord
from id_card_generator.ui.components.layout_blocks import StatLine
from id_card_generator.ui.components.record_table import RecordTableModel
from id_card_generator.ui.data_source_page import DataSourcePage


@pytest.fixture
def spreadsheet(tmp_path: Path) -> Path:
    path = tmp_path / "staff.xlsx"
    pd.DataFrame(
        {
            "PIN Number": ["100001", "100002", "100003"],
            "Employee ID": ["EMP-77", "EMP-78", "EMP-79"],
            "Name": ["Aditya Sharma", "Priya Patel", "Ravi Kumar"],
            "Grade": [1, 2, 3],
            "Salary": [1200.5, 1300.25, 1400.0],
            "Joined On": ["2024-01-05", "2024-02-06", "2024-03-07"],
            "Photo": ["a.png", "b.jpg", "c.png"],
        }
    ).to_excel(path, index=False)
    return path


@pytest.fixture
def page(qtbot, spreadsheet: Path) -> DataSourcePage:
    connector = DataSourcePage()
    qtbot.addWidget(connector)
    connector.load_file(spreadsheet, copy_to_workspace=False)
    return connector


# ---------------------------------------------------------------------------
# The placeholders
# ---------------------------------------------------------------------------
def test_the_placeholders_show_their_state(qtbot):
    """Every placeholder is listed with its mapping and its tag."""
    connector = DataSourcePage()
    qtbot.addWidget(connector)

    connector.field_mappings["pin_number"] = "PIN Number"
    connector._refresh_placeholders_list()

    assert connector.list_placeholders.count() == len(connector.template_tokens)

    # The token is stored on the item, so the inspector can pick it up.
    item = connector.list_placeholders.item(0)
    assert item.data(Qt.UserRole) == "pin_number"

    # The row that carries the widget shows the mapping.
    row = connector.list_placeholders.itemWidget(item)
    assert row is not None
    labels = [label.text() for label in row.findChildren(QLabel)]
    assert "{{pin_number}}" in labels
    assert "Mapped → PIN Number" in labels
    assert "REQ" in labels


def test_a_required_placeholder_is_tagged(qtbot):
    """The pin is required, the department is not."""
    connector = DataSourcePage()
    qtbot.addWidget(connector)

    assert connector._is_required("pin_number") is True
    assert connector._is_required("employee_name") is True
    assert connector._is_required("department") is False

    # The toggle of the rules box remembers the choice.
    connector.lbl_active_token.setText("{{department}}")
    connector.chk_required.setChecked(False)
    connector.chk_required.setChecked(True)
    assert connector._is_required("department") is True


def test_the_token_is_picked_up_by_the_inspector(page: DataSourcePage):
    """Clicking a placeholder loads it into the mapping inspector."""
    item = page.list_placeholders.item(0)
    page._on_placeholder_clicked(item)

    token = page.lbl_active_token.text()
    assert token.startswith("{{")
    assert page.lbl_token_detail.text()


# ---------------------------------------------------------------------------
# The column types
# ---------------------------------------------------------------------------
def test_the_column_types_are_inferred(page: DataSourcePage):
    """The type of every column is guessed from the values."""
    types = page.column_types

    assert types["PIN Number"] == "[Integer]"
    assert types["Name"] == "[String]"
    assert types["Grade"] == "[Integer]"
    assert types["Salary"] == "[Decimal]"
    assert types["Joined On"] == "[Date]"
    assert types["Photo"] == "[Image Path]"


def test_the_source_column_combo_carries_the_type(page: DataSourcePage):
    """The mapping inspector shows the type next to the column."""
    index = page.cmb_source_column.findData("Grade")
    assert index >= 0
    assert "[Integer]" in page.cmb_source_column.itemText(index)


def test_the_selected_column_reports_its_type(page: DataSourcePage):
    """Choosing a column shows the inferred type."""
    page.lbl_active_token.setText("{{grade}}")
    index = page.cmb_source_column.findData("Grade")
    page.cmb_source_column.setCurrentIndex(index)

    assert "[Integer]" in page.lbl_column_type.text()


# ---------------------------------------------------------------------------
# The photo lookup and the policy
# ---------------------------------------------------------------------------
def test_the_photo_lookup_offers_every_column(page: DataSourcePage):
    """The photos can be looked up by any column of the sheet."""
    data = [page.cmb_photo_lookup.itemData(i) for i in range(page.cmb_photo_lookup.count())]
    assert data[0] == ""
    for column in ("PIN Number", "Employee ID", "Name"):
        assert column in data


def test_the_photo_lookup_change_is_published(page: DataSourcePage):
    """Picking a lookup column publishes the change."""
    seen = []
    page.photo_lookup_changed.connect(seen.append)

    index = page.cmb_photo_lookup.findData("Employee ID")
    page.cmb_photo_lookup.setCurrentIndex(index)

    assert seen == ["Employee ID"]
    assert page.photo_lookup_column == "Employee ID"


def test_the_photo_policy_is_published(page: DataSourcePage):
    """Choosing the policy for missing photographs publishes the change."""
    seen = []
    page.photo_policy_changed.connect(seen.append)

    index = page.cmb_photo_policy.findData(MissingPhotoPolicy.FAIL_RECORD)
    page.cmb_photo_policy.setCurrentIndex(index)

    assert seen == [MissingPhotoPolicy.FAIL_RECORD]


def test_the_photo_stats_are_shown(page: DataSourcePage):
    """The connector reports how the photographs were found."""
    page.set_photo_stats(matched=120, missing=4, ambiguous=2)
    assert "Matched 120" in page.lbl_photo_stats.text()
    assert "Missing 4" in page.lbl_photo_stats.text()
    assert "Ambiguous 2" in page.lbl_photo_stats.text()


# ---------------------------------------------------------------------------
# The record table
# ---------------------------------------------------------------------------
def test_the_table_shows_the_records(page: DataSourcePage):
    """The imported records are listed in the virtual table."""
    assert page.record_model.rowCount() == 3
    # Row, Status, PIN and one column per spreadsheet column except the PIN.
    assert page.record_model.columnCount() == 3 + len(page.columns) - 1


def test_the_table_filters_the_records(page: DataSourcePage):
    """The search only keeps the matching records."""
    page.txt_search.setText("Priya")

    assert page.record_model.rowCount() == 1
    assert "1 of 3" in page.lbl_summary.text()


def test_the_row_number_is_the_spreadsheet_row(page: DataSourcePage):
    """The first column shows the row of the sheet, not the index of the view."""
    record = page.record_model.record_at(0)
    assert record is not None

    index = page.record_model.index(0, 0)
    assert page.record_model.data(index, Qt.DisplayRole) == str(record.row_index + 1)


def test_the_model_marks_the_missing_pin(qtbot):
    """A record without a PIN is flagged in the table."""
    model = RecordTableModel()
    records = [
        SourceRecord(row_index=0, raw_pin="", pin="", data={"Name": "No PIN"}),
        SourceRecord(row_index=1, raw_pin="2", pin="2", data={"Name": "Fine"}),
    ]
    model.set_records(records, ["Name"])

    status = model.data(model.index(0, 1), Qt.DisplayRole)
    assert status == "MISSING PIN"
    assert model.data(model.index(1, 1), Qt.DisplayRole) == "VALID"


# ---------------------------------------------------------------------------
# The connection state
# ---------------------------------------------------------------------------
def test_the_connection_is_described(page: DataSourcePage):
    """The centre column names the sheet and the number of records."""
    assert "Connected" in page.lbl_connection.text()
    assert "3" in page.lbl_connection.text()


def test_the_mapping_tools_are_visible(page: DataSourcePage):
    """Auto-map and validate are real buttons on the screen."""
    assert not page.btn_automap.isHidden()
    assert not page.btn_validate.isHidden()


def test_auto_map_fills_the_placeholders(page: DataSourcePage):
    """The magic button maps the columns by name."""
    page.field_mappings.clear()
    page._auto_map_columns()

    assert page.field_mappings.get("pin_number") == "PIN Number"
    assert page.field_mappings.get("employee_name") == "Name"


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------
def test_the_stat_line_does_not_keep_stale_labels(qtbot):
    """Refreshing the statistics must not leave the old labels behind.

    The old labels kept painting over the new ones, so the numbers of two
    statistics were drawn on top of each other.
    """
    line = StatLine()
    qtbot.addWidget(line)

    line.set_stats([("Fields", 5), ("Records", 0)])
    line.set_stats([("Fields", 5), ("Records", 120)])

    labels = [
        child
        for child in line.findChildren(type(line._labels[0]))
        if child.text() in ("RECORDS", "120")
    ]
    assert len(labels) == 2
    assert all(child.parent() is line for child in labels)

    # The old label is detached, so it cannot paint over the new one.
    texts = [child.text() for child in line._labels]
    assert texts == ["5", "120"]
