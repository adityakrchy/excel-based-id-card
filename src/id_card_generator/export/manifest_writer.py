"""Generates audit CSV manifests for exported ID cards."""

import csv
import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ManifestWriter:
    """Writes detailed CSV manifest for compliance, tracking, and audit trails."""

    FIELDNAMES = [
        "PIN Number",
        "Name",
        "Office Name",
        "Designation",
        "Constituency",
        "Source PDF",
        "Source Page",
        "Source Row",
        "Matched Photo Path",
        "Output Filename",
        "Review Status",
        "Export Status",
        "Exported At",
    ]

    @staticmethod
    def write_manifest(records_metadata: List[Dict[str, Any]], destination_file: Path) -> Path:
        """Write manifest CSV containing all record export entries."""
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(destination_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=ManifestWriter.FIELDNAMES)
            writer.writeheader()

            for item in records_metadata:
                row = {
                    "PIN Number": item.get("pin", ""),
                    "Name": item.get("name", ""),
                    "Office Name": item.get("office_name", ""),
                    "Designation": item.get("designation", ""),
                    "Constituency": item.get("constituency", ""),
                    "Source PDF": item.get("source_pdf", ""),
                    "Source Page": item.get("source_page", ""),
                    "Source Row": item.get("source_row", ""),
                    "Matched Photo Path": item.get("photo_path", ""),
                    "Output Filename": item.get("output_filename", ""),
                    "Review Status": item.get("review_status", ""),
                    "Export Status": item.get("export_status", "Success"),
                    "Exported At": now_str,
                }
                writer.writerow(row)

        logger.info("Audit manifest written to %s (%d rows)", destination_file, len(records_metadata))
        return destination_file
