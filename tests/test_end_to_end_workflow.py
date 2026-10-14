"""End-to-end integration test validating the complete application workflow."""

from pathlib import Path
import tempfile
import pandas as pd
from PIL import Image

from id_card_generator.core.constants import OutputFormat, ReviewStatus
from id_card_generator.core.geometry import calculate_card_dimensions
from id_card_generator.core.models import (
    CanvasElement,
    ExportConfiguration,
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.data.excel_importer import ExcelImporter
from id_card_generator.data.photo_matcher import PhotoMatcher
from id_card_generator.export.export_manager import ExportManager
from id_card_generator.generation.batch_generator import BatchGenerator
from id_card_generator.review.review_manager import ReviewManager


def test_full_end_to_end_pipeline(sample_photos_dir: Path, tmp_path: Path):
    """Execute complete workflow from Excel to photo matching, template design, batch generation, review, and export."""

    # 1. Create synthetic Excel file with custom headers (Employee Code, Full Name, Department)
    excel_path = tmp_path / "staff.xlsx"
    df = pd.DataFrame([
        {"EmpCode": "100001", "FullName": "Aditya Sharma", "Dept": "Engineering"},
        {"EmpCode": "100002", "FullName": "Priya Patel", "Dept": "Product"},
        {"EmpCode": "888888", "FullName": "Missing Photo User", "Dept": "Operations"},
    ])
    df.to_excel(excel_path, index=False)

    # 2. Import Excel data
    columns, records = ExcelImporter.import_data(excel_path, pin_column_hint="EmpCode")
    assert len(records) == 3
    assert "EmpCode" in columns
    assert "FullName" in columns

    # 3. Photo matching with generic lookup key column 'EmpCode'
    matcher = PhotoMatcher()
    matcher.set_directory(sample_photos_dir)
    matcher.set_key_column("EmpCode")
    match_results, summary = matcher.match_all(records)

    assert summary.matched_count == 2
    assert summary.missing_count == 1

    # 4. Create custom Blank Canvas template with physical dimensions (85.6 x 54 mm, 300 DPI)
    w_px, h_px, _, _ = calculate_card_dimensions(85.6, 54.0, "mm", 300, orientation="landscape")
    template = TemplateDefinition(
        name="Staff ID Card",
        width_px=w_px,
        height_px=h_px,
        dpi=300,
        unit="mm",
        width_physical=85.6,
        height_physical=54.0,
        orientation="landscape",
        background_color="#1E293B",
        elements=[
            # Header background
            CanvasElement(name="Header", type="rect", x=0, y=0, width=w_px, height=80),
            # Photo element
            CanvasElement(name="Photo", type="photo", x=40, y=100, width=180, height=220, binding="photo"),
            # Dynamic text elements mapped to spreadsheet columns
            CanvasElement(name="Name", type="dynamic_text", x=250, y=120, width=500, height=40, binding="FullName"),
            CanvasElement(name="Code", type="dynamic_text", x=250, y=170, width=300, height=30, binding="EmpCode"),
            CanvasElement(name="Dept", type="dynamic_text", x=250, y=210, width=300, height=30, binding="Dept"),
        ]
    )

    column_mappings = {
        template.elements[2].id: "FullName",
        template.elements[3].id: "EmpCode",
        template.elements[4].id: "Dept",
    }

    # 5. Batch generation to staging directory
    staging_dir = tmp_path / "staging"
    gen_summary = BatchGenerator.generate_batch(
        template=template,
        records=records,
        match_results=match_results,
        column_mappings=column_mappings,
        settings=RenderSettings(),
        target_dir=staging_dir,
    )

    assert gen_summary.total_records == 3
    assert gen_summary.completed_count == 3  # All generated (missing photo gets placeholder)
    assert len(gen_summary.results) == 3

    # 6. Sequential Review & Approval
    review_mgr = ReviewManager()
    review_mgr.initialize_from_generation(records, gen_summary.results)
    assert len(review_mgr.records) == 3

    # Approve record 1 and 2, reject record 3 (missing photo)
    review_mgr.update_status(records[0].record_id, ReviewStatus.APPROVED)
    review_mgr.update_status(records[1].record_id, ReviewStatus.APPROVED)
    review_mgr.update_status(records[2].record_id, ReviewStatus.REJECTED)

    assert review_mgr.counts["approved"] == 2
    assert review_mgr.counts["rejected"] == 1

    # 7. Export approved cards only with CSV manifest
    export_dir = tmp_path / "final_export"
    export_cfg = ExportConfiguration(
        output_dir=str(export_dir),
        format=OutputFormat.PNG,
        approved_only=True,
        export_manifest=True,
        export_contact_sheet=False,
    )

    source_records_map = {r.record_id: r for r in records}
    export_res = ExportManager.export_batch(
        review_records=review_mgr.records,
        config=export_cfg,
        source_records_map=source_records_map,
        match_results_map=match_results,
    )

    assert export_res.exported_count == 2
    assert export_res.skipped_count == 1
    assert export_res.failed_count == 0
    assert len(export_res.exported_files) == 2
    assert export_res.manifest_path is not None
    assert Path(export_res.manifest_path).exists()

    # Validate exported images exist and match dimensions
    for f_path in export_res.exported_files:
        assert Path(f_path).exists()
        with Image.open(f_path) as im:
            assert im.size == (w_px, h_px)
