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


def test_generic_column_matching(sample_photos_dir: Path):
    matcher = PhotoMatcher()
    matcher.set_directory(sample_photos_dir)
    matcher.set_key_column("EmpCode")

    # Record using arbitrary EmpCode column instead of PIN
    rec = SourceRecord(
        row_index=1,
        raw_pin="",
        pin="",
        data={"EmpCode": "100001", "Name": "Aditya"}
    )
    res = matcher.match_record(rec)
    assert res.status == MatchStatus.MATCHED
    assert res.photo_path is not None
    assert "100001.jpg" in res.photo_path


def test_stable_record_id_override_across_reordering(sample_photos_dir: Path):
    matcher = PhotoMatcher()
    matcher.set_directory(sample_photos_dir)

    rec_a = SourceRecord(row_index=1, raw_pin="999001", pin="999001", data={"Name": "Person A"})
    rec_b = SourceRecord(row_index=2, raw_pin="999002", pin="999002", data={"Name": "Person B"})

    override_file = sample_photos_dir / "100001.jpg"
    # Associate override with stable record_id
    matcher.set_override(rec_a.record_id, str(override_file))

    # Reorder records (rec_a now row 2)
    reordered_a = SourceRecord(
        record_id=rec_a.record_id,
        row_index=2,
        raw_pin="999001",
        pin="999001",
        data={"Name": "Person A"}
    )
    res_a = matcher.match_record(reordered_a)
    assert res_a.status == MatchStatus.OVERRIDDEN
    assert res_a.photo_path == str(override_file)

    res_b = matcher.match_record(rec_b)
    assert res_b.status == MatchStatus.MISSING


def test_clear_photo_override_multi_keys(sample_photos_dir: Path):
    """Verify that removing an override across record_id, key_val, and pin completely clears it."""
    matcher = PhotoMatcher()
    matcher.set_directory(sample_photos_dir)

    rec = SourceRecord(row_index=1, raw_pin="888888", pin="888888", data={"Name": "Missing Guy"})
    # Initially missing
    assert matcher.match_record(rec).status == MatchStatus.MISSING

    # Override on record_id, pin, and key_val
    override_file = sample_photos_dir / "100001.jpg"
    matcher.set_override(rec.record_id, str(override_file))
    matcher.set_override(rec.pin, str(override_file))
    matcher.set_override("888888", str(override_file))

    res = matcher.match_record(rec)
    assert res.status == MatchStatus.OVERRIDDEN

    # Now clear override using all associated identifiers
    matcher.remove_override(rec.record_id, "888888", rec.pin)

    # Must cleanly revert back to MISSING (or original non-overridden match)
    res_cleared = matcher.match_record(rec)
    assert res_cleared.status == MatchStatus.MISSING
    assert res_cleared.is_overridden is False
    assert res_cleared.photo_path is None

