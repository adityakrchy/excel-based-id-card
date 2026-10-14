"""Unit tests for batch card generation."""

from pathlib import Path
from id_card_generator.core.constants import MissingPhotoPolicy, OutputFormat
from id_card_generator.core.models import PhotoMatchResult, RenderSettings, SourceRecord
from id_card_generator.generation.batch_generator import BatchGenerator
from id_card_generator.templates.template_manager import TemplateManager


def test_batch_generator_run(sample_photos_dir: Path, temp_dir: Path):
    mgr = TemplateManager()
    tmpl = mgr.get_template("builtin-classic-portrait")
    assert tmpl is not None

    records = [
        SourceRecord(row_index=1, raw_pin="100001", pin="100001", data={"Name": "Aditya Sharma"}),
        SourceRecord(row_index=2, raw_pin="100002", pin="100002", data={"Name": "Priya Patel"}),
        SourceRecord(row_index=3, raw_pin="888888", pin="888888", data={"Name": "Missing Photo"}),
    ]

    matches = {
        records[0].record_id: PhotoMatchResult(pin="100001", photo_path=str(sample_photos_dir / "100001.jpg")),
        records[1].record_id: PhotoMatchResult(pin="100002", photo_path=str(sample_photos_dir / "100002.png")),
        records[2].record_id: PhotoMatchResult(pin="888888", photo_path=None),
    }

    staging_dir = temp_dir / "staging"
    settings = RenderSettings(
        output_format=OutputFormat.PNG,
        missing_photo_policy=MissingPhotoPolicy.GENERATE_WITH_PLACEHOLDER,
    )

    summary = BatchGenerator.generate_batch(
        template=tmpl,
        records=records,
        match_results=matches,
        column_mappings={},
        settings=settings,
        target_dir=staging_dir,
    )

    assert summary.total_records == 3
    assert summary.completed_count == 3
    assert summary.failed_count == 0
    assert len(summary.results) == 3

    # Check files exist
    for res in summary.results:
        assert res.success is True
        assert res.image_path is not None
        assert Path(res.image_path).exists()
