"""Render the redesigned UI to PNG files for visual review."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

app = QApplication([])

from id_card_generator.core.constants import WorkflowStep
from id_card_generator.ui.main_window import MainWindow

win = MainWindow()
win.resize(1440, 900)
win.show()


def capture(step, name):
    win.switch_page(step)
    app.processEvents()
    win.grab().save(f"/tmp/opencode/ui_{name}.png")
    print("saved", name)


for step, name in [
    (WorkflowStep.DASHBOARD, "dashboard"),
    (WorkflowStep.DATA_SOURCE, "data"),
    (WorkflowStep.TEMPLATES, "templates"),
    (WorkflowStep.CANVAS_EDITOR, "editor"),
    (WorkflowStep.EXPORT, "export"),
]:
    capture(step, name)
