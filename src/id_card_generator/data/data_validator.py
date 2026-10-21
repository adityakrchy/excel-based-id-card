"""Spreadsheet data validation and integrity verification."""

from collections import Counter
from typing import Dict, List, Optional, Tuple
from id_card_generator.core.models import SourceRecord


class ValidationReport:
    """Summary of data validation analysis."""
    def __init__(self) -> None:
        self.total_records: int = 0
        self.valid_records: int = 0
        self.records_with_errors: int = 0
        self.records_with_warnings: int = 0
        self.missing_pins: int = 0
        self.duplicate_pins: Dict[str, int] = {}
        self.empty_fields_count: Dict[str, int] = {}


class DataValidator:
    """Validates records for missing keys, duplicates, and format warnings."""

    @staticmethod
    def analyze_records(
        records: List[SourceRecord],
        required_fields: Optional[List[str]] = None,
        allow_empty_non_essential: bool = True,
    ) -> Tuple[ValidationReport, List[Tuple[List[str], List[str]]]]:
        """Analyze records WITHOUT mutating them.

        Duplication detection needs a global PIN counter, so it runs once over
        the whole dataset (typically on a worker thread at the end of the load
        pipeline). Per-record error/warning lists are returned as tuples and
        applied by the GUI thread afterwards - ``RecordTableModel`` paints the
        status column from those very lists, which makes mutating them in a
        worker a data race.

        Returns:
            ``(report, annotations)`` where ``annotations[i]`` is
            ``(errors, warnings)`` for ``records[i]``.
        """
        report = ValidationReport()
        report.total_records = len(records)

        # Count occurrences of non-empty normalized PINs
        pin_counter = Counter(r.pin for r in records if r.pin)

        for pin, count in pin_counter.items():
            if count > 1:
                report.duplicate_pins[pin] = count

        annotations: List[Tuple[List[str], List[str]]] = []
        for r in records:
            errors: List[str] = []
            warnings: List[str] = []

            # 1. Missing PIN validation
            if not r.pin:
                errors.append("Missing PIN Number")
                report.missing_pins += 1

            # 2. Duplicate PIN validation
            elif pin_counter[r.pin] > 1:
                warnings.append(
                    f"Duplicate PIN Number '{r.pin}' (found in {pin_counter[r.pin]} records)"
                )

            # 3. Accidental whitespace warning
            if r.raw_pin and r.raw_pin != r.pin:
                warnings.append(
                    f"PIN contained accidental surrounding whitespace (raw: '{r.raw_pin}')"
                )

            # 4. Required fields check
            if required_fields:
                for field in required_fields:
                    val = r.get_value(field)
                    if not val:
                        msg = f"Missing required field '{field}'"
                        if allow_empty_non_essential and field.lower() != "pin number":
                            warnings.append(msg)
                        else:
                            errors.append(msg)

            # Record metrics
            if not errors:
                report.valid_records += 1
            else:
                report.records_with_errors += 1

            if warnings:
                report.records_with_warnings += 1

            annotations.append((errors, warnings))

        return report, annotations

    @staticmethod
    def validate_records(
        records: List[SourceRecord],
        required_fields: Optional[List[str]] = None,
        allow_empty_non_essential: bool = True,
    ) -> ValidationReport:
        """Analyze and populate validation_errors and validation_warnings on each record."""
        report, annotations = DataValidator.analyze_records(
            records,
            required_fields=required_fields,
            allow_empty_non_essential=allow_empty_non_essential,
        )
        for record, (errors, warnings) in zip(records, annotations):
            record.validation_errors[:] = errors
            record.validation_warnings[:] = warnings
        return report
