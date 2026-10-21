"""Persistent top workflow stepper navigation widget with home/dashboard and sequential stages."""

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
        (WorkflowStep.CANVAS_EDITOR, "4. Mapping && Editor"),
        (WorkflowStep.GENERATE, "5. Generate && Review"),
        (WorkflowStep.EXPORT, "6. Export"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workflow_stepper")
        self._buttons: Dict[WorkflowStep, QPushButton] = {}
        self._current_step = WorkflowStep.DASHBOARD

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(8)

        # 0. Dashboard & Settings Button
        self.btn_dashboard = QPushButton("⌂ Dashboard && Settings")
        self.btn_dashboard.setFlat(True)
        self.btn_dashboard.setCursor(Qt.PointingHandCursor)
        self.btn_dashboard.clicked.connect(lambda: self.step_clicked.emit(WorkflowStep.DASHBOARD.value))
        layout.addWidget(self.btn_dashboard)
        self._buttons[WorkflowStep.DASHBOARD] = self.btn_dashboard

        sep = QLabel("|")
        sep.setStyleSheet("color: #475569; padding: 0 4px;")
        layout.addWidget(sep)

        # 1-7 Sequential Steps
        for i, (step, label) in enumerate(self.STEPS):
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, s=step: self.step_clicked.emit(s.value))
            layout.addWidget(btn)
            self._buttons[step] = btn

            if i < len(self.STEPS) - 1:
                arrow = QLabel("→")
                arrow.setStyleSheet("color: #64748B; font-weight: bold; padding: 0 2px;")
                layout.addWidget(arrow)

        layout.addStretch()
        self.set_active_step(WorkflowStep.DASHBOARD)

    def set_active_step(self, active_step: WorkflowStep) -> None:
        """Update step visual highlights."""
        self._current_step = active_step
        for step, btn in self._buttons.items():
            if step == active_step:
                btn.setProperty("active", "true")
                btn.setStyleSheet(
                    "color: #38BDF8; font-weight: bold; background-color: rgba(56, 189, 248, 0.12); "
                    "border-radius: 4px; padding: 4px 8px;"
                )
            else:
                btn.setProperty("active", "false")
                btn.setStyleSheet(
                    "color: #94A3B8; font-weight: normal; background-color: transparent; padding: 4px 8px;"
                )
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def mark_step_completed(self, step: WorkflowStep, completed: bool = True) -> None:
        """Mark a step as successfully completed with checkmark."""
        if step in self._buttons:
            btn = self._buttons[step]
            base_label = next((lbl for s, lbl in self.STEPS if s == step), None)
            if not base_label:
                return
            if completed:
                btn.setText(f"✓ {base_label}")
            else:
                btn.setText(base_label)
