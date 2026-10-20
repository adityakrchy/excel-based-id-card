"""Matching engine pairing spreadsheet records with photographs via arbitrary key column or PIN."""

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from id_card_generator.core.constants import MatchStatus
from id_card_generator.core.models import PhotoMatchResult, SourceRecord
from id_card_generator.data.data_normalizer import DataNormalizer
from id_card_generator.data.photo_scanner import PhotoScanner

logger = logging.getLogger(__name__)


def _chunks(items: List, size: int):
    """Yield consecutive slices of ``items``."""
    for start in range(0, len(items), size):
        yield items[start:start + size]


# Records above this count are matched on a thread pool.  Below it the
# thread hand-off costs more than it saves.
PARALLEL_MATCH_THRESHOLD = 2000

# Upper bound of worker threads used for matching.
MAX_MATCH_WORKERS = 8


class MatchSummary:
    """Summary metrics of photograph matching."""
    def __init__(self) -> None:
        self.total_records: int = 0
        self.matched_count: int = 0
        self.missing_count: int = 0
        self.ambiguous_count: int = 0
        self.overridden_count: int = 0
        self.unassigned_photos_count: int = 0
        self.unassigned_photo_paths: List[Path] = []


class PhotoMatcher:
    """Matches records against scanned photograph index with generic key column, prefix/suffix and override support."""

    def __init__(self) -> None:
        self.photo_dir: Optional[Path] = None
        self.index: Dict[str, List[str]] = {}
        self.lower_index: Dict[str, List[str]] = {}
        self.overrides: Dict[str, str] = {}  # record_id or key_val -> photo_path
        self.key_column: Optional[str] = None
        self.prefix: str = ""
        self.suffix: str = ""

    def set_directory(self, photo_dir: Path) -> None:
        """Set photo directory and scan it."""
        self.photo_dir = photo_dir
        self.rescan()

    def set_key_column(self, column_name: Optional[str]) -> None:
        """Set spreadsheet column used as photo lookup key."""
        self.key_column = column_name

    def set_affixes(self, prefix: str = "", suffix: str = "") -> None:
        """Configure filename prefix and suffix rules."""
        self.prefix = prefix or ""
        self.suffix = suffix or ""

    def set_indexes(
        self,
        index: Dict[str, List[str]],
        lower_index: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        """Directly update the exact and case-insensitive indexes from background streaming worker."""
        self.index = index
        if lower_index is not None:
            self.lower_index = lower_index
        else:
            # Build the case-insensitive index without the quadratic list
            # membership test of the previous implementation.
            rebuilt: Dict[str, List[str]] = {}
            for stem, paths in self.index.items():
                lower_stem = stem.lower()
                bucket = rebuilt.get(lower_stem)
                if bucket is None:
                    rebuilt[lower_stem] = list(paths)
                else:
                    bucket.extend(paths)
            self.lower_index = rebuilt

    def rescan(self) -> None:
        """Rescan current photo directory and rebuild exact and lower-case lookup indexes."""
        if self.photo_dir and self.photo_dir.exists():
            idx = PhotoScanner.scan_directory(self.photo_dir)
            self.set_indexes(idx)
        else:
            self.index = {}
            self.lower_index = {}

    def set_override(self, key_or_id: str, photo_path: str) -> None:
        """Manually associate a specific photo with a record ID or lookup key."""
        self.overrides[str(key_or_id).strip()] = photo_path

    def remove_override(self, *keys_or_ids: str) -> None:
        """Remove a manual photo override across any matching key, record_id, or pin."""
        targets = set()
        for k in keys_or_ids:
            if k is not None:
                s = str(k).strip()
                if s:
                    targets.add(s)
                    targets.add(s.lower())
                    _, norm = DataNormalizer.normalize_pin(s)
                    if norm:
                        targets.add(norm)
                        targets.add(norm.lower())

        for k in list(self.overrides.keys()):
            k_str = str(k).strip()
            if k_str in targets or k_str.lower() in targets:
                self.overrides.pop(k, None)

    def clear_overrides(self) -> None:
        """Clear all manual overrides."""
        self.overrides.clear()

    def get_lookup_key_value(self, record: SourceRecord) -> str:
        """Extract the lookup key value for a record based on key_column or pin."""
        if self.key_column and self.key_column in record.data:
            raw_val = record.data.get(self.key_column, "")
            _, normalized_val = DataNormalizer.normalize_pin(raw_val)
            return normalized_val
        return record.pin or ""

    def match_record(self, record: SourceRecord) -> PhotoMatchResult:
        """Match a single record to its photograph."""
        key_val = self.get_lookup_key_value(record)
        pin_val = record.pin or key_val

        # 1. Check manual overrides (by record_id first for stability, then by key_val or pin)
        override_target = (
            self.overrides.get(record.record_id)
            or (self.overrides.get(key_val) if key_val else None)
            or (self.overrides.get(pin_val) if pin_val else None)
        )

        if override_target:
            override_path = Path(override_target)
            if override_path.exists():
                return PhotoMatchResult(
                    pin=pin_val,
                    key_value=key_val,
                    record_id=record.record_id,
                    status=MatchStatus.OVERRIDDEN,
                    photo_path=str(override_path),
                    is_overridden=True,
                    details=f"Manually overridden: {override_path.name}",
                )
            else:
                logger.warning("Override photo file missing: %s", override_path)

        if not key_val:
            return PhotoMatchResult(
                pin=pin_val,
                key_value=key_val,
                record_id=record.record_id,
                status=MatchStatus.MISSING,
                details=f"Record has no value for lookup column '{self.key_column or 'PIN Number'}'",
            )

        # 2. Form candidate search patterns
        candidate_stems = [
            f"{self.prefix}{key_val}{self.suffix}",
            key_val,
        ]

        # De-duplicate patterns while preserving order
        patterns = []
        for pat in candidate_stems:
            if pat and pat not in patterns:
                patterns.append(pat)

        # Collect the candidates from the exact and the case-insensitive
        # index.  A set keeps the de-duplication linear.
        found_paths: List[str] = []
        seen: Set[str] = set()
        for pat in patterns:
            for bucket in (self.index.get(pat), self.lower_index.get(pat.lower())):
                if not bucket:
                    continue
                for p in bucket:
                    if p not in seen:
                        seen.add(p)
                        found_paths.append(p)

        if len(found_paths) == 1:
            found = found_paths[0]
            return PhotoMatchResult(
                pin=pin_val,
                key_value=key_val,
                record_id=record.record_id,
                status=MatchStatus.MATCHED,
                photo_path=found,
                details=f"Matched {Path(found).name}",
            )
        elif len(found_paths) > 1:
            return PhotoMatchResult(
                pin=pin_val,
                key_value=key_val,
                record_id=record.record_id,
                status=MatchStatus.AMBIGUOUS,
                candidate_paths=list(found_paths),
                details=(
                    f"Ambiguous: {len(found_paths)} photos found "
                    f"({', '.join(Path(p).name for p in found_paths)})"
                ),
            )
        else:
            return PhotoMatchResult(
                pin=pin_val,
                key_value=key_val,
                record_id=record.record_id,
                status=MatchStatus.MISSING,
                details=f"No photo found for key '{key_val}' (searched: {', '.join(patterns)})",
            )

    def _match_records_parallel(
        self,
        records: List[SourceRecord],
        workers: int,
    ) -> Dict[str, PhotoMatchResult]:
        """Match records on a thread pool and return the results by record id."""
        results: Dict[str, PhotoMatchResult] = {}
        chunk_size = max(256, (len(records) + workers - 1) // workers)

        def _match_chunk(chunk: List[SourceRecord]) -> List[PhotoMatchResult]:
            return [self.match_record(r) for r in chunk]

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for chunk_results in pool.map(_match_chunk, _chunks(records, chunk_size)):
                for res in chunk_results:
                    results[res.record_id] = res
        return results

    def match_all(
        self,
        records: List[SourceRecord],
        workers: int = 0,
    ) -> Tuple[Dict[str, PhotoMatchResult], MatchSummary]:
        """Match all records and generate a comprehensive summary.

        ``workers`` enables multi threaded matching for large datasets; 0
        picks a sensible value automatically.
        """
        summary = MatchSummary()
        summary.total_records = len(records)
        if not records:
            return {}, summary

        if workers <= 0:
            workers = min(MAX_MATCH_WORKERS, (len(records) // PARALLEL_MATCH_THRESHOLD) + 1)
        else:
            workers = max(1, min(workers, MAX_MATCH_WORKERS))

        if workers > 1 and len(records) >= PARALLEL_MATCH_THRESHOLD:
            results = self._match_records_parallel(records, workers)
        else:
            results = {r.record_id: self.match_record(r) for r in records}

        # Collect the matched files.  A set keeps the membership test O(1).
        matched_files: Set[str] = set()
        for res in results.values():
            if res.status in (MatchStatus.MATCHED, MatchStatus.OVERRIDDEN):
                if res.photo_path:
                    matched_files.add(res.photo_path)
            elif res.status == MatchStatus.AMBIGUOUS:
                summary.ambiguous_count += 1
            else:
                summary.missing_count += 1

        summary.matched_count = sum(
            1 for r in results.values() if r.status == MatchStatus.MATCHED
        )
        summary.overridden_count = sum(
            1 for r in results.values() if r.status == MatchStatus.OVERRIDDEN
        )

        # Detect the unassigned photos.  This is linear in the number of
        # photos - the previous list based membership test was quadratic and
        # dominated the runtime for large photo folders.
        unassigned: List[str] = []
        for paths in self.index.values():
            for p in paths:
                if p not in matched_files:
                    unassigned.append(p)

        summary.unassigned_photo_paths = [Path(p) for p in unassigned]
        summary.unassigned_photos_count = len(unassigned)
        return results, summary
