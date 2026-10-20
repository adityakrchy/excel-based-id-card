"""Unit and integration tests for Project-based workspace workflow.

Verifies:
1. Creating a project workspace directory with data/, photos/, exports/, and project.json.
2. Importing Excel spreadsheet copies the file into <workspace>/data/ for reuse.
3. Photo matching copies ONLY matched photos into <workspace>/photos/, leaving unmatched photos untouched.
4. Manual photo overrides copy the selected photo to <workspace>/photos/.
5. Project reload recovers the workspace structure seamlessly.
"""

from pathlib import Path
from PIL import Image
from PySide6.QtCore import Qt

from id_card_generator.core.constants import MatchStatus
from id_card_generator.core.models import PhotoMatchResult, ProjectConfiguration, SourceRecord
from id_card_generator.core.project_manager import ProjectManager
from id_card_generator.data.excel_importer import ExcelImporter
from id_card_generator.data.photo_matcher import PhotoMatcher
from id_card_generator.ui.data_source_page import DataSourcePage
from id_card_generator.ui.dialogs.project_dialog import ProjectDialog
from id_card_generator.ui.photo_library_page import PhotoLibraryPage


def test_create_workspace(temp_dir: Path):
    """Test workspace initialization creates required subdirectories and project.json."""
    ws_path = temp_dir / "Student_Badges_2026"
    config = ProjectManager.create_workspace("Student Badges 2026", ws_path)

    assert ws_path.exists()
    assert (ws_path / "data").is_dir()
    assert (ws_path / "photos").is_dir()
    assert (ws_path / "exports").is_dir()
    assert (ws_path / "project.json").is_file()

    assert config.project_name == "Student Badges 2026"
    assert config.workspace_path == ws_path.resolve()
    assert config.data_dir == (ws_path / "data").resolve()
    assert config.photos_dir == (ws_path / "photos").resolve()
    assert config.exports_dir == (ws_path / "exports").resolve()


def test_copy_excel_to_workspace(temp_dir: Path):
    """Test importing spreadsheet copies file into workspace data/ directory."""
    ws_path = temp_dir / "Workspace"
    config = ProjectManager.create_workspace("My Workspace", ws_path)

    # Create external excel file
    external_dir = temp_dir / "external_source"
    external_dir.mkdir()
    external_excel = external_dir / "employees_q1.csv"
    external_excel.write_text("PIN Number,Name,Designation\nEMP001,Alice Smith,Engineer\nEMP002,Bob Jones,Designer\n")

    copied_excel = ProjectManager.copy_excel_to_workspace(config, external_excel)

    assert copied_excel.exists()
    assert copied_excel.parent == (ws_path / "data").resolve()
    assert copied_excel.name == "employees_q1.csv"
    assert copied_excel.read_text() == external_excel.read_text()

    # Re-reading project.json confirms excel_file_path is updated
    loaded = ProjectManager.load_project(ws_path)
    assert loaded.excel_file_path == str(copied_excel.resolve())


def test_data_source_page_copies_excel_to_workspace(qtbot, temp_dir: Path):
    """Test DataSourcePage integration copies spreadsheet on load_file."""
    ws_path = temp_dir / "DSP_Workspace"
    config = ProjectManager.create_workspace("DSP Workspace", ws_path)

    external_dir = temp_dir / "downloads"
    external_dir.mkdir()
    external_csv = external_dir / "class_records.csv"
    external_csv.write_text("PIN Number,Name,Department\nSTU101,Charlie Brown,Arts\nSTU102,Lucy Van Pelt,Science\n")

    page = DataSourcePage()
    qtbot.addWidget(page)
    page.show()
    page.set_project_config(config)

    page.load_file(external_csv)

    # The current_file_path should now be the file in workspace/data
    assert page.current_file_path is not None
    assert page.current_file_path.parent == (ws_path / "data").resolve()
    assert page.current_file_path.name == "class_records.csv"
    assert len(page.records) == 2
    assert not page.lbl_workspace_badge.isHidden()
    assert "data/class_records.csv" in page.lbl_workspace_badge.text()


