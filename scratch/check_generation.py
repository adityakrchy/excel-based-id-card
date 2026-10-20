"""Verify the generation flow and measure the parallel rendering speed-up."""

import os
import shutil
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

app = QApplication([])

from id_card_generator.core.models import (
    CanvasElement,
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.generation.batch_generator import BatchGenerator
from id_card_generator.ui.generation_page import GenerationPage

N = 400
tmp = Path(tempfile.mkdtemp())

template = TemplateDefinition(
    name="Perf Card", width_px=1012, height_px=638, dpi=300, background_color="#FFFFFF"
)
template.elements = [
    CanvasElement(
        id=f"t{i}",
        name=f"Text {i}",
        type="static_text",
        x=40,
        y=40 + i * 60,
        width=900,
        height=50,
        static_content=f"Field {i}",
        z_index=i,
    )
    for i in range(8)
]
records = [
    SourceRecord(
        row_index=i,
        raw_pin=f"{i:06d}",
        pin=f"{i:06d}",
        data={"PIN Number": f"{i:06d}", "Name": f"Person {i}"},
    )
    for i in range(N)
]

# --- serial vs parallel -------------------------------------------------
t0 = time.perf_counter()
s1 = BatchGenerator.generate_batch(
    template=template, records=records, match_results={}, column_mappings={},
    settings=RenderSettings(), target_dir=tmp / "serial", workers=1,
)
t_serial = time.perf_counter() - t0

t0 = time.perf_counter()
s2 = BatchGenerator.generate_batch(
    template=template, records=records, match_results={}, column_mappings={},
    settings=RenderSettings(), target_dir=tmp / "parallel", workers=4,
)
t_parallel = time.perf_counter() - t0

print(f"serial   : {t_serial:6.2f}s  ({s1.completed_count} cards)")
print(f"parallel : {t_parallel:6.2f}s  ({s2.completed_count} cards)")
print(f"speed-up  : {t_serial / max(t_parallel, 0.001):.2f}x")
print(f"order kept: {[r.pin for r in s1.results] == [r.pin for r in s2.results]}")

# --- the page (this used to raise AttributeError) ------------------------
page = GenerationPage()
page.resize(1200, 800)
page.show()
page.set_generation_context(
    template=template, records=records[:20], match_results={}, column_mappings={},
    settings=RenderSettings(),
)
done = []
page.generation_completed.connect(done.append)
page._start_generation()

deadline = time.perf_counter() + 60
while not done and time.perf_counter() < deadline:
    app.processEvents()
    time.sleep(0.01)

print(f"page run  : {'ok' if done else 'FAILED'}  ({done[0].completed_count if done else 0} cards)")
print(f"status    : {page.lbl_status.text()}")
print(f"engine    : {page.pill_engine_state.text() if hasattr(page.pill_engine_state, 'text') else ''}")
page.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
