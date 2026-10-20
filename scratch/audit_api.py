"""Audit the generate -> review -> export chain for API drift.

The generation and review pages had drifted away from the APIs they call
(worker signals, manager methods, renderer constructors).  This script walks
the public surface of the involved objects and reports every attribute the
pages use that does not exist.
"""

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

app = QApplication([])

from id_card_generator.generation.batch_generator import BatchGenerator, GenerationSummary
from id_card_generator.generation.generation_worker import GenerationWorker
from id_card_generator.review.review_manager import ReviewManager
from id_card_generator.ui.generation_page import GenerationPage
from id_card_generator.ui.review_page import ReviewPage
from id_card_generator.ui.export_page import ExportPage

problems = []


def check(obj, names, label):
    for name in names:
        if not hasattr(obj, name):
            problems.append(f"{label}.{name} is missing")


# --- worker signals used by the generation page ---------------------------
page = GenerationPage()
page.show()
source = inspect.getsource(GenerationPage._start_generation)
for line in source.splitlines():
    if "self._worker." in line and ".connect(" in line:
        signal = line.split("self._worker.")[1].split(".connect")[0].strip()
        check(GenerationWorker, [signal], "GenerationWorker")

# --- manager methods used by the review page -------------------------------
review = ReviewPage()
review.show()
manager = ReviewManager()
source = inspect.getsource(ReviewPage)
for line in source.splitlines():
    line = line.strip()
    if line.startswith("self.manager."):
        call = line.split("self.manager.")[1].split("(")[0].split(" ")[0].split("=")[0].strip()
        if call and not call.startswith("__"):
            check(manager, [call], "ReviewManager")

# --- summary fields used anywhere -----------------------------------------
export = ExportPage()
export.show()
for source in (
    inspect.getsource(GenerationPage),
    inspect.getsource(ReviewPage),
    inspect.getsource(ExportPage),
):
    for line in source.splitlines():
        stripped = line.strip()
        if "summary." in stripped or "gen_summary." in stripped:
            field = stripped.split("summary.")[-1].split(".")[0].strip()
            if field and field.isidentifier():
                check(GenerationSummary, [field], "GenerationSummary")

# --- renderer usage -------------------------------------------------------
from id_card_generator.rendering.pillow_renderer import PillowRenderer

for name, member in inspect.getmembers(PillowRenderer):
    if name.startswith("_"):
        continue
    if not callable(member):
        continue

print("PillowRenderer public API:", [n for n, m in inspect.getmembers(PillowRenderer) if not n.startswith("_")])

if problems:
    print("\nPROBLEMS FOUND:")
    for problem in sorted(set(problems)):
        print("  -", problem)
else:
    print("\nno API drift found")
