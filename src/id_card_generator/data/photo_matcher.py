"""Matching engine pairing spreadsheet records with photographs via PIN Number."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from id_card_generator.core.constants import MatchStatus
from id_card_generator.core.models import PhotoMatchResult, SourceRecord
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
    """Matches records against scanned photograph index with override support."""

    def __init__(self) -> None:
        self.photo_dir: Optional[Path] = None
        self.index: Dict[str, List[Path]] = {}
        self.overrides: Dict[str, str] = {}  # pin -> photo_path

    def set_directory(self, photo_dir: Path) -> None:
        """Set photo directory and scan it."""
        self.photo_dir = photo_dir
        self.rescan()

    def rescan(self) -> None:
        """Rescan current photo directory."""
        if self.photo_dir and self.photo_dir.exists():
            self.index = PhotoScanner.scan_directory(self.photo_dir)
        else:
            self.index = {}

    def set_override(self, pin: str, photo_path: str) -> None:
        """Manually associate a specific photo with a PIN."""
        self.overrides[pin] = photo_path

    def remove_override(self, pin: str) -> None:
        """Remove a manual photo override."""
        self.overrides.pop(pin, None)

    def match_record(self, record: SourceRecord) -> PhotoMatchResult:
        """Match a single record to its photograph."""
        pin = record.pin
        if not pin:
            return PhotoMatchResult(
                pin=pin,
                status=MatchStatus.MISSING,
                details="Record has no PIN Number",
            )

        # Check manual override first
        if pin in self.overrides:
            override_path = Path(self.overrides[pin])
            if override_path.exists():
                return PhotoMatchResult(
                    pin=pin,
                    status=MatchStatus.OVERRIDDEN,
                    photo_path=str(override_path),
                    is_overridden=True,
                    details=f"Manually overridden: {override_path.name}",
                )
            else:
                # Override file was moved or deleted
                logger.warning("Override photo file missing: %s", override_path)

        # Look up in index
        candidates = self.index.get(pin, [])

        if len(candidates) == 1:
            return PhotoMatchResult(
                pin=pin,
                status=MatchStatus.MATCHED,
                photo_path=str(candidates[0]),
                details=f"Matched {candidates[0].name}",
            )
        elif len(candidates) > 1:
            return PhotoMatchResult(
                pin=pin,
                status=MatchStatus.AMBIGUOUS,
                candidate_paths=[str(p) for p in candidates],
                details=f"Ambiguous: {len(candidates)} photos found ({', '.join(p.name for p in candidates)})",
            )
        else:
            return PhotoMatchResult(
                pin=pin,
                status=MatchStatus.MISSING,
                details=f"No photo found for PIN '{pin}'",
            )

    def match_all(self, records: List[SourceRecord]) -> Tuple[Dict[str, PhotoMatchResult], MatchSummary]:
        """Match all records and generate a comprehensive summary."""
        results: Dict[str, PhotoMatchResult] = {}
        summary = MatchSummary()
        summary.total_records = len(records)

        matched_pins: Set[str] = set()

        for r in records:
            res = self.match_record(r)
            results[r.record_id] = res

            if res.status == MatchStatus.MATCHED:
                summary.matched_count += 1
                matched_pins.add(r.pin)
            elif res.status == MatchStatus.OVERRIDDEN:
                summary.overridden_count += 1
                matched_pins.add(r.pin)
            elif res.status == MatchStatus.AMBIGUOUS:
                summary.ambiguous_count += 1
            else:
                summary.missing_count += 1

        # Detect unassigned photos in directory
        for stem, paths in self.index.items():
            if stem not in matched_pins:
                summary.unassigned_photos_count += len(paths)
                summary.unassigned_photo_paths.extend(paths)

        return results, summary
