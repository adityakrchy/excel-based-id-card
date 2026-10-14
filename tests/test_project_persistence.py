"""Unit tests for project persistence, saving, loading, and relinking."""

from pathlib import Path
from id_card_generator.core.constants import ReviewStatus
from id_card_generator.core.models import ProjectConfiguration
from id_card_generator.core.project_manager import ProjectManager


def test_project_save_load_relink(temp_dir: Path):
    proj_path = temp_dir / "my_project.json"
    dummy_excel = temp_dir / "data.xlsx"
    dummy_excel.touch()
    dummy_photos = temp_dir / "photos"
    dummy_photos.mkdir()

    cfg = ProjectConfiguration(
        project_name="Corporate Badges 2026",
        excel_file_path=str(dummy_excel),
        photo_dir_path=str(dummy_photos),
        column_mappings={"el-name": "Full Name", "el-pin": "PIN"},
        review_states={"r1": ReviewStatus.APPROVED},
    )

    ProjectManager.save_project(cfg, proj_path)
    assert proj_path.exists()

    loaded = ProjectManager.load_project(proj_path)
    assert loaded.project_name == "Corporate Badges 2026"
    assert loaded.excel_file_path == str(dummy_excel)
    assert loaded.review_states["r1"] == ReviewStatus.APPROVED

    # Test missing reference detection
    dummy_excel.unlink()  # delete excel file
    missing = ProjectManager.check_missing_references(loaded)
    assert len(missing) == 1
    assert missing[0][0] == "excel_file"

    # Relink
    new_excel = temp_dir / "new_data.xlsx"
    new_excel.touch()
    relinked = ProjectManager.relink_references(loaded, {"excel_file": str(new_excel)})
    assert relinked.excel_file_path == str(new_excel)
    assert len(ProjectManager.check_missing_references(relinked)) == 0
