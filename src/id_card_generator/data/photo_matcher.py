"""Matching engine pairing spreadsheet records with photographs via arbitrary key column or PIN."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from id_card_generator.core.constants import MatchStatus
from id_card_generator.core.models import PhotoMatchResult, SourceRecord
from id_card_generator.data.data_normalizer import DataNormalizer
from id_card_generator.data.photo_scanner import PhotoScanner

logger = logging.getLogger(__name__)


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
        self.index: Dict[str, List[Path]] = {}
        self.lower_index: Dict[str, List[Path]] = {}
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

    def rescan(self) -> None:
        """Rescan current photo directory and rebuild exact and lower-case lookup indexes."""
        if self.photo_dir and self.photo_dir.exists():
            self.index = PhotoScanner.scan_directory(self.photo_dir)
            self.lower_index = {}
            for stem, paths in self.index.items():
                lower_stem = stem.lower()
                if lower_stem not in self.lower_index:
                    self.lower_index[lower_stem] = []
                for p in paths:
                    if p not in self.lower_index[lower_stem]:
                        self.lower_index[lower_stem].append(p)
        else:
            self.index = {}
            self.lower_index = {}

    def set_override(self, key_or_id: str, photo_path: str) -> None:
        """Manually associate a specific photo with a record ID or lookup key."""
        self.overrides[str(key_or_id).strip()] = photo_path

    def remove_override(self, key_or_id: str) -> None:
        """Remove a manual photo override."""
        self.overrides.pop(str(key_or_id).strip(), None)

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

        found_paths: List[Path] = []
        for pat in patterns:
            # Check exact match
            if pat in self.index:
                for p in self.index[pat]:
                    if p not in found_paths:
                        found_paths.append(p)
            # Check case-insensitive match
            pat_lower = pat.lower()
            if pat_lower in self.lower_index:
                for p in self.lower_index[pat_lower]:
                    if p not in found_paths:
                        found_paths.append(p)

        if len(found_paths) == 1:
            return PhotoMatchResult(
                pin=pin_val,
                key_value=key_val,
                record_id=record.record_id,
                status=MatchStatus.MATCHED,
                photo_path=str(found_paths[0]),
                details=f"Matched {found_paths[0].name}",
            )
        elif len(found_paths) > 1:
            return PhotoMatchResult(
                pin=pin_val,
                key_value=key_val,
                record_id=record.record_id,
                status=MatchStatus.AMBIGUOUS,
                candidate_paths=[str(p) for p in found_paths],
                details=f"Ambiguous: {len(found_paths)} photos found ({', '.join(p.name for p in found_paths)})",
            )
        else:
            return PhotoMatchResult(
                pin=pin_val,
                key_value=key_val,
                record_id=record.record_id,
                status=MatchStatus.MISSING,
                details=f"No photo found for key '{key_val}' (searched: {', '.join(patterns)})",
            )

    def match_all(self, records: List[SourceRecord]) -> Tuple[Dict[str, PhotoMatchResult], MatchSummary]:
        """Match all records and generate a comprehensive summary."""
        results: Dict[str, PhotoMatchResult] = {}
        summary = MatchSummary()
        summary.total_records = len(records)

        matched_files: Set[Path] = set()

        for r in records:
            res = self.match_record(r)
            results[r.record_id] = res

            if res.status == MatchStatus.MATCHED:
                summary.matched_count += 1
                if res.photo_path:
                    matched_files.add(Path(res.photo_path))
            elif res.status == MatchStatus.OVERRIDDEN:
                summary.overridden_count += 1
                if res.photo_path:
                    matched_files.add(Path(res.photo_path))
            elif res.status == MatchStatus.AMBIGUOUS:
                summary.ambiguous_count += 1
            else:
                summary.missing_count += 1

        # Detect unassigned photos in directory
        for stem, paths in self.index.items():
            for p in paths:
                if p not in matched_files and p not in summary.unassigned_photo_paths:
                    summary.unassigned_photo_paths.append(p)

        summary.unassigned_photos_count = len(summary.unassigned_photo_paths)
        return results, summary
