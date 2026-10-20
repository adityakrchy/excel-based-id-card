"""Simulate the real user flow: new project -> data source -> photos."""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

app = QApplication([])

from id_card_generator.core.models import ProjectConfiguration
from id_card_generator.ui.main_window import MainWindow
from id_card_generator.ui.dialogs.new_project_dialog import NewProjectDialog

tmp = Path(tempfile.mkdtemp())

# Build a small spreadsheet to upload.
import pandas as pd

xlsx = tmp / "staff.xlsx"
pd.DataFrame(
    {
        "PIN Number": ["100001", "100002"],
        "Name": ["Aditya Sharma", "Priya Patel"],
        "Designation": ["Engineer", "Analyst"],
    }
).to_excel(xlsx, index=False)

photos = tmp / "photos"
photos.mkdir()
for i in range(2):
    (photos / f"10000{i + 1}.jpg").write_bytes(b"")

win = MainWindow()
win.resize(1440, 900)
win.show()


def state(label):
    print(f"--- {label}: page index = {win.stack.currentIndex()} (0=dashboard 1=data 2=photos 3=templates 4=editor 5=gen 6=review 7=export)")
    win.grab().save(f"/tmp/opencode/flow_{label}.png")


# 1. Create a new project (as the hub does).
dialog = NewProjectDialog(win, template_manager=win.template_manager)
dialog.txt_project_name.setText("Staff Badges 2026")
dialog._on_create_clicked()
cfg = dialog.created_config
win.records = []
win.columns = []
win.match_results = {}
win.column_mappings = {}
win.active_template = cfg.template
win.set_project(cfg, workspace_path=None)
if cfg.template:
    win.page_editor.load_template(cfg.template)
    win.page_templates.active_template = cfg.template
win.switch_page(win.step_to_index and __import__(
    "id_card_generator.core.constants", fromlist=["WorkflowStep"]
).WorkflowStep.DATA_SOURCE)
state("1_after_new_project")

# 2. Upload the data source.
win.page_data_source.load_file(xlsx, copy_to_workspace=False)
app.processEvents()
print("records loaded:", len(win.page_data_source.records), "columns:", win.page_data_source.columns)
state("2_after_data_upload")

# 3. Photos directory.
win.switch_page(__import__(
    "id_card_generator.core.constants", fromlist=["WorkflowStep"]
).WorkflowStep.PHOTOS)
app.processEvents()
win.page_photos.matcher.photo_dir = str(photos)
win.page_photos._rescan()
app.processEvents()
print("photo dir:", win.page_photos.matcher.photo_dir)
state("3_after_photos")

# 4. Continue to templates.
win.switch_page(__import__(
    "id_card_generator.core.constants", fromlist=["WorkflowStep"]
).WorkflowStep.TEMPLATES)
state("4_templates")

print("DONE")
