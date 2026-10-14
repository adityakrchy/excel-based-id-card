"""Unit tests for sequential review and approval workflow."""

from id_card_generator.core.constants import ReviewStatus
from id_card_generator.core.models import RenderResult, SourceRecord
from id_card_generator.review.review_manager import ReviewManager


def test_review_manager_workflow():
    records = [
        SourceRecord(row_index=1, raw_pin="1001", pin="1001", data={"Name": "Alice"}),
        SourceRecord(row_index=2, raw_pin="1002", pin="1002", data={"Name": "Bob"}),
        SourceRecord(row_index=3, raw_pin="1003", pin="1003", data={"Name": "Charlie"}),
    ]

    gen_results = [
        RenderResult(record_id=records[0].record_id, pin="1001", success=True, image_path="/staging/1001.png"),
        RenderResult(record_id=records[1].record_id, pin="1002", success=True, image_path="/staging/1002.png"),
        RenderResult(record_id=records[2].record_id, pin="1003", success=False, error_message="Error"),
    ]

    manager = ReviewManager()
    manager.initialize_from_generation(records, gen_results)

    # Initial state
    counts = manager.counts
    assert counts["total"] == 3
    assert counts["pending"] == 3
    assert counts["approved"] == 0

    # Navigation
    curr = manager.get_current_record()
    assert curr is not None and curr.pin == "1001"

    manager.next_record()
    assert manager.get_current_record().pin == "1002"

    # Approve record 1
    manager.update_status(records[0].record_id, ReviewStatus.APPROVED)
    assert manager.counts["approved"] == 1

    # Invalidate approval on regeneration
    manager.invalidate_approval(records[0].record_id)
    assert manager.counts["approved"] == 0
    assert manager.counts["pending"] == 3

    # Batch approve valid
    count = manager.batch_approve_all_valid()
    assert count == 2  # Only record 0 and 1 have rendered_image_path
    assert manager.counts["approved"] == 2
