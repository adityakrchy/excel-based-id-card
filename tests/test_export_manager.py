"""Unit tests for export manager, CSV manifest, and PDF contact sheet."""

from pathlib import Path
from PIL import Image
from id_card_generator.core.constants import OutputFormat, ReviewStatus
from id_card_generator.core.models import (
    ExportConfiguration,
    PhotoMatchResult,
    ReviewRecord,
    SourceRecord,
)
from id_card_generator.export.export_manager import ExportManager


def test_export_batch(temp_dir: Path):
    staging_dir = temp_dir / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    out_dir = temp_dir / "final_export"

    # Create dummy staging images
    img1 = Image.new("RGBA", (200, 300), color="blue")
    img1_path = staging_dir / "1001_Alice.png"
    img1.save(img1_path)

    img2 = Image.new("RGBA", (200, 300), color="green")
    img2_path = staging_dir / "1002_Bob.png"
    img2.save(img2_path)

    rev_records = [
        ReviewRecord(record_id="r1", pin="1001", name="Alice", status=ReviewStatus.APPROVED, rendered_image_path=str(img1_path)),
        ReviewRecord(record_id="r2", pin="1002", name="Bob", status=ReviewStatus.REJECTED, rendered_image_path=str(img2_path)),
    ]

    source_records = {
        "r1": SourceRecord(row_index=1, raw_pin="1001", pin="1001", data={"Name": "Alice", "Office Name": "HQ"}),
        "r2": SourceRecord(row_index=2, raw_pin="1002", pin="1002", data={"Name": "Bob", "Office Name": "Branch"}),
    }

    match_results = {
        "r1": PhotoMatchResult(pin="1001", photo_path="/photos/1001.jpg"),
        "r2": PhotoMatchResult(pin="1002", photo_path="/photos/1002.jpg"),
    }

    config = ExportConfiguration(
        output_dir=str(out_dir),
        format=OutputFormat.PNG,
        approved_only=True,
        export_manifest=True,
        export_contact_sheet=True,
    )

    result = ExportManager.export_batch(
        config=config,
        review_records=rev_records,
        source_records_map=source_records,
        match_results_map=match_results,
    )

    # Since approved_only=True, only Alice is exported, Bob is skipped
    assert result.exported_count == 1
    assert result.skipped_count == 1
    assert result.failed_count == 0

    assert (out_dir / "1001_Alice.png").exists()
    assert (out_dir / "export_manifest.csv").exists()
    assert (out_dir / "contact_sheet.pdf").exists()
