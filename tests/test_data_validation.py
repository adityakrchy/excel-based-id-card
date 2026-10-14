"""Unit tests for data normalization and validation."""

from id_card_generator.core.models import SourceRecord
from id_card_generator.data.data_normalizer import DataNormalizer
from id_card_generator.data.data_validator import DataValidator


def test_data_normalizer_pin():
    # Integer
    raw, norm = DataNormalizer.normalize_pin(12345)
    assert raw == "12345" and norm == "12345"

    # Float .0 stripping
    raw, norm = DataNormalizer.normalize_pin(100001.0)
    assert norm == "100001"

    # String with leading zeros
    raw, norm = DataNormalizer.normalize_pin("00123")
    assert norm == "00123"

    # String with whitespace
    raw, norm = DataNormalizer.normalize_pin("  00456  ")
    assert raw == "  00456  "
    assert norm == "00456"

    # NaN / None
    raw, norm = DataNormalizer.normalize_pin(None)
    assert norm == ""


def test_data_normalizer_sanitize_filename():
    assert DataNormalizer.sanitize_filename('1001_John:Doe*Senior?Manager') == "1001_John_Doe_Senior_Manager"
    assert DataNormalizer.sanitize_filename("..//invalid//..") == "invalid"


def test_data_validator_rules():
    records = [
        SourceRecord(row_index=1, raw_pin="1001", pin="1001", data={"Name": "Alice"}),
        SourceRecord(row_index=2, raw_pin="1002", pin="1002", data={"Name": "Bob"}),
        SourceRecord(row_index=3, raw_pin="1001", pin="1001", data={"Name": "Duplicate Alice"}),
        SourceRecord(row_index=4, raw_pin="", pin="", data={"Name": "No PIN"}),
        SourceRecord(row_index=5, raw_pin=" 1003 ", pin="1003", data={"Name": "Charlie"}),
    ]

    report = DataValidator.validate_records(records, required_fields=["Name"])
    assert report.total_records == 5
    assert report.missing_pins == 1
    assert "1001" in report.duplicate_pins

    # Record 4 has missing PIN error
    assert not records[3].is_valid
    assert "Missing PIN Number" in records[3].validation_errors

    # Record 1 & 3 have duplicate PIN warning
    assert any("Duplicate PIN" in w for w in records[0].validation_warnings)
    assert any("Duplicate PIN" in w for w in records[2].validation_warnings)

    # Record 5 has whitespace warning
    assert any("whitespace" in w for w in records[4].validation_warnings)
