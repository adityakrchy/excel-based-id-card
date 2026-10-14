"""Manages sequential review workflow, per-record approval states, and navigation."""

import datetime
import logging
from typing import Dict, List, Optional
from id_card_generator.core.constants import ReviewStatus
from id_card_generator.core.models import RenderResult, ReviewRecord, SourceRecord

logger = logging.getLogger(__name__)


class ReviewManager:
    """Maintains review records, status updates, navigation, and filtering."""

    def __init__(self) -> None:
        self.records: List[ReviewRecord] = []
        self._record_map: Dict[str, ReviewRecord] = {}  # record_id -> ReviewRecord
        self.current_index: int = 0
        self.filter_status: Optional[ReviewStatus] = None
        self.search_query: str = ""

    def initialize_from_generation(
        self,
        source_records: List[SourceRecord],
        generation_results: List[RenderResult],
        saved_states: Optional[Dict[str, ReviewStatus]] = None,
    ) -> None:
        """Initialize review list from source records and generation results."""
        self.records.clear()
        self._record_map.clear()
        self.current_index = 0

        res_by_id = {res.record_id: res for res in generation_results}
        saved_states = saved_states or {}

        for rec in source_records:
            gen_res = res_by_id.get(rec.record_id)
            status = saved_states.get(rec.record_id, ReviewStatus.PENDING)

            review_item = ReviewRecord(
                record_id=rec.record_id,
                pin=rec.pin,
                name=rec.get_value("Name", ""),
                status=status,
                rendered_image_path=gen_res.image_path if gen_res else None,
            )
            self.records.append(review_item)
            self._record_map[rec.record_id] = review_item

        logger.info("ReviewManager initialized with %d records.", len(self.records))

    def get_filtered_records(self) -> List[ReviewRecord]:
        """Return subset of records matching current filter and search."""
        filtered = self.records

        if self.filter_status is not None:
            filtered = [r for r in filtered if r.status == self.filter_status]

        if self.search_query:
            query = self.search_query.lower().strip()
            filtered = [
                r for r in filtered
                if query in r.pin.lower() or query in r.name.lower()
            ]

        return filtered

    def get_current_record(self) -> Optional[ReviewRecord]:
        """Get record at current index in filtered list."""
        filtered = self.get_filtered_records()
        if not filtered:
            return None
        if self.current_index >= len(filtered):
            self.current_index = max(0, len(filtered) - 1)
        return filtered[self.current_index]

    def next_record(self) -> Optional[ReviewRecord]:
        """Advance to next record in filtered list."""
        filtered = self.get_filtered_records()
        if filtered and self.current_index < len(filtered) - 1:
            self.current_index += 1
        return self.get_current_record()

    def prev_record(self) -> Optional[ReviewRecord]:
        """Return to previous record in filtered list."""
        if self.current_index > 0:
            self.current_index -= 1
        return self.get_current_record()

    def first_record(self) -> Optional[ReviewRecord]:
        """Jump to first record."""
        self.current_index = 0
        return self.get_current_record()

    def last_record(self) -> Optional[ReviewRecord]:
        """Jump to last record."""
        filtered = self.get_filtered_records()
        if filtered:
            self.current_index = len(filtered) - 1
        return self.get_current_record()

    def update_status(
        self,
        record_id: str,
        status: ReviewStatus,
        comments: Optional[str] = None,
    ) -> None:
        """Update review status of a specific record."""
        rec = self._record_map.get(record_id)
        if rec:
            rec.status = status
            rec.comments = comments
            rec.last_reviewed_at = datetime.datetime.now().isoformat()
            logger.debug("Record %s marked as %s", rec.pin, status)

    def invalidate_approval(self, record_id: str) -> None:
        """Invalidate approval when card is regenerated."""
        rec = self._record_map.get(record_id)
        if rec and rec.status == ReviewStatus.APPROVED:
            rec.status = ReviewStatus.PENDING
            logger.info("Approval invalidated for record %s due to regeneration.", rec.pin)

    def batch_approve_all_valid(self) -> int:
        """Mark all generated, non-failed cards as APPROVED."""
        count = 0
        for r in self.records:
            if r.rendered_image_path and r.status != ReviewStatus.REJECTED:
                r.status = ReviewStatus.APPROVED
                count += 1
        return count

    def batch_reject_all(self) -> int:
        """Mark all cards as REJECTED."""
        count = 0
        for r in self.records:
            r.status = ReviewStatus.REJECTED
            count += 1
        return count

    @property
    def counts(self) -> Dict[str, int]:
        """Return count breakdown by status."""
        stats = {
            "total": len(self.records),
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "correction": 0,
            "skipped": 0,
        }
        for r in self.records:
            if r.status == ReviewStatus.APPROVED:
                stats["approved"] += 1
            elif r.status == ReviewStatus.REJECTED:
                stats["rejected"] += 1
            elif r.status == ReviewStatus.CORRECTION:
                stats["correction"] += 1
            elif r.status == ReviewStatus.SKIPPED:
                stats["skipped"] += 1
            else:
                stats["pending"] += 1
        return stats
