"""Persistent top workflow stepper navigation widget."""

from typing import Dict
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)
from id_card_generator.core.constants import WorkflowStep


class WorkflowNav(QFrame):
    """Top workflow indicator showing step progression and allowing quick navigation."""

    step_clicked = Signal(str)  # WorkflowStep value

    STEPS = [
        (WorkflowStep.DATA_SOURCE, "1. Data Source"),
        (WorkflowStep.PHOTOS, "2. Photos"),
        (WorkflowStep.TEMPLATES, "3. Template"),
        (WorkflowStep.CANVAS_EDITOR, "4. Mapping & Editor"),
        (WorkflowStep.GENERATE, "5. Generate"),
        (WorkflowStep.REVIEW, "6. Review"),
        (WorkflowStep.EXPORT, "7. Export"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workflow_stepper")
        self._buttons: Dict[WorkflowStep, QPushButton] = {}
        self._current_step = WorkflowStep.DATA_SOURCE

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(8)

        for i, (step, label) in enumerate(self.STEPS):
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, s=step: self.step_clicked.emit(s.value))
            layout.addWidget(btn)
            self._buttons[step] = btn

            if i < len(self.STEPS) - 1:
                arrow = QLabel("→")
                arrow.setStyleSheet("color: #64748B; font-weight: bold; padding: 0 4px;")
                layout.addWidget(arrow)

        layout.addStretch()
        self.set_active_step(WorkflowStep.DATA_SOURCE)

    def set_active_step(self, active_step: WorkflowStep) -> None:
        """Update step visual highlights."""
        self._current_step = active_step
        for step, btn in self._buttons.items():
            if step == active_step:
                btn.setProperty("active", "true")
                btn.setStyleSheet("color: #38BDF8; font-weight: bold; text-decoration: underline;")
            else:
                btn.setProperty("active", "false")
                btn.setStyleSheet("color: #94A3B8; font-weight: normal; text-decoration: none;")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def mark_step_completed(self, step: WorkflowStep, completed: bool = True) -> None:
        """Mark a step as successfully completed with checkmark."""
        if step in self._buttons:
            btn = self._buttons[step]
            base_label = next(lbl for s, lbl in self.STEPS if s == step)
            if completed:
                btn.setText(f"✓ {base_label}")
            else:
                btn.setText(base_label)
