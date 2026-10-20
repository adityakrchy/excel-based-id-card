"""End-to-end test of the data source -> photo lookup chain.

Importing a spreadsheet has to publish the columns and the records, and the
photo library has to offer **every** column for the lookup, so a photo can be
matched by PIN, by employee id or by any other column.
"""

from pathlib import Path

import pandas as pd
import pytest

from id_card_generator.core.models import SourceRecord
from id_card_generator.ui.data_source_page import DataSourcePage
from id_card_generator.ui.photo_library_page import PhotoLibraryPage


@pytest.fixture
def spreadsheet(tmp_path: Path) -> Path:
    path = tmp_path / "staff.xlsx"
    pd.DataFrame(
        {
            "PIN Number": ["100001", "100002"],
            "Employee ID": ["EMP-77", "EMP-78"],
            "Name": ["Aditya Sharma", "Priya Patel"],
        }
    ).to_excel(path, index=False)
    return path


def test_import_publishes_columns_and_records(qtbot, spreadsheet: Path):
    """A successful import must not be swallowed by a display error."""
    page = DataSourcePage()
    qtbot.addWidget(page)

    published = {}
    page.data_loaded.connect(
        lambda cols, records, report: published.update(
            columns=list(cols), records=list(records)
        )
    )

    page.load_file(spreadsheet, copy_to_workspace=False)

    assert published.get("columns"), "the columns were never published"
    assert "PIN Number" in published["columns"]
    assert "Employee ID" in published["columns"]
    assert len(published.get("records", [])) == 2


def test_photo_lookup_offers_every_column(qtbot, spreadsheet: Path):
    """The lookup combo lists every column of the imported sheet."""
    source = DataSourcePage()
    qtbot.addWidget(source)

    photos = PhotoLibraryPage()
    qtbot.addWidget(photos)

    def _on_loaded(columns, records, report):
        photos.set_columns(list(columns))
        photos.set_records(list(records))

    source.data_loaded.connect(_on_loaded)
    source.load_file(spreadsheet, copy_to_workspace=False)

    combo = photos.cmb_key_col
    entries = [combo.itemText(i) for i in range(combo.count())]
    assert "Auto-detect (PIN / ID)" in entries[0]
    for column in ("PIN Number", "Employee ID", "Name"):
        assert column in entries, f"the lookup is missing the column '{column}'"


def test_photo_matching_by_any_column(qtbot, tmp_path: Path):
    """A photo can be found through the column the user picks."""
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    (photo_dir / "EMP-77.jpg").write_bytes(b"photo")

    photos = PhotoLibraryPage()
    qtbot.addWidget(photos)

    records = [
        SourceRecord(
            row_index=0, raw_pin="100001", pin="100001",
            data={"PIN Number": "100001", "Employee ID": "EMP-77", "Name": "Aditya"},
        )
    ]

    photos.set_columns(["PIN Number", "Employee ID", "Name"])
    photos.set_records(records)
    photos.matcher.set_directory(photo_dir)

    def _wait(qtbot, status):
        """Wait until the current card reached the expected status."""
        for _ in range(200):
            result = photos.match_results.get(records[0].record_id)
            if result is not None and result.status.value == status:
                return
            qtbot.wait(25)

    # Match by the PIN - there is no photo with that name.
    photos.matcher.set_key_column("PIN Number")
    _wait(qtbot, "missing")
    assert photos.match_results[records[0].record_id].status.value == "missing"

    # Match by the employee id - the photo is found.
    photos.matcher.set_key_column("Employee ID")
    photos._rematch()
    _wait(qtbot, "matched")
    assert photos.match_results[records[0].record_id].status.value == "matched"
    assert photos.match_results[records[0].record_id].photo_path.endswith("EMP-77.jpg")


def test_lookup_column_change_rematches(qtbot, tmp_path: Path):
    """Changing the lookup column re-runs the matching."""
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    (photo_dir / "100001.jpg").write_bytes(b"photo")

    photos = PhotoLibraryPage()
    qtbot.addWidget(photos)

    records = [
        SourceRecord(
            row_index=0, raw_pin="100001", pin="100001",
            data={"PIN Number": "100001", "Employee ID": "EMP-77"},
        )
    ]
    photos.set_columns(["PIN Number", "Employee ID"])
    photos.set_records(records)
    photos.matcher.set_directory(photo_dir)

    photos.cmb_key_col.setCurrentIndex(2)  # Employee ID
    photos._on_rule_changed()

    for _ in range(200):
        if photos.match_results:
            break
        qtbot.wait(25)

    assert photos.match_results[records[0].record_id].status.value == "missing"
