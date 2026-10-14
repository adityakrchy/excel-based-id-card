"""Unit tests for photograph scanning and matching."""

from pathlib import Path
from id_card_generator.core.constants import MatchStatus
from id_card_generator.core.models import SourceRecord
from id_card_generator.data.photo_matcher import PhotoMatcher


def test_photo_matcher_workflow(sample_photos_dir: Path):
    matcher = PhotoMatcher()
    matcher.set_directory(sample_photos_dir)

    records = [
        # Normal match
        SourceRecord(row_index=1, raw_pin="100001", pin="100001", data={"Name": "Aditya"}),
        # Leading zero match
        SourceRecord(row_index=2, raw_pin="005001", pin="005001", data={"Name": "Ananya"}),
        # Missing photo
        SourceRecord(row_index=3, raw_pin="888888", pin="888888", data={"Name": "Missing Guy"}),
        # Ambiguous photo (100004 has both .jpg and .png)
        SourceRecord(row_index=4, raw_pin="100004", pin="100004", data={"Name": "Sneha"}),
    ]

    results, summary = matcher.match_all(records)

    # Record 1 (100001) -> MATCHED
    assert results[records[0].record_id].status == MatchStatus.MATCHED
    assert results[records[0].record_id].photo_path is not None
    assert "100001.jpg" in results[records[0].record_id].photo_path

    # Record 2 (005001) -> MATCHED (.webp)
    assert results[records[1].record_id].status == MatchStatus.MATCHED
    assert "005001.webp" in results[records[1].record_id].photo_path

    # Record 3 (888888) -> MISSING
    assert results[records[2].record_id].status == MatchStatus.MISSING
    assert results[records[2].record_id].photo_path is None

    # Record 4 (100004) -> AMBIGUOUS (never arbitrarily picks one!)
    assert results[records[3].record_id].status == MatchStatus.AMBIGUOUS
    assert len(results[records[3].record_id].candidate_paths) == 2

    # Unassigned photo (999999.png exists in folder but not in records)
    assert summary.unassigned_photos_count >= 1
    assert any("999999.png" in str(p) for p in summary.unassigned_photo_paths)


def test_photo_override(sample_photos_dir: Path):
    matcher = PhotoMatcher()
    matcher.set_directory(sample_photos_dir)

    # 888888 was missing
    rec = SourceRecord(row_index=1, raw_pin="888888", pin="888888", data={"Name": "Missing Guy"})
    assert matcher.match_record(rec).status == MatchStatus.MISSING

    # Override with 100001.jpg
    override_file = sample_photos_dir / "100001.jpg"
    matcher.set_override("888888", str(override_file))

    res = matcher.match_record(rec)
    assert res.status == MatchStatus.OVERRIDDEN
    assert res.photo_path == str(override_file)
    assert res.is_overridden is True
