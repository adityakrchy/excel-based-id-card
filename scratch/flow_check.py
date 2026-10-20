"""Walk the real production flow and report every step."""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

app = QApplication([])

import pandas as pd

from id_card_generator.core.constants import WorkflowStep
from id_card_generator.ui.main_window import MainWindow
from id_card_generator.ui.dialogs.new_project_dialog import NewProjectDialog

tmp = Path(tempfile.mkdtemp())
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

PAGES = {
    0: "Hub",
    1: "Data Source",
    2: "Photo Library",
    3: "Templates",
    4: "Designer",
    5: "Generate",
    6: "Review",
    7: "Export",
    8: "Settings",
}


def report(label):
    idx = win.stack.currentIndex()
    active = [t.value for t, s in win.studio_nav._states.items() if s.value == "active"]
    done = [t.value for t, s in win.studio_nav._states.items() if s.value == "done"]
    blocked = [t.value for t, s in win.studio_nav._states.items() if s.value == "blocked"]
    print(f"{label:34} -> {PAGES[idx]:14} active={active} done={done} blocked={blocked}")


# 1. New project from the hub.
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
win.switch_page(WorkflowStep.DATA_SOURCE)
app.processEvents()
report("1. new project")

# 2. Upload the data source.
win.page_data_source.load_file(xlsx, copy_to_workspace=False)
app.processEvents()
report("2. data source uploaded")

# 3. Continue with the photos directory (the footer's next button).
win.page_data_source.nav_bar.btn_next.click()
app.processEvents()
win.page_photos.matcher.photo_dir = str(photos)
win.page_photos._rescan()
app.processEvents()
report("3. photos directory")

# 4. Templates.
win.page_photos.nav_bar.btn_next.click()
app.processEvents()
win.page_templates._use_template()
app.processEvents()
report("4. template selected")

# 5. Designer.
win.page_templates.nav_bar.btn_next.click()
app.processEvents()
report("5. designer")

# 6. Generate.
win.page_editor.nav_bar.btn_next.click()
app.processEvents()
report("6. generate")

# 7. Review.
win.page_generation.nav_bar.btn_next.click()
app.processEvents()
report("7. review")

# 8. Export.
win.page_review.nav_bar.btn_next.click()
app.processEvents()
report("8. export")

# 9. Back to the hub - it must point at the next unfinished step.
win.page_export.nav_bar.btn_next.click()
app.processEvents()
report("9. back on the hub")
print("hub hint:", win.page_dashboard.lbl_flow_next.text())
print("hub button:", win.page_dashboard.btn_flow_continue.text())
win.grab().save("/tmp/opencode/flow_end.png")
