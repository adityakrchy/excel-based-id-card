"""End-to-end check of the optimised photo flow in the real application."""

import os
import shutil
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

app = QApplication([])

from PIL import Image

from id_card_generator.core.constants import WorkflowStep
from id_card_generator.core.models import ProjectConfiguration, SourceRecord
from id_card_generator.ui.main_window import MainWindow

N = 3000
tmp = Path(tempfile.mkdtemp())
photos = tmp / "photos"
photos.mkdir()

print(f"creating {N} photos...")
template = Image.new("RGB", (1200, 900), (40, 70, 130))
for i in range(N):
    template.save(photos / f"{i:06d}.jpg", quality=60)

records = [
    SourceRecord(
        row_index=i,
        raw_pin=f"{i:06d}",
        pin=f"{i:06d}",
        data={"PIN Number": f"{i:06d}", "Name": f"Person {i}"},
    )
    for i in range(N)
]

win = MainWindow()
win.resize(1440, 900)
win.show()

ws = tmp / "workspace"
config = ProjectConfiguration(project_name="Photo Perf", workspace_dir=str(ws))
win.set_project(config)
win.page_photos.set_project_config(config)
win.page_photos.set_records(records)

t0 = time.perf_counter()
win.page_photos.matcher.set_directory(photos)
win.page_photos._rematch()
deadline = time.perf_counter() + 180
while time.perf_counter() < deadline:
    app.processEvents()
    if win.page_photos._worker is None and win.page_photos._match_worker is None:
        if win.page_photos.match_results:
            break
    time.sleep(0.01)
elapsed = time.perf_counter() - t0

summary = win.page_photos.match_summary
print(f"flow time        : {elapsed:6.2f}s")
print(f"results          : {len(win.page_photos.match_results):,}")
print(f"matched          : {summary.matched_count:,}")
print(f"unassigned       : {summary.unassigned_photos_count:,}")
print(f"workspace photos : {len(list((ws / 'photos').glob('*.jpg'))):,}")
print(f"metrics label    : {win.page_photos.lbl_metrics.text()}")

# Wait for the thumbnail workers.
deadline = time.perf_counter() + 60
while time.perf_counter() < deadline:
    app.processEvents()
    if win.page_photos._thread_pool.activeThreadCount() == 0:
        break
    time.sleep(0.01)

win.switch_page(WorkflowStep.PHOTOS)
app.processEvents()
win.grab().save("/tmp/opencode/photos_optimised.png")

import resource

print(f"peak rss         : {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024:6.1f} MB")
shutil.rmtree(tmp, ignore_errors=True)
