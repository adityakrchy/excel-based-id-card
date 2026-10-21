"""Tests for the individual card export.

The export writes one file per card - an entire sheet is never produced
unless the optional printable contact sheet is requested.
"""

from pathlib import Path

import pytest
from PIL import Image

from id_card_generator.core.constants import OutputFormat, ReviewStatus
from id_card_generator.core.models import (
    ExportConfiguration,
    PhotoMatchResult,
    ReviewRecord,
    SourceRecord,
)
from id_card_generator.export.export_manager import ExportManager


def _stage_cards(folder: Path, pins) -> dict:
    """Create rendered card images in the staging folder."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for pin in pins:
        path = folder / f"{pin}.png"
        Image.new("RGB", (200, 120), (30, 60, 120)).save(path)
        paths[pin] = path
    return paths


def _review_records(pins) -> list:
    return [
        ReviewRecord(
            record_id=f"rec-{pin}",
            pin=pin,
            name=f"Person {pin}",
            status=ReviewStatus.APPROVED,
        )
        for pin in pins
    ]


# ---------------------------------------------------------------------------
# One file per card
# ---------------------------------------------------------------------------
def test_export_writes_one_file_per_card(tmp_path: Path):
    """Every approved card becomes its own file."""
    staged = _stage_cards(tmp_path / "staging", ["1001", "1002", "1003"])
    records = _review_records(["1001", "1002", "1003"])
    for record in records:
        record.rendered_image_path = str(staged[record.pin])

    out_dir = tmp_path / "out"
    result = ExportManager.export_batch(
        config=ExportConfiguration(output_dir=str(out_dir)),
        review_records=records,
        source_records_map={},
        match_results_map={},
    )

    assert result.exported_count == 3
    assert len(result.exported_files) == 3
    for path in result.exported_files:
        assert Path(path).exists()
        assert Path(path).suffix == ".png"

    # No sheet was produced.
    assert not list(out_dir.glob("*.pdf"))
    assert len(list(out_dir.glob("*.png"))) == 3


def test_export_skips_unapproved_cards(tmp_path: Path):
    """Only the approved cards are written."""
    staged = _stage_cards(tmp_path / "staging", ["1001", "1002"])
    records = _review_records(["1001", "1002"])
    records[1].status = ReviewStatus.PENDING
    for record in records:
        record.rendered_image_path = str(staged[record.pin])

    result = ExportManager.export_batch(
        config=ExportConfiguration(output_dir=str(tmp_path / "out")),
        review_records=records,
        source_records_map={},
        match_results_map={},
    )

    assert result.exported_count == 1
    assert result.skipped_count == 1


# ---------------------------------------------------------------------------
# File name pattern
# ---------------------------------------------------------------------------
def test_naming_pattern_is_applied(tmp_path: Path):
    """The {PIN_NUMBER} / {NAME} / {ROW} tokens are replaced."""
    staged = _stage_cards(tmp_path / "staging", ["1001"])
    source = SourceRecord(
        row_index=7, raw_pin="1001", pin="1001", data={"Name": "Ada Lovelace"}
    )
    record = ReviewRecord(
        record_id="rec-1",
        pin="1001",
        name="Ada Lovelace",
        status=ReviewStatus.APPROVED,
        rendered_image_path=str(staged["1001"]),
    )

    config = ExportConfiguration(
        output_dir=str(tmp_path / "out"),
        naming_pattern="{ROW}-{PIN_NUMBER}-{NAME}",
    )
    result = ExportManager.export_batch(
        config=config,
        review_records=[record],
        source_records_map={record.record_id: source},
        match_results_map={},
    )

    assert result.exported_count == 1
    assert Path(result.exported_files[0]).name == "7-1001-Ada Lovelace.png"


def test_invalid_naming_pattern_falls_back(tmp_path: Path):
    """An unknown token must not break the export."""
    staged = _stage_cards(tmp_path / "staging", ["1001"])
    record = ReviewRecord(
        record_id="rec-1",
        pin="1001",
        name="Ada",
        status=ReviewStatus.APPROVED,
        rendered_image_path=str(staged["1001"]),
    )

    config = ExportConfiguration(
        output_dir=str(tmp_path / "out"),
        naming_pattern="{NOT_A_TOKEN}",
    )
    result = ExportManager.export_batch(
        config=config,
        review_records=[record],
        source_records_map={},
        match_results_map={},
    )

    assert result.exported_count == 1
    assert Path(result.exported_files[0]).exists()


def test_duplicate_names_do_not_overwrite(tmp_path: Path):
    """Two cards with the same name keep both files."""
    staged = _stage_cards(tmp_path / "staging", ["1001", "1002"])
    records = _review_records(["1001", "1002"])
    for record in records:
        record.name = "Same Name"
        record.rendered_image_path = str(staged[record.pin])

    out_dir = tmp_path / "out"
    result = ExportManager.export_batch(
        config=ExportConfiguration(output_dir=str(out_dir)),
        review_records=records,
        source_records_map={},
        match_results_map={},
    )

    assert result.exported_count == 2
    assert len(set(result.exported_files)) == 2
    assert len(list(out_dir.glob("*.png"))) == 2


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------
def test_jpeg_export_converts_the_cards(tmp_path: Path):
    """Selecting JPEG re-encodes the cards."""
    staged = _stage_cards(tmp_path / "staging", ["1001"])
    record = ReviewRecord(
        record_id="rec-1",
        pin="1001",
        name="Ada",
        status=ReviewStatus.APPROVED,
        rendered_image_path=str(staged["1001"]),
    )

    out_dir = tmp_path / "out"
    result = ExportManager.export_batch(
        config=ExportConfiguration(
            output_dir=str(out_dir), format=OutputFormat.JPEG, jpeg_quality=80
        ),
        review_records=[record],
        source_records_map={},
        match_results_map={},
    )

    assert result.exported_count == 1
    exported = Path(result.exported_files[0])
    assert exported.suffix == ".jpg"
    with Image.open(exported) as image:
        assert image.format == "JPEG"


# ---------------------------------------------------------------------------
# Optional artifacts
# ---------------------------------------------------------------------------
def test_contact_sheet_is_optional(tmp_path: Path):
    """The printable sheet is only produced when it is requested."""
    staged = _stage_cards(tmp_path / "staging", ["1001", "1002"])
    records = _review_records(["1001", "1002"])
    for record in records:
        record.rendered_image_path = str(staged[record.pin])

    out_dir = tmp_path / "out"
    result = ExportManager.export_batch(
        config=ExportConfiguration(output_dir=str(out_dir)),
        review_records=records,
        source_records_map={},
        match_results_map={},
    )
    assert result.contact_sheet_path is None
    assert not (out_dir / "contact_sheet.pdf").exists()

    result = ExportManager.export_batch(
        config=ExportConfiguration(
            output_dir=str(out_dir), export_contact_sheet=True, sheet_columns=3, sheet_rows=2
        ),
        review_records=records,
        source_records_map={},
        match_results_map={},
    )
    assert result.contact_sheet_path is not None
    assert Path(result.contact_sheet_path).exists()


def test_manifest_is_written(tmp_path: Path):
    """The audit manifest lists every exported card."""
    staged = _stage_cards(tmp_path / "staging", ["1001", "1002"])
    records = _review_records(["1001", "1002"])
    for record in records:
        record.rendered_image_path = str(staged[record.pin])

    result = ExportManager.export_batch(
        config=ExportConfiguration(output_dir=str(tmp_path / "out")),
        review_records=records,
        source_records_map={},
        match_results_map={},
    )

    assert result.manifest_path is not None
    content = Path(result.manifest_path).read_text(encoding="utf-8")
    assert "1001" in content and "1002" in content


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def test_export_page_lists_the_files(qtbot, tmp_path: Path):
    """The page previews the file names that are going to be written."""
    from id_card_generator.ui.export_page import ExportPage

    staged = _stage_cards(tmp_path / "staging", ["1001", "1002"])
    records = _review_records(["1001", "1002"])
    for record in records:
        record.rendered_image_path = str(staged[record.pin])

    page = ExportPage()
    qtbot.addWidget(page)
    page.show()
    page.set_export_context(records, {}, {})

    # The pattern preview shows an example file name.
    assert "1001" in page.lbl_pattern_hint.text()

    # The export button counts the cards.
    assert "2" in page.btn_execute_export.text()


def test_export_page_honours_the_format_setting(qtbot):
    """Switching to JPEG enables the quality slider and updates the ribbon."""
    from id_card_generator.ui.export_page import ExportPage

    page = ExportPage()
    qtbot.addWidget(page)
    page.show()

    assert not page.slider_quality.isEnabled()
    page.cmb_format.setCurrentIndex(1)
    assert page.slider_quality.isEnabled()
    assert "JPEG" in page.pill_format.text()


def test_export_page_sheet_settings_are_optional(qtbot):
    """The imposition controls only appear for the optional contact sheet."""
    from id_card_generator.ui.export_page import ExportPage

    page = ExportPage()
    qtbot.addWidget(page)
    page.show()

    assert not page.sheet_box.isVisible()
    page.chk_contact_sheet.setChecked(True)
    assert page.sheet_box.isVisible()


# ---------------------------------------------------------------------------
# The filter of the cards that are written
# ---------------------------------------------------------------------------
def _records(count: int = 6):
    """Reviewed cards with a department."""
    from PySide6.QtCore import Qt

    from id_card_generator.core.constants import ReviewStatus
    from id_card_generator.core.models import ReviewRecord, SourceRecord

    records = []
    sources = {}
    for index in range(count):
        source = SourceRecord(
            row_index=index,
            raw_pin=f"EMP{index}",
            pin=f"EMP{index}",
            data={
                "PIN Number": f"EMP{index}",
                "Name": f"Employee {index}",
                "Department": ["Engineering", "Accounts"][index % 2],
            },
        )
        sources[source.record_id] = source
        records.append(
            ReviewRecord(
                record_id=source.record_id,
                pin=source.pin,
                name=f"Employee {index}",
                status=ReviewStatus.APPROVED,
            )
        )
    return records, sources


def test_the_export_lists_the_cards(qtbot, tmp_path):
    """The table of the export shows the cards that are written."""
    from id_card_generator.ui.export_page import ExportPage

    page = ExportPage()
    qtbot.addWidget(page)

    records, sources = _records()
    page.set_export_context(records, sources, {})

    assert page.card_model.rowCount() == 6
    assert page.card_model.columnCount() >= 5
    assert "6 of 6" in page.lbl_table_info.text()


def test_a_column_of_the_export_can_be_filtered(qtbot, tmp_path):
    """Only the cards that pass the filter are written."""
    from PySide6.QtCore import Qt

    from id_card_generator.core.constants import ReviewStatus
    from id_card_generator.ui.export_page import ExportPage

    page = ExportPage()
    qtbot.addWidget(page)

    records, sources = _records()
    # Two cards are not approved, so the policy leaves four.
    records[0].status = ReviewStatus.PENDING
    records[1].status = ReviewStatus.PENDING
    page.set_export_context(records, sources, {})

    assert page.card_model.rowCount() == 4

    department = None
    for column in range(page.card_model.columnCount()):
        if page.card_model.headerData(column, Qt.Horizontal) == "Department":
            department = column
            break
    assert department is not None

    page.card_model.set_column_filter(department, {"Engineering"})
    page._on_filters_changed()

    assert page.card_model.rowCount() == 2
    assert "2 of 6" in page.lbl_table_info.text()
    assert "2 Cards" in page.btn_execute_export.text()


def test_the_filters_survive_a_refresh(qtbot):
    """The filter of a column stays when the table is filled again."""
    from PySide6.QtCore import Qt

    from id_card_generator.ui.export_page import ExportPage

    page = ExportPage()
    qtbot.addWidget(page)

    records, sources = _records()
    page.set_export_context(records, sources, {})

    department = None
    for column in range(page.card_model.columnCount()):
        if page.card_model.headerData(column, Qt.Horizontal) == "Department":
            department = column
            break

    page.card_model.set_column_filter(department, {"Engineering"})
    page._refresh_export_list()

    assert page.card_model.rowCount() == 3
    assert page.card_model.is_filtered(department) is True


def test_the_file_name_belongs_to_its_card(qtbot):
    """Every row shows the name of the file it is written to."""
    from PySide6.QtCore import Qt

    from id_card_generator.ui.export_page import ExportPage

    page = ExportPage()
    qtbot.addWidget(page)

    records, sources = _records()
    page.set_export_context(records, sources, {})

    model = page.card_model
    file_column = None
    for column in range(model.columnCount()):
        if model.headerData(column, Qt.Horizontal) == "File":
            file_column = column
            break
    assert file_column is not None

    for row in range(model.rowCount()):
        name = model.data(model.index(row, file_column))
        pin = model.data(model.index(row, 2))
        assert name.startswith(pin)
