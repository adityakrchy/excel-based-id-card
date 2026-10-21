"""UI integration tests using pytest-qt."""

import pytest
from id_card_generator.core.constants import APP_NAME, WorkflowStep
from id_card_generator.ui.main_window import MainWindow


@pytest.fixture
def app_window(qtbot):
    """Fixture providing an instantiated MainWindow."""
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def test_main_window_initialization(app_window: MainWindow):
    assert app_window.windowTitle().startswith(APP_NAME)
    assert app_window.stack.currentIndex() == 0  # Starts on Dashboard
    assert app_window.nav_buttons[WorkflowStep.DASHBOARD].isChecked()


def test_main_window_navigation(app_window: MainWindow, qtbot):
    # Navigate to Data Source
    app_window.switch_page(WorkflowStep.DATA_SOURCE)
    assert app_window.stack.currentIndex() == 1
    assert app_window.nav_buttons[WorkflowStep.DATA_SOURCE].isChecked()

    # Navigate to Photos
    app_window.switch_page(WorkflowStep.PHOTOS)
    assert app_window.stack.currentIndex() == 2

    # Navigate to Templates
    app_window.switch_page(WorkflowStep.TEMPLATES)
    assert app_window.stack.currentIndex() == 3

    # Navigate to Canvas Editor
    app_window.switch_page(WorkflowStep.CANVAS_EDITOR)
    assert app_window.stack.currentIndex() == 4

    # Navigate to Generate & Review
    app_window.switch_page(WorkflowStep.GENERATE)
    assert app_window.stack.currentIndex() == 5

    # Navigate to Export
    app_window.switch_page(WorkflowStep.EXPORT)
    assert app_window.stack.currentIndex() == 6

    # Navigate to Settings
    app_window.switch_page(WorkflowStep.SETTINGS)
    assert app_window.stack.currentIndex() == 7


def test_theme_switching(app_window: MainWindow):
    # Switch to light theme
    app_window.apply_theme("light")
    # Switch to dark theme
    app_window.apply_theme("dark")
    assert True
