"""Spreadsheet data validation and integrity verification."""

from collections import Counter
from typing import Dict, List, Optional
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
    def validate_records(
        records: List[SourceRecord],
        required_fields: Optional[List[str]] = None,
        allow_empty_non_essential: bool = True,
    ) -> ValidationReport:
        """Analyze and populate validation_errors and validation_warnings on each record."""
        report = ValidationReport()
        report.total_records = len(records)

        # Count occurrences of non-empty normalized PINs
        pin_counter = Counter(r.pin for r in records if r.pin)

        for pin, count in pin_counter.items():
            if count > 1:
                report.duplicate_pins[pin] = count

        for r in records:
            r.validation_errors.clear()
            r.validation_warnings.clear()

            # 1. Missing PIN validation
            if not r.pin:
                r.validation_errors.append("Missing PIN Number")
                report.missing_pins += 1

            # 2. Duplicate PIN validation
            elif pin_counter[r.pin] > 1:
                r.validation_warnings.append(
                    f"Duplicate PIN Number '{r.pin}' (found in {pin_counter[r.pin]} records)"
                )

            # 3. Accidental whitespace warning
            if r.raw_pin and r.raw_pin != r.pin:
                r.validation_warnings.append(
                    f"PIN contained accidental surrounding whitespace (raw: '{r.raw_pin}')"
                )

            # 4. Required fields check
            if required_fields:
                for field in required_fields:
                    val = r.get_value(field)
                    if not val:
                        msg = f"Missing required field '{field}'"
                        if allow_empty_non_essential and field.lower() != "pin number":
                            r.validation_warnings.append(msg)
                        else:
                            r.validation_errors.append(msg)

            # Record metrics
            if r.is_valid:
                report.valid_records += 1
            else:
                report.records_with_errors += 1

            if r.validation_warnings:
                report.records_with_warnings += 1

        return report
