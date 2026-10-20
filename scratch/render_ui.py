"""Render the redesigned UI (dark + light) for visual review."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

app = QApplication([])

from id_card_generator.core.constants import WorkflowStep
from id_card_generator.ui.main_window import MainWindow

win = MainWindow()
win.resize(1440, 900)
win.show()


def capture(step, name, theme="black"):
    win.apply_theme(theme)
    win.switch_page(step)
    app.processEvents()
    win.grab().save(f"/tmp/opencode/ui_{name}.png")
    print("saved", name, theme)


capture(WorkflowStep.CANVAS_EDITOR, "editor", "black")
capture(WorkflowStep.CANVAS_EDITOR, "editor_light", "white")
capture(WorkflowStep.PHOTOS, "photos", "black")
capture(WorkflowStep.REVIEW, "review", "black")
capture(WorkflowStep.GENERATE, "generate", "black")
