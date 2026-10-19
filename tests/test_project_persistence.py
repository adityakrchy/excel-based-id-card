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


def test_idcrt_format_save_load(temp_dir: Path):
    """Test saving and loading projects using the .idcrt extension."""
    idcrt_path = temp_dir / "Executive_Pass_2026.idcrt"
    dummy_excel = temp_dir / "exec_list.xlsx"
    dummy_excel.touch()

    cfg = ProjectConfiguration(
        project_name="Executive Pass 2026",
        excel_file_path=str(dummy_excel),
        column_mappings={"name": "Executive Name", "role": "Title"},
    )

    ProjectManager.save_project(cfg, idcrt_path)
    assert idcrt_path.exists()
    assert idcrt_path.suffix == ".idcrt"

    loaded = ProjectManager.load_project(idcrt_path)
    assert loaded.project_name == "Executive Pass 2026"
    assert loaded.excel_file_path == str(dummy_excel)
    assert loaded.column_mappings["name"] == "Executive Name"
    assert loaded.workspace_dir is None


def test_main_window_idcrt_save_load(qtbot, temp_dir: Path):
    """Test MainWindow project saving and loading with .idcrt file."""
    from id_card_generator.ui.main_window import MainWindow

    idcrt_path = (temp_dir / "Badge_Project_2026.idcrt").resolve()
    dummy_excel = temp_dir / "staff.xlsx"
    dummy_excel.touch()

    cfg = ProjectConfiguration(
        project_name="Badge Project 2026",
        excel_file_path=str(dummy_excel),
    )

    window = MainWindow()
    qtbot.addWidget(window)
    window.set_project(cfg)

    # Save to .idcrt path
    window._save_to_path(idcrt_path)
    assert idcrt_path.exists()
    assert window.current_project_path == idcrt_path
    assert "Badge_Project_2026.idcrt" in window.header_bar.lbl_project_name.text()

    # Load from .idcrt path into a new window
    window2 = MainWindow()
    qtbot.addWidget(window2)
    success = window2.load_project_from_file(idcrt_path)
    assert success is True
    assert window2.current_project_config.project_name == "Badge Project 2026"
    assert "Badge_Project_2026.idcrt" in window2.header_bar.lbl_project_name.text()


def test_new_project_dialog(qtbot):
    """Test NewProjectDialog creates configuration cleanly without workspace setup."""
    from id_card_generator.ui.dialogs.new_project_dialog import NewProjectDialog

    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)

    dialog.txt_project_name.setText("Summer Camp Badges")
    dialog._on_create_clicked()

    assert dialog.result() == NewProjectDialog.Accepted
    assert dialog.created_config is not None
    assert dialog.created_config.project_name == "Summer Camp Badges"
    assert dialog.created_config.workspace_dir is None