def test_copy_matched_photos_only(temp_dir: Path):
    """Test photo matching copies ONLY matched photos into workspace/photos/ and leaves unmatched ones."""
    ws_path = temp_dir / "Photo_Workspace"
    config = ProjectManager.create_workspace("Photo Workspace", ws_path)

    # Create external photo folder
    external_photos = temp_dir / "camera_photos"
    external_photos.mkdir()

    # Create dummy image files
    img_101 = external_photos / "STU101.jpg"
    img_102 = external_photos / "STU102.png"
    img_unmatched_1 = external_photos / "RANDOM_999.jpg"
    img_unmatched_2 = external_photos / "VISITOR_001.png"

    for img_path in (img_101, img_102, img_unmatched_1, img_unmatched_2):
        im = Image.new("RGB", (64, 64), color="blue")
        im.save(img_path)

    records = [
        SourceRecord(row_index=0, raw_pin="STU101", pin="STU101", data={"PIN Number": "STU101", "Name": "Alice"}),
        SourceRecord(row_index=1, raw_pin="STU102", pin="STU102", data={"PIN Number": "STU102", "Name": "Bob"}),
        SourceRecord(row_index=2, raw_pin="STU103", pin="STU103", data={"PIN Number": "STU103", "Name": "Charlie"}),  # No photo exists
    ]

    matcher = PhotoMatcher()
    matcher.set_directory(external_photos)
    match_results, summary = matcher.match_all(records)

    assert summary.matched_count == 2
    assert summary.missing_count == 1

    # Copy matched photos to workspace
    updated_results, copied_count = ProjectManager.copy_matched_photos_to_workspace(config, match_results)

    assert copied_count == 2

    # Verify that matched photos were copied to workspace/photos/
    ws_photos = ws_path / "photos"
    assert (ws_photos / "STU101.jpg").exists()
    assert (ws_photos / "STU102.png").exists()

    # CRITICAL: Verify unmatched photos were NEVER copied into workspace
    assert not (ws_photos / "RANDOM_999.jpg").exists()
    assert not (ws_photos / "VISITOR_001.png").exists()

    # Verify result photo_path points to workspace copy
    assert updated_results[records[0].record_id].photo_path == str((ws_photos / "STU101.jpg").resolve())
    assert updated_results[records[1].record_id].photo_path == str((ws_photos / "STU102.png").resolve())
    assert updated_results[records[2].record_id].photo_path is None


def test_photo_library_page_workspace_integration(qtbot, temp_dir: Path):
    """Test PhotoLibraryPage automatically copies matched photos into workspace."""
    ws_path = temp_dir / "PLP_Workspace"
    config = ProjectManager.create_workspace("PLP Workspace", ws_path)

    external_photos = temp_dir / "source_photos"
    external_photos.mkdir()

    # Matched and unmatched photos
    img_matched = external_photos / "P100.jpg"
    img_unrelated = external_photos / "UNRELATED.jpg"
    Image.new("RGB", (32, 32), color="red").save(img_matched)
    Image.new("RGB", (32, 32), color="green").save(img_unrelated)

    records = [
        SourceRecord(row_index=0, raw_pin="P100", pin="P100", data={"PIN Number": "P100", "Name": "Person 100"}),
    ]

    page = PhotoLibraryPage()
    qtbot.addWidget(page)
    page.show()
    page.set_project_config(config)
    page.set_records(records)
    page.matcher.set_directory(external_photos)
    page._rematch()

    # The matching runs on a worker thread - wait for it to finish.
    for _ in range(200):
        if page._match_worker is None and page.match_results:
            break
        qtbot.wait(25)

    # Matched photo should now be in workspace photos
    ws_photos = ws_path / "photos"
    assert (ws_photos / "P100.jpg").exists()
    assert not (ws_photos / "UNRELATED.jpg").exists()

    assert page.match_results[records[0].record_id].photo_path == str((ws_photos / "P100.jpg").resolve())
    assert not page.lbl_workspace_photos.isHidden()
    assert "Copied 1 matched photo" in page.lbl_workspace_photos.text()


def test_copy_single_photo_manual_override(temp_dir: Path):
    """Test copying a single photo for manual override into workspace."""
    ws_path = temp_dir / "Override_Workspace"
    config = ProjectManager.create_workspace("Override Workspace", ws_path)

    ext_photo = temp_dir / "custom_avatar.png"
    Image.new("RGB", (32, 32), color="yellow").save(ext_photo)

    copied = ProjectManager.copy_single_photo_to_workspace(config, ext_photo, pin="STU999")
    assert copied.exists()
    assert copied.parent == (ws_path / "photos").resolve()
    assert copied.name == "custom_avatar.png"


def test_project_dialog_create_workspace(qtbot, temp_dir: Path):
    """Test ProjectDialog properly creates and emits new workspace."""
    dialog = ProjectDialog(initial_mode="create")
    qtbot.addWidget(dialog)

    ws_dest = temp_dir / "DialogProject"
    dialog.txt_project_name.setText("Dialog Test Project")
    dialog.txt_workspace_path.setText(str(ws_dest))

    with qtbot.waitSignal(dialog.workspace_ready, timeout=2000) as blocker:
        dialog._on_submit()

    assert dialog.result() == ProjectDialog.Accepted
    assert ws_dest.exists()
    assert (ws_dest / "project.json").exists()
    assert dialog.created_config is not None
    assert dialog.created_config.project_name == "Dialog Test Project"


def test_main_window_workspace_flow(qtbot, temp_dir: Path):
    """Test MainWindow integration with project workspace."""
    from id_card_generator.ui.main_window import MainWindow

    ws_path = temp_dir / "MW_Workspace"
    config = ProjectManager.create_workspace("MainWindow Test Project", ws_path)

    window = MainWindow()
    qtbot.addWidget(window)
    window.set_project(config, ws_path)

    assert window.current_project_config is not None
    assert window.current_project_config.project_name == "MainWindow Test Project"
    assert "MW_Workspace" in window.windowTitle()
    assert window.page_data_source.project_config is not None
    assert window.page_photos.project_config is not None
    assert window.page_dashboard.current_project_config is not None
