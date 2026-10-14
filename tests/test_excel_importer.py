"""Unit tests for Excel and CSV data importing."""

from pathlib import Path
import pytest
from id_card_generator.core.exceptions import DataSourceError
from id_card_generator.data.excel_importer import ExcelImporter


def test_get_sheet_names(sample_excel_file: Path):
    sheets = ExcelImporter.get_sheet_names(sample_excel_file)
    assert "Employees" in sheets
    assert "Contractors" in sheets


def test_import_excel_data(sample_excel_file: Path):
    columns, records = ExcelImporter.import_data(sample_excel_file, sheet_name="Employees")
    assert len(records) == 7
    assert "PIN Number" in columns
    assert "Name" in columns
    assert "Designation" in columns

    # Verify first record
    rec0 = records[0]
    assert rec0.pin == "100001"
    assert rec0.get_value("Name") == "Aditya Sharma"
    assert rec0.get_value("Designation") == "Senior Engineer"

    # Verify leading zero preservation on "005001"
    rec4 = records[4]
    assert rec4.pin == "005001"
    assert rec4.get_value("Name") == "Ananya Das"

    # Verify whitespace normalization on "  100003  "
    rec2 = records[2]
    assert rec2.raw_pin == "  100003  "
    assert rec2.pin == "100003"


def test_import_csv_data(sample_csv_file: Path):
    sheets = ExcelImporter.get_sheet_names(sample_csv_file)
    assert sheets == ["Default"]

    columns, records = ExcelImporter.import_data(sample_csv_file)
    assert len(records) == 3
    assert records[2].pin == "009999"


def test_nonexistent_file():
    with pytest.raises(DataSourceError):
        ExcelImporter.import_data(Path("/nonexistent/file.xlsx"))
